"""Binance USD-M Futures Position Protection（自 monitor 项目并入，Phase 3）。

T1: 2h / 7-bar structure / 0.5 ATR confirmation / real-time trigger.
T2/T3: closed-candle structure confirmation.
TP: fixed-R staged maker-only reduce orders with retry/cycling.
Position lifecycle is isolated for every manual close/reopen cycle.

与独立 monitor 项目的差异（并入后端时仅做以下改造，风控判定逻辑零改动）：
- 配置来源：SQLite settings 的 position_protection 字典（默认值见 config.py），
  不再读取 config/config.json；
- 状态持久化：SQLite 的 protection_state 表（key='state'），不再写 JSON 文件；
- 告警：改为 WebApp 的 notifier（UI 日志 + loguru），不再依赖钉钉/桌面通知；
- REST 限流复用 backend/app/core/rest_guardian.py，删除本文件内嵌的重复实现。

Phase 3 T08：本文件拆分为职责模块（判定/动作语义零改动），engine.py 保留
轮询主循环并对外做 re-export facade，保持既有 `from .engine import x` /
`engine.x` 导入不变。模块归属：config=配置深合并；state=状态持久化/Runtime/
动作锁/reconcile；market_data=K线/ATR/EMA/黑天鹅行情；stops=止损判定；
take_profit=TP 阶梯；exits=应急减仓/市价单（静态审计白名单）+ 交易所 STOP 管理。
"""

import asyncio
import random
import time

from loguru import logger

from ..core.rest_guardian import CircuitBreakerException
from .config import DEFAULT_CONFIG, _f, load_protection_config
from .exits import (  # noqa: F401  facade re-export
    CLIENT_ALGO_PREFIX, LAST_STOP_MAINTAIN_TIME, LAST_STOP_ORDER_TIME,
    _algo_methods, _algo_status, _algo_trigger, _cancel_algo,
    _cancel_bot_reduce_orders, _cancel_program_stops_for_flat, _cancel_stop_orders,
    _create_full_close_stop, _ensure_disaster_stop, _find_stop_orders,
    _full_exit_with_revalidation, _get_open_algo_orders, _is_program_stop,
    _limit_reduce_with_maker_retry, _make_client_algo_id, _market_reduce_and_confirm,
    _take_over_external_stops,
)
from .market_data import (  # noqa: F401  facade re-export
    _atr_from_df, _atr_from_rows, _closed_atr, _closed_df, _ema_structure_from_rows,
    _ema_value, _emergency_signal, _fetch_ohlcv, _fetch_positions, _fetch_ticker,
    _market_snapshot, _position_fresh, _two_source_price_ok,
)
from .notifier import send_alert
from .state import (  # noqa: F401  facade re-export
    LAST_RISK_ACTION_TS, RUNTIME, Runtime, _ACTION_EXECUTION_LOCK, _STATUS_LOG_LAST,
    _load_state, _mark_risk_action_done, _position_open_time_ms, _position_side,
    _position_size, _raw_position_side, _reconcile_position_state, _rest,
    _risk_action_lock_key, _risk_action_on_cooldown, _save_state, _state_key,
    _status_log, _try_lock_risk_action,
)
from .stops import (  # noqa: F401  facade re-export
    _calculate_disaster_stop, _calculate_dynamic_protection_stop,
    _strategy_levels_from_rows,
)
from .take_profit import (  # noqa: F401  facade re-export
    _initialize_take_profit_levels, _take_profit_hit, _take_profit_protection_stop,
    _tp3_action_text, _tp3_remaining_ratio,
)


async def cleanup_orphaned_state_and_orders(exchange, conf):
    try:
        positions = await _fetch_positions(exchange, conf, priority="NORMAL", force=True)
        active = {(p.get("symbol"), _position_side(p)) for p in positions if _position_size(p) > 0}
        state = _load_state()
        modified = False

        for key in list(state):
            if "_" not in key:
                state.pop(key, None); modified = True; continue
            symbol, side = key.rsplit("_", 1)
            if (symbol, side) not in active:
                state.pop(key, None); modified = True

        if modified:
            _save_state(state)

    except Exception as exc:
        logger.error(f"清理孤儿状态/订单异常: {exc}")


# ---------------------------------------------------------------------------
# Per-position guardian
# ---------------------------------------------------------------------------

async def _execute_tp_reduce(exchange, symbol, side, pos_state, fresh, current_price,
                             current_contracts, level, conf, full_config):
    """TP1/TP2/TP3 阶梯止盈减仓的共用执行逻辑（消除 watch_symbol_position 内三档重复分支）。

    调用方需已持有 RUNTIME.action_lock。返回减仓后剩余仓位（<=1e-10 表示已清空）。
    """
    key = _state_key(symbol, side)
    base = _f(pos_state.get("base_contracts"), current_contracts)
    if level == 3:
        if not _try_lock_risk_action(symbol, side, pos_state, "TP3"):
            return current_contracts
        tp3_keep = _tp3_remaining_ratio(conf)
        pos_state["tp3_triggered"] = True
        state = _load_state(); state[key] = pos_state; _save_state(state)
        if tp3_keep <= 0:
            qty = current_contracts
            msg = (f"[{symbol}] 🎯 躺平达到{conf.get('tp3_r_multiple',3.0):g}R，执行全部止盈！ "
                   f"周期:{pos_state.get('risk_cycle_id')} | 当前:{current_price:.8f} | "
                   f"躺平:{_f(pos_state.get('tp3_price')):.8f} | 模式:Maker挂单循环全平")
            alert_title = "止盈提示: 躺平 全平"
            reason = "躺平止盈"
        else:
            reduce_ratio = max(0.0, 1.0 - tp3_keep)
            qty = min(current_contracts, base * reduce_ratio)
            msg = (f"[{symbol}] 🎯 躺平达到{conf.get('tp3_r_multiple',3.0):g}R，执行躺平止盈，保留{tp3_keep:.0%}仓位继续吃利润！ "
                   f"周期:{pos_state.get('risk_cycle_id')} | 当前:{current_price:.8f} | 躺平:{_f(pos_state.get('tp3_price')):.8f} | "
                   f"本次减仓:{qty:.8f} | 模式:Maker挂单循环")
            alert_title = "止盈提示: 躺平 分批止盈"
            reason = "躺平止盈"
    elif level == 2:
        if pos_state.get("tp2_triggered") or not _try_lock_risk_action(symbol, side, pos_state, "TP2"):
            return current_contracts
        pos_state["tp2_triggered"] = True
        ratio = float(conf.get("tp2_ratio", 0.30))
        qty = min(current_contracts, base * ratio)
        msg = (f"[{symbol}] 🎯 TP2达到{conf.get('tp2_r_multiple',2.0):g}R，执行{int(ratio*100)}%止盈并锁定利润！ "
               f"周期:{pos_state.get('risk_cycle_id')} | 当前:{current_price:.8f} | TP2:{_f(pos_state.get('tp2_price')):.8f}")
        alert_title = "止盈提示: TP2 减仓"
        reason = "TP2止盈"
    else:
        if pos_state.get("tp1_triggered") or not _try_lock_risk_action(symbol, side, pos_state, "TP1"):
            return current_contracts
        pos_state["tp1_triggered"] = True
        ratio = float(conf.get("tp1_ratio", 0.20))
        qty = min(current_contracts, base * ratio)
        msg = (f"[{symbol}] 🎯 TP1达到{conf.get('tp1_r_multiple',1.0):g}R，执行{int(ratio*100)}%止盈并启动保本保护！ "
               f"周期:{pos_state.get('risk_cycle_id')} | 当前:{current_price:.8f} | TP1:{_f(pos_state.get('tp1_price')):.8f}")
        alert_title = "止盈提示: TP1 减仓"
        reason = "TP1止盈"

    state = _load_state(); state[key] = pos_state; _save_state(state)

    logger.success(msg)
    send_alert(full_config, alert_title, msg, symbol=symbol)

    if qty > 0:
        _, after = await _limit_reduce_with_maker_retry(
            exchange, symbol, side, fresh, qty, reason, conf,
            int(pos_state.get("position_version", 0)), pos_state,
            max_retries=int(conf.get("tp_limit_max_retries", 0)),
            check_interval_sec=float(conf.get("tp_limit_check_interval_sec", 1.0)),
            timeout_sec=float(conf.get("tp_limit_timeout_sec", 10.0)),
            allow_market_fallback=False,
            maker_only=bool(conf.get("tp_maker_only", True)),
        )
        pos_state["contracts"] = after
    else:
        after = current_contracts

    if level == 3:
        pos_state["tp_protection_stage"] = 3 if tp3_keep > 0 else 0
        if tp3_keep > 0:
            logger.success(f"[{symbol}] 🔐 躺平完成：剩余{after}仓位继续由移动STOP保护利润")
    elif level == 2:
        pos_state["tp_protection_stage"] = 2
        logger.success(f"[{symbol}] 🔐 TP2完成：下一轮交易所STOP抬到 TP1 上方锁定利润")
    else:
        pos_state["tp_protection_stage"] = 1
        logger.success(f"[{symbol}] 🔐 TP1完成：下一轮交易所STOP抬到保本上方保护本金")

    state = _load_state(); state[key] = pos_state; _save_state(state)
    if after <= 1e-10:
        state.pop(key, None); _save_state(state)
    return after


async def _execute_tiered_reduce(exchange, symbol, side, pos_state, fresh, current_contracts,
                                 tier, qty, msg, alert_title, reason, conf, full_config):
    """T1/T2 分级结构减仓的共用执行逻辑（限价 maker 减仓，消除 watch_symbol_position 内重复分支）。

    调用方需已持有 RUNTIME.action_lock。返回减仓后剩余仓位。
    """
    key = _state_key(symbol, side)
    action_key = (symbol, side, str(pos_state.get("risk_cycle_id")), tier)
    if action_key in RUNTIME.risk_action_latches:
        logger.warning(f"[{symbol}/{side}] 🛑 {tier}本风险周期已执行/已锁定，跳过重复动作。")
        return current_contracts
    if _risk_action_on_cooldown(symbol, side, tier, conf):
        logger.warning(
            f"[{symbol}/{side}] ⏳ {tier} 距上次减仓不足 "
            f"{_f(conf.get('risk_action_min_interval_sec'), 0.0):.0f}s"
            f"（疑似风险周期被异常重建），本次跳过，不落闩。")
        return current_contracts
    RUNTIME.risk_action_latches.add(action_key)
    if tier == "T2":
        pos_state["t2_triggered"] = True
    else:
        pos_state["t1_triggered"] = True
    state = _load_state(); state[key] = pos_state; _save_state(state)

    logger.warning(msg)
    send_alert(full_config, alert_title, msg, symbol=symbol)

    _, after = await _limit_reduce_with_maker_retry(
        exchange, symbol, side, fresh, qty, reason, conf,
        int(pos_state.get("position_version", 0)), pos_state)
    pos_state["contracts"] = after
    if tier == "T2":
        pos_state["t2_done"] = True
    else:
        pos_state["t1_done"] = True
    pos_state["last_program_reduce_ts"] = int(time.time())
    _mark_risk_action_done(symbol, side, tier)
    state = _load_state(); state[key] = pos_state; _save_state(state)
    return after


async def watch_symbol_position(exchange, symbol, side):
    last_heartbeat_time = 0
    await asyncio.sleep(random.uniform(0.1, 2.0))
    logger.info(f"[{symbol}/{side}] 👁️ 高级风控守护协程已就位")

    while True:
        try:
            full_config = load_protection_config()
            conf = full_config.get("position_protection", {})
            if not conf.get("enabled", True):
                await asyncio.sleep(5)
                continue

            timeframe = str(conf.get("timeframe", "2h"))

            pos = RUNTIME.global_positions_map.get((symbol, side))
            if not pos or _position_size(pos) <= 0:
                key0 = _state_key(symbol, side)
                state = _load_state()
                state.pop(key0, None)
                RUNTIME.runtime_position_states.pop(_state_key(symbol, side), None)
                _save_state(state)
                await _cancel_program_stops_for_flat(exchange, symbol, side, conf)
                await asyncio.sleep(5)
                continue

            side = _position_side(pos)
            contracts = _position_size(pos)
            entry_price = _f(pos.get("entryPrice"), 0.0)
            key = _state_key(symbol, side)

            now_time = time.time()
            # 心跳降噪：默认 15 分钟一条（44 个仓位每分钟一条会把日志抽屉刷满）
            if now_time - last_heartbeat_time > float(conf.get("patrol_log_interval_sec", 900.0)):
                logger.info(f"[{symbol}] 🛡️ 巡检中... 当前{ '做多' if side=='long' else '做空' }仓位: {contracts} | 开仓均价: {entry_price}")
                last_heartbeat_time = now_time

            state = _load_state()

            # 主控已经确认这是“平仓后重新出现”的仓位：直接删除旧风险周期。
            # 这一步优先于 entryPrice/openTime 判断，解决“同价重开”无法识别的问题。
            force_new_cycle = key in RUNTIME.force_new_cycle_keys
            if force_new_cycle:
                state.pop(key, None)
                RUNTIME.runtime_position_states.pop(key, None)
                logger.warning(f"[{symbol}/{side}] ♻️ 新开仓生命周期重置：清除旧 T1/T2/T3、TP、抄底及保护STOP状态。")
                await _cancel_program_stops_for_flat(exchange, symbol, side, conf)
                try:
                    await _cancel_bot_reduce_orders(exchange, symbol, side, conf, reason="新风险周期启动")
                except Exception as cleanup_exc:
                    logger.warning(f"[{symbol}/{side}] 新周期旧减仓单清理异常: {cleanup_exc}")

            # 如果状态文件暂时不可写，优先使用本进程的新周期状态，绝不读回旧周期；
            # 但仍然调用 reconcile，以便正常处理真实加仓/减仓和仓位版本变化。
            if key in RUNTIME.runtime_position_states and not force_new_cycle:
                state[key] = RUNTIME.runtime_position_states[key]

            pos_state, changed = _reconcile_position_state(state, key, symbol, side, contracts, timeframe, position=pos, conf=conf)
            RUNTIME.runtime_position_states[key] = pos_state

            if changed or force_new_cycle:
                _save_state(state)
                # 即使磁盘写入失败，也不再重复“初始化新周期”；内存状态由 runtime_position_states 接管。
                RUNTIME.force_new_cycle_keys.discard(key)

            fetch_t3_lookback = int(conf.get("t3_structure_lookback", 83))
            entry_lookback = int(conf.get("entry_classification_lookback_bars", 500))
            limit = max(fetch_t3_lookback + 25, 120, entry_lookback)
            ohlcv_rows = await _fetch_ohlcv(exchange, symbol, timeframe, limit, conf, priority="LOW", force=False)

            async with RUNTIME.action_lock(symbol, side):
                snap = await _market_snapshot(exchange, symbol, conf, priority="NORMAL")
                current_price = snap["mark"]

                # TP 安全校验：如果持仓入口价格已变化，或旧状态中的 TP 阶梯与当前方向不一致，
                # 必须先清空旧 TP，重新按当前风险周期初始化；绝不允许旧 TP 直接触发平仓。
                tp_entry_state = _f(pos_state.get("tp_entry_price"), 0.0)
                tp1_state = _f(pos_state.get("tp1_price"), 0.0)
                tp2_state = _f(pos_state.get("tp2_price"), 0.0)
                tp3_state = _f(pos_state.get("tp3_price"), 0.0)
                tp_state_valid = False
                if tp_entry_state > 0 and tp1_state > 0 and tp2_state > 0 and tp3_state > 0 and entry_price > 0:
                    same_entry = abs(tp_entry_state - entry_price) / max(entry_price, 1e-12) <= 0.001
                    if side == "long":
                        tp_state_valid = same_entry and (entry_price < tp1_state < tp2_state < tp3_state)
                    else:
                        tp_state_valid = same_entry and (entry_price > tp1_state > tp2_state > tp3_state)
                if pos_state.get("tp_entry_price") and not tp_state_valid:
                    logger.warning(
                        f"[{symbol}] 🧹 检测到旧/异常TP状态，已清除并禁止本轮误触发 | "
                        f"方向:{side} | 当前开仓价:{entry_price:.8f} | "
                        f"旧TP1:{tp1_state:.8f} TP2:{tp2_state:.8f} 躺平:{tp3_state:.8f}"
                    )
                    pos_state.update({
                        "tp_entry_price": None, "tp_initial_stop": None, "tp_risk_distance": None,
                        "tp1_price": None, "tp2_price": None, "tp3_price": None,
                        "tp1_triggered": False, "tp2_triggered": False, "tp3_triggered": False,
                        "tp_protected_stop": None, "tp_protection_stage": 0,
                    })
                    state[key] = pos_state
                    _save_state(state)

                # 双轨治理：守护端接管开仓端遗留的 SL/TP/TS 条件单。
                # 幂等：每风险周期只执行一次（新周期 pop 状态后标志自动重置）。
                if bool(conf.get("take_over_external_stops", False)) \
                        and not pos_state.get("external_stops_taken_over"):
                    try:
                        await _take_over_external_stops(exchange, symbol, side, pos, conf)
                        pos_state["external_stops_taken_over"] = True
                        state[key] = pos_state
                        _save_state(state)
                    except Exception as take_over_exc:
                        logger.warning(f"[{symbol}] 接管外部SL/TP/TS失败，下轮重试: {take_over_exc}")

                # 先计算/初始化本风险周期的固定 TP，再维护交易所 STOP，
                # 这样 TP1/TP2 完成后的利润保护 STOP 能在同一轮进入交易所。
                if bool(conf.get("take_profit_enabled", True)):
                    try:
                        strategy_for_tp = _strategy_levels_from_rows(ohlcv_rows, conf)
                        tp_stop, _ = _calculate_dynamic_protection_stop(
                            exchange, symbol, side, current_price, strategy_for_tp, conf
                        )
                        if _initialize_take_profit_levels(pos_state, side, entry_price, tp_stop, conf):
                            state[key] = pos_state
                            _save_state(state)
                    except Exception as tp_init_exc:
                        logger.warning(f"[{symbol}] 止盈位初始化失败，本轮继续使用止损保护: {tp_init_exc}")

                try:
                    await _ensure_disaster_stop(exchange, symbol, side, pos, current_price, conf, ohlcv_rows=ohlcv_rows, force_replace=changed, pos_state=pos_state)
                except Exception as e:
                    logger.error(f"[{symbol}] 交易所兜底止损异常，不影响内部风控继续运行: {e}")

                # 每一次巡检都重新读取交易所当前 STOP，确保日志展示的是“实际挂单价格”，
                # 而不是仅依赖 last_stop_price。TP1/TP2/躺平 也在同一条日志完整输出。
                actual_stop = None
                strategy_stop_display = None
                try:
                    strategy_for_log = _strategy_levels_from_rows(ohlcv_rows, conf)
                    strategy_stop_display, _ = _calculate_dynamic_protection_stop(
                        exchange, symbol, side, current_price, strategy_for_log, conf
                    )
                    strategy_stop_display = float(strategy_stop_display)
                except Exception:
                    strategy_stop_display = None
                try:
                    current_stops = await _find_stop_orders(exchange, symbol, side, pos, current_price, conf, force=True)
                    if current_stops:
                        actual_stop = _algo_trigger(current_stops[0])
                except Exception as stop_read_exc:
                    logger.warning(f"[{symbol}] 读取交易所实际STOP失败: {stop_read_exc}")

                if actual_stop is not None:
                    pos_state["last_stop_price"] = float(actual_stop)
                    state[key] = pos_state
                    _save_state(state)

                tp_stage = int(pos_state.get("tp_protection_stage", 0) or 0)
                tp_keep = _tp3_remaining_ratio(conf)
                tp3_action = "全平" if tp_keep <= 0 else f"保留{tp_keep:.0%}"
                _status_log(
                    "tp_status", symbol, side, "INFO",
                    f"[{symbol}] 🛡️🎯 止盈止损状态 | 方向:{'多' if side=='long' else '空'} | "
                    f"当前价:{current_price:.8f} | 开仓价:{entry_price:.8f} | 仓位:{contracts:.8f} | "
                    f"STOP(交易所实际):{_f(actual_stop, pos_state.get('last_stop_price') or 0):.8f} | "
                    f"策略止损:{_f(strategy_stop_display, pos_state.get('last_stop_price') or 0):.8f} | "
                    f"TP1:{_f(pos_state.get('tp1_price'), 0):.8f} → {float(conf.get('tp1_ratio', 0.20)):.0%} [{'已完成' if pos_state.get('tp1_triggered') else '待触发'}] | "
                    f"TP2:{_f(pos_state.get('tp2_price'), 0):.8f} → {float(conf.get('tp2_ratio', 0.30)):.0%} [{'已完成' if pos_state.get('tp2_triggered') else '待触发'}] | "
                    f"躺平:{_f(pos_state.get('tp3_price'), 0):.8f} → {tp3_action} [{'已完成' if pos_state.get('tp3_triggered') else '待触发'}] | "
                    f"保护阶段:TP{tp_stage} | TP保护STOP:{_f(pos_state.get('tp_protected_stop'), 0):.8f} | "
                    f"R:{_f(pos_state.get('tp_risk_distance'), 0):.8f} | 周期:{pos_state.get('risk_cycle_id')}",
                    float(conf.get("status_log_interval_sec", 900.0)),
                )

            # ---------------- 分批止盈：1R/2R/3R ----------------
            try:
                if bool(conf.get("take_profit_enabled", True)) and pos_state.get("tp_risk_distance"):
                    tp_level = _take_profit_hit(pos_state, side, current_price)
                    if tp_level:
                        async with RUNTIME.action_lock(symbol, side):
                            state = _load_state()
                            pos_state = state.get(key, pos_state)
                            fresh = await _position_fresh(exchange, symbol, side, conf, priority="HIGH")
                            if not fresh:
                                continue
                            current_contracts = _position_size(fresh)
                            try:
                                tp_snap = await _market_snapshot(exchange, symbol, conf, priority="HIGH")
                                current_price = float(tp_snap["mark"])
                            except Exception:
                                pass
                            if current_contracts <= 0:
                                state.pop(key, None); _save_state(state); return

                            # 防止程序重启/网络抖动后遗留多张机器人减仓单。
                            await _cancel_bot_reduce_orders(exchange, symbol, side, conf, reason=f"TP{tp_level}前")

                            # 重新按最新价格确认，防止等待锁期间价格已经回落。
                            tp_level = _take_profit_hit(pos_state, side, current_price)
                            if tp_level:
                                await _execute_tp_reduce(
                                    exchange, symbol, side, pos_state, fresh, current_price,
                                    current_contracts, tp_level, conf, full_config)
                                if _f(pos_state.get("contracts"), current_contracts) <= 1e-10:
                                    return
            except Exception as tp_exc:
                logger.error(f"[{symbol}] 分批止盈逻辑异常: {tp_exc}")

            # ---------------- 紧急止损 1：放量加速 / 黑天鹅 (市价 Taker) ----------------
            try:
                emergency, details = await _emergency_signal(exchange, symbol, side, conf)

                if details:
                    # 常规状态行属于每轮噪音：正常走 DEBUG 且节流，真正触发才升到 INFO 立即打
                    _status_log(
                        "blackswan", symbol, side,
                        "INFO" if emergency else "DEBUG",
                        f"[{symbol}] 🚨 黑天鹅监控 | 方向:{side} | "
                        f"当前波动:{details.get('move',0):.4f} | "
                        f"触发阈值:{details.get('threshold',0):.4f} | "
                        f"成交量异常:{details.get('volume_crash',False)} | "
                        f"结构确认:{details.get('structure',False)} | "
                        f"状态:{'触发' if emergency else '正常'}",
                        0.0 if emergency else float(conf.get("status_log_interval_sec", 900.0)),
                    )

                if details and details.get("volume_crash"):
                    logger.warning(f"[{symbol}] ⚠️ 侦测到局部异常放量！伴随极速反向位移！")
                elif details and details["move"] >= details["threshold"] * 0.8:
                    logger.warning(f"[{symbol}] 🚨 行情波动逼近熔断阈值！当前波动: {details['move']:.2f}")

                if emergency:
                    ok, _ = await _two_source_price_ok(exchange, symbol, details["ws_price"], side, conf)
                    if ok:
                        async with RUNTIME.action_lock(symbol, side):
                            state = _load_state(); pos_state = state.get(key, pos_state)
                            fresh = await _position_fresh(exchange, symbol, side, conf, priority="HIGH")
                            if fresh:
                                msg = f"[{symbol}] 🚨 触发 {details['reason']}！执行紧急市价全平！"
                                logger.error(msg); send_alert(full_config, f"风控警告: {details['reason']}", msg, symbol=symbol)
                                success, _ = await _full_exit_with_revalidation(exchange, symbol, side, fresh, f"{details['reason']} 紧急市价全平", conf, pos_state)
                                if success:
                                    state.pop(key, None); _save_state(state)
                                    return
            except Exception as e:
                logger.error(f"[{symbol}] 紧急信号检查异常: {e}")

            # ---------------- 紧急止损 2：抄底 3ATR 专属保护线跌破 (市价 Taker) ----------------
            try:
                if pos_state.get("t3_waived") and pos_state.get("bottom_fish_sl"):
                    realtime_bf_sl = float(pos_state["bottom_fish_sl"])
                    if (side == "long" and current_price <= realtime_bf_sl) or \
                       (side == "short" and current_price >= realtime_bf_sl):
                        async with RUNTIME.action_lock(symbol, side):
                            fresh = await _position_fresh(exchange, symbol, side, conf, priority="HIGH")
                            if fresh:
                                msg = f"[{symbol}] 💔 跌破 3ATR 专属抄底保护线，无条件市价全平！"
                                logger.error(msg); send_alert(full_config, "风控警告: 实时抄底止损", msg, symbol=symbol)
                                success, _ = await _full_exit_with_revalidation(exchange, symbol, side, fresh, "抄底实时市价全平", conf, pos_state)
                                if success:
                                    state = _load_state()
                                    state.pop(key, None)
                                    _save_state(state)
                                    return
            except Exception as e:
                logger.error(f"[{symbol}] 实时抄底止损检查异常: {e}")

            # ---------------- V3：EMA趋势过滤 + ATR + 结构破位分级风控 ----------------
            try:
                strategy = _strategy_levels_from_rows(ohlcv_rows, conf)
                ema_fast = strategy["ema_fast"]
                ema_slow = strategy["ema_slow"]
                atr = strategy["atr"]
                closed_ts = strategy["closed_ts"]
                closed_price = strategy["last_close"]
                trend = strategy["trend"]

                t1_lookback = int(conf.get("t1_structure_lookback", 7))
                t2_lookback = int(conf.get("t2_structure_lookback", 26))
                t3_lookback = int(conf.get("t3_structure_lookback", 83))
                closed_df = strategy["df"]
                if len(closed_df) < max(t3_lookback + 1, 3):
                    raise RuntimeError("结构K线不足")

                # 结构位只看“触发K线之前”的已收盘K线，避免结构位包含当前收盘K线自身，
                # 否则 long 的 close <= low-buffer、short 的 close >= high+buffer 在数学上几乎不可能成立。
                prior_df = closed_df.iloc[:-1]
                t1_low = float(prior_df.iloc[-t1_lookback:]["low"].min())
                t1_high = float(prior_df.iloc[-t1_lookback:]["high"].max())
                t2_low = float(prior_df.iloc[-t2_lookback:]["low"].min())
                t2_high = float(prior_df.iloc[-t2_lookback:]["high"].max())
                t3_low = float(prior_df.iloc[-t3_lookback:]["low"].min())
                t3_high = float(prior_df.iloc[-t3_lookback:]["high"].max())
                buffer = atr * float(conf.get("structure_buffer_atr", 0.50))
                t1_atr_buffer = atr * float(conf.get("t1_atr_confirmation", 0.50))
                atr_confirm = atr * float(conf.get("t2_atr_confirmation", 0.50))

                # T1：实时价格触发“小结构 + 独立 ATR 缓冲”，不再等待K线收盘。
                # T2/T3 继续保持原来的“收盘价确认”逻辑。
                if side == "long":
                    t1_level = t1_low - t1_atr_buffer
                    t1_hit = (current_price <= t1_level
                              and not pos_state.get("t1_done")
                              and not pos_state.get("t1_triggered"))
                    t2_hit = (closed_price <= t2_low - max(buffer, atr_confirm) and trend in ("bear", "neutral")
                              and not pos_state.get("t2_done") and not pos_state.get("t2_triggered"))
                    t3_hit = (closed_price <= t3_low - buffer and ema_fast < ema_slow
                              and not pos_state.get("t3_triggered") and not pos_state.get("t3_waived"))
                    strategy_stop = float(strategy["long_structure"])
                else:
                    t1_level = t1_high + t1_atr_buffer
                    t1_hit = (current_price >= t1_level
                              and not pos_state.get("t1_done")
                              and not pos_state.get("t1_triggered"))
                    t2_hit = (closed_price >= t2_high + max(buffer, atr_confirm) and trend in ("bull", "neutral")
                              and not pos_state.get("t2_done") and not pos_state.get("t2_triggered"))
                    t3_hit = (closed_price >= t3_high + buffer and ema_fast > ema_slow
                              and not pos_state.get("t3_triggered") and not pos_state.get("t3_waived"))
                    strategy_stop = float(strategy["short_structure"])

                # 新仓保护：T1/T2/T3 只允许检查“开仓之后才形成/收盘”的K线。
                # 例如上一仓已在上一根K线跌破T1，用户数小时后重新开多，不能因为历史K线仍是破位状态
                # 就在新仓刚开完时立即再减20%。entry_time_ms 不可靠时已由 reconcile 回退到首次发现时间。
                entry_time_ms = int(pos_state.get("entry_time_ms") or 0)
                candle_is_after_entry = (entry_time_ms <= 0) or (int(closed_ts) >= entry_time_ms)

                # T1 使用实时价格，但防止“旧仓已破位 -> 几小时后重新开仓”立即继承旧破位。
                # 如果新仓开仓价本身已经在 T1 线外，先不触发；只有价格重新回到线内后再次突破才触发。
                t1_armed = bool(pos_state.get("t1_realtime_armed", False))
                entry_price_for_t1 = _f(pos_state.get("risk_entry_price"), 0.0)
                if entry_price_for_t1 <= 0:
                    entry_price_for_t1 = _f(pos_state.get("last_position_entry_price"), 0.0)
                if entry_price_for_t1 > 0 and not pos_state.get("t1_realtime_armed_initialized", False):
                    if side == "long":
                        t1_armed = entry_price_for_t1 > t1_level
                    else:
                        t1_armed = entry_price_for_t1 < t1_level
                    pos_state["t1_realtime_armed"] = t1_armed
                    pos_state["t1_realtime_armed_initialized"] = True

                # 已经重新回到结构线内，重新武装 T1；随后实时再次突破即可触发。
                if side == "long" and current_price > t1_level:
                    t1_armed = True
                elif side == "short" and current_price < t1_level:
                    t1_armed = True
                pos_state["t1_realtime_armed"] = t1_armed

                t1_hit = t1_hit and t1_armed
                # T2/T3 仍必须等待开仓后的已收盘K线。
                if not candle_is_after_entry:
                    t2_hit = t3_hit = False

                # T1 为实时触发；T2/T3 只能在新收盘K线出现时触发。
                # 触发锁先落盘，再发通知/下单，彻底杜绝同一风险周期重复20%推送。
                new_closed_candle = closed_ts > int(pos_state.get("last_checked_time", 0))
                t2_hit = t2_hit and new_closed_candle
                t3_hit = t3_hit and new_closed_candle
                if new_closed_candle or t1_hit:
                    logger.info(
                        f"[{symbol}] 📊 V3止盈/止损监控 | 方向:{side} | 收盘:{closed_price:.4f} | 当前:{current_price:.4f} | "
                        f"EMA26:{ema_fast:.4f} EMA83:{ema_slow:.4f} 趋势:{trend} ATR14:{atr:.4f} | "
                        f"T1结构位:{t1_low if side=='long' else t1_high:.4f} | T1触发线:{t1_level:.4f} | T1实时状态:{'已破' if t1_hit else ('待触发' if t1_armed else '未武装')} | "
                        f"T2减仓位:{t2_low if side=='long' else t2_high:.4f} (30%) | "
                        f"T3全平结构位:{t3_low if side=='long' else t3_high:.4f} | "
                        f"当前策略保护止损:{strategy_stop:.4f} | 新仓K线保护:{'已生效' if candle_is_after_entry else '等待开仓后新K线'} | "
                        f"TP保护阶段:{int(pos_state.get('tp_protection_stage',0))} | TP保护止损:{_f(pos_state.get('tp_protected_stop'),0):.4f} | "
                        f"TP1:{_f(pos_state.get('tp1_price'),0):.4f} TP2:{_f(pos_state.get('tp2_price'),0):.4f} 躺平:{_f(pos_state.get('tp3_price'),0):.4f}({_tp3_action_text(conf)}) | "
                        f"周期:{pos_state.get('risk_cycle_id')}"
                    )

                    if new_closed_candle:
                        pos_state["last_checked_time"] = closed_ts
                        pos_state["last_closed_candle_ts"] = closed_ts
                    pos_state["last_risk_check_time"] = int(time.time())
                    pos_state["risk_state"] = {
                        "t1": "triggered" if t1_hit else ("done" if pos_state.get("t1_done") else "normal"),
                        "t2": "triggered" if t2_hit else ("done" if pos_state.get("t2_done") else "normal"),
                        "t3": "triggered" if t3_hit else "normal",
                        "black_swan": "normal",
                        "atr_protection": "active",
                        "ema_fast": ema_fast, "ema_slow": ema_slow, "trend": trend,
                        "atr": atr, "strategy_stop": strategy_stop, "last_close": closed_price,
                    }
                    state[key] = pos_state
                    _save_state(state)

                    async with RUNTIME.action_lock(symbol, side):
                        fresh = await _position_fresh(exchange, symbol, side, conf, priority="HIGH")
                        if not fresh:
                            continue
                        current_contracts = _position_size(fresh)

                        # T3：EMA趋势反转 + 大结构失守 -> 全平
                        if t3_hit:
                            action_key = (symbol, side, str(pos_state.get("risk_cycle_id")), "T3")
                            if action_key in RUNTIME.risk_action_latches:
                                logger.warning(f"[{symbol}/{side}] 🛑 T3本风险周期已执行/已锁定，跳过重复动作。")
                                continue
                            RUNTIME.risk_action_latches.add(action_key)
                            await _cancel_bot_reduce_orders(exchange, symbol, side, conf, reason="T3全平前")
                            pos_state["t3_triggered"] = True
                            state[key] = pos_state
                            _save_state(state)
                            msg = (f"[{symbol}] 🚨 T3结构趋势失效，全平！周期:{pos_state.get('risk_cycle_id')} | "
                                   f"收盘:{closed_price:.4f} EMA26:{ema_fast:.4f} EMA83:{ema_slow:.4f} ATR:{atr:.4f}")
                            logger.error(msg)
                            send_alert(full_config, "风控警告: T3 趋势失效", msg, symbol=symbol)
                            success, _ = await _full_exit_with_revalidation(exchange, symbol, side, fresh, "T3 EMA+结构全平", conf, pos_state)
                            if success:
                                state.pop(key, None); _save_state(state); return

                        # T2：中结构失守 + ATR确认 + 趋势过滤 -> 30%
                        elif t2_hit:
                            qty = min(current_contracts, (_f(pos_state.get("base_contracts"), current_contracts)) * float(conf.get("tier2_ratio", 0.30)))
                            msg = (f"[{symbol}] 📉 T2结构破位，执行30%减仓！周期:{pos_state.get('risk_cycle_id')} | "
                                   f"收盘:{closed_price:.4f} 结构:{t2_low if side=='long' else t2_high:.4f} "
                                   f"ATR:{atr:.4f} EMA26/83:{ema_fast:.4f}/{ema_slow:.4f} 当前:{current_price:.4f}")
                            await _execute_tiered_reduce(
                                exchange, symbol, side, pos_state, fresh, current_contracts,
                                "T2", qty, msg, "风控提示: T2 减仓", "T2结构减仓", conf, full_config)

                        # T1：小结构破位 -> 20%，不再用MA直接触发
                        elif t1_hit:
                            qty = min(current_contracts, (_f(pos_state.get("base_contracts"), current_contracts)) * float(conf.get("tier1_ratio", 0.20)))
                            msg = (f"[{symbol}] 📉 T1结构破位，执行20%减仓！周期:{pos_state.get('risk_cycle_id')} | "
                                   f"当前:{current_price:.4f} 结构:{t1_low if side=='long' else t1_high:.4f} 触发线:{t1_level:.4f} "
                                   f"ATR:{atr:.4f} EMA26/83:{ema_fast:.4f}/{ema_slow:.4f}")
                            await _execute_tiered_reduce(
                                exchange, symbol, side, pos_state, fresh, current_contracts,
                                "T1", qty, msg, "风控提示: T1 减仓", "T1结构减仓", conf, full_config)

            except Exception as exc:
                logger.error(f"[{symbol}] EMA/ATR/结构破位逻辑异常: {exc}")

            await asyncio.sleep(5.0 + random.uniform(0.0, 1.0))

        except asyncio.CancelledError:
            raise
        except CircuitBreakerException as c_exc:
            # 明确感知限流状态并进行单行提示，不吞日志也不刷屏 Traceback
            if time.time() - RUNTIME.last_circuit_notice > 10.0:
                logger.warning(f"⏳ [限流冷却中] {c_exc}")
                RUNTIME.last_circuit_notice = time.time()
            await asyncio.sleep(5.0)
        except Exception as exc:
            logger.error(f"[{symbol}] 风控守护未知异常: {exc}")
            await asyncio.sleep(5.0)


# ---------------------------------------------------------------------------
# Main coordinator
# ---------------------------------------------------------------------------

async def protect_positions_main(exchange, config=None):
    full_config = load_protection_config()
    conf = full_config.get("position_protection", {})
    if not conf.get("enabled", True):
        logger.info("仓位保护已禁用")
        return

    _algo_methods(exchange)
    logger.info("🛡️ 风控中枢启动：集中式批量巡检 + 限流显式警报机制已就位")
    await cleanup_orphaned_state_and_orders(exchange, conf)

    tasks = {}
    last_cleanup = 0.0
    last_heartbeat_time = 0

    while True:
        try:
            full_config = load_protection_config()
            conf = full_config.get("position_protection", {})

            # 支持运行中热关闭：WebApp 的 supervisor 会在下一轮把任务取消
            if not conf.get("enabled", True):
                logger.info("🛡️ 仓位保护配置已关闭，引擎退出")
                return

            # 1. 集中批量拉取一次所有仓位
            positions = await _fetch_positions(exchange, conf, symbols=None, priority="NORMAL", force=True)

            # 2. 全局批量更新全市场 Tickers（一次请求解决所有币种 Ticker 需求）
            try:
                tickers = await _rest(exchange, "fetch_tickers", priority="LOW", conf=conf)
                now_ts = time.monotonic()
                for sym, tick_data in tickers.items():
                    RUNTIME.ticker_cache[sym] = (now_ts, tick_data)
            except Exception as e:
                logger.warning(f"批量获取 Tickers 异常 (降级为单币拉取): {e}")

            # 3. 更新全局仓位映射
            pos_map = {}
            active = set()
            for pos in positions:
                side = _position_side(pos)
                if _position_size(pos) <= 0 or side not in ("long", "short"):
                    continue
                symbol = pos.get("symbol")
                if not symbol:
                    continue
                key = (symbol, side)
                pos_map[key] = pos
                active.add(key)

            RUNTIME.global_positions_map = pos_map

            # 3.5 仓位生命周期：只要主控观察到某方向从“有仓”变成“无仓”，
            # 就立即标记下一次重新出现为全新风险周期。这样手动平仓后再开仓，
            # 即使旧 state 文件还没来得及清理，也绝不会继承 T1/T2/TP/抄底状态。
            # 防抖：部分交易所在挂reduce单/资金费结算时会短暂漏报仓位，
            # 必须连续消失超过 flat_confirm_sec 才认定真平仓，否则会“闪断 -> 换周期 -> T1立刻再减”。
            disappeared = RUNTIME.previous_active_keys - active
            keep_previous = set()
            for old_key in disappeared:
                confirm_sec = _f(conf.get("flat_confirm_sec"), 0.0) or 0.0
                first_seen = RUNTIME.disappeared_since.setdefault(old_key, time.time())
                if confirm_sec > 0 and (time.time() - first_seen) < confirm_sec:
                    logger.warning(
                        f"[{old_key[0]}/{old_key[1]}] 👻 仓位短暂消失 {time.time() - first_seen:.0f}s"
                        f"（<{confirm_sec:.0f}s），暂不重建风险周期，防接口抖动误判。")
                    keep_previous.add(old_key)
                    continue
                RUNTIME.disappeared_since.pop(old_key, None)
                RUNTIME.force_new_cycle_keys.add(old_key)
                # 旧周期的一次性动作闩锁也必须失效。
                RUNTIME.risk_action_latches = {
                    x for x in RUNTIME.risk_action_latches
                    if not (isinstance(x, tuple) and len(x) >= 2 and x[:2] == old_key)
                }
                old_symbol, old_side = old_key
                try:
                    await _cancel_bot_reduce_orders(
                        exchange, old_symbol, old_side, conf, reason="仓位已手动平仓，清理旧减仓单"
                    )
                    await _cancel_program_stops_for_flat(exchange, old_symbol, old_side, conf)
                    RUNTIME.runtime_position_states.pop(_state_key(old_symbol, old_side), None)
                    old_state = _load_state()
                    old_state.pop(_state_key(old_symbol, old_side), None)
                    _save_state(old_state)
                except Exception as lifecycle_exc:
                    logger.warning(f"[{old_symbol}/{old_side}] 平仓后生命周期清理异常: {lifecycle_exc}")
                logger.info(f"[{old_symbol}/{old_side}] 🧹 检测到仓位已消失：下一次重新开仓强制建立全新风险周期。")

            # 防抖期内重新出现的方向不再保留“消失中”标记
            for k in list(RUNTIME.disappeared_since):
                if k in active:
                    RUNTIME.disappeared_since.pop(k, None)
            RUNTIME.previous_active_keys = set(active) | keep_previous

            # 4. 按 symbol + side 调度，完整支持 Binance Hedge Mode 同币双向持仓
            for symbol, side in active:
                task_key = (symbol, side)
                task = tasks.get(task_key)
                if task is None or task.done():
                    tasks[task_key] = asyncio.create_task(
                        watch_symbol_position(exchange, symbol, side),
                        name=f"position-protect:{symbol}:{side}"
                    )

            if time.time() - last_heartbeat_time >= 60:
                if active:
                    logger.info(f"💓 [风控中枢心跳] 正在守护 {len(active)} 个活跃仓位方向: {list(active)}")
                else:
                    logger.debug("💓 [风控中枢心跳] 当前账户 0 持仓，等待入场信号...")
                last_heartbeat_time = time.time()

            # 5. 清理无效任务：仓位消失立即取消守护，避免长期空转
            for task_key, task in list(tasks.items()):
                if task_key not in active:
                    if not task.done():
                        task.cancel()
                    tasks.pop(task_key, None)

            if time.time() - last_cleanup >= 3600:
                await cleanup_orphaned_state_and_orders(exchange, conf)
                last_cleanup = time.time()

            # 6. 自适应休眠（持仓多时自动平滑平摊请求）
            dynamic_sync_sec = max(5.0, len(active) * 0.15)
            await asyncio.sleep(dynamic_sync_sec)

        except asyncio.CancelledError:
            raise
        except CircuitBreakerException as c_exc:
            logger.warning(f"⏳ [风控主控] 系统处于 API 限流冷却状态，休眠 10 秒后重试: {c_exc}")
            await asyncio.sleep(10.0)
        except Exception as exc:
            logger.error(f"风控主控循环异常: {exc}", exc_info=True)
            await asyncio.sleep(10.0)
