"""应急减仓与交易所 STOP 管理（T08 自 engine.py 拆出）。

静态审计白名单落点：本模块是 protection 包内唯一允许下发市价减仓单的文件，
且全部为 reduceOnly 平仓方向的减仓/止损调用，永远不做开仓。
"""

import asyncio
import time
import uuid

from loguru import logger

from .algo_compat import (
    cancel_algo_order,
    create_close_position_stop,
    fetch_open_algo_orders,
    supports_algo,
)
from .config import _f
from .market_data import (
    _atr_from_rows,
    _closed_atr,
    _fetch_ticker,
    _position_fresh,
)
from .state import (
    RUNTIME,
    _load_state,
    _position_size,
    _raw_position_side,
    _rest,
    _save_state,
    _state_key,
    _status_log,
)
from .stops import (
    _calculate_disaster_stop,
    _calculate_dynamic_protection_stop,
    _continuous_trailing_stop,
    _strategy_levels_from_rows,
)
from .take_profit import _take_profit_protection_stop

CLIENT_ALGO_PREFIX = "PM_WS_SL_"


# ---------------------------------------------------------------------------
# Exchange algo orders & Market Functions
# ---------------------------------------------------------------------------

def _make_client_algo_id(symbol, side):
    compact = symbol.replace("/", "").replace(":", "")
    suffix = "L" if side == "long" else "S"
    return f"{CLIENT_ALGO_PREFIX}{compact}_{suffix}_{uuid.uuid4().hex[:8]}"[:36]


def _algo_status(order):
    return str(order.get("algoStatus") or order.get("status") or "").upper()


def _algo_trigger(order):
    return _f(order.get("triggerPrice") or order.get("stopPrice"))


def _is_program_stop(order, side, position_side, current_price=None):
    if not isinstance(order, dict):
        return False

    client_id = str(order.get("clientAlgoId") or order.get("clientOrderId") or "")
    if not client_id.startswith(CLIENT_ALGO_PREFIX):
        return False

    type_upper = str(order.get("orderType") or order.get("type") or "").upper()
    if type_upper != "STOP_MARKET":
        return False

    status = _algo_status(order)
    if status and status not in ("NEW", "TRIGGER_PENDING", "UNTRIGGERED", "PARTIALLY_FILLED", ""):
        return False

    expected = "SELL" if side == "long" else "BUY"
    if str(order.get("side") or "").upper() != expected:
        return False

    return True


def _algo_methods(exchange):
    """检查条件单接口可用性。

    新版 ccxt 有 Algo Order 接口时直接使用；旧版没有则退回标准条件单
    （见 algo_compat.py），不再抛异常导致整个引擎无法启动。
    """
    if not supports_algo(exchange):
        logger.warning("⚠️ 当前 CCXT 缺少 Binance Algo Order 接口，回退旧版条件单（功能等价）")


async def _get_open_algo_orders(exchange, symbol, conf, force=False):
    ttl = float(conf.get("orders_cache_ttl_sec", 10))
    now = time.monotonic()
    cached = RUNTIME.orders_cache.get(symbol)
    if not force and cached and now - cached[0] < ttl:
        return cached[1]

    orders = await fetch_open_algo_orders(exchange, symbol, conf, RUNTIME.rest)
    RUNTIME.orders_cache[symbol] = (time.monotonic(), orders)
    return orders


async def _find_stop_orders(exchange, symbol, side, position, current_price, conf, force=False):
    raw_ps = _raw_position_side(position)
    orders = await _get_open_algo_orders(exchange, symbol, conf, force=force)
    return [o for o in orders if _is_program_stop(o, side, raw_ps, current_price)]


async def _cancel_algo(exchange, symbol, algo_id, conf):
    result = await cancel_algo_order(exchange, symbol, algo_id, conf, RUNTIME.rest)
    RUNTIME.orders_cache.pop(symbol, None)
    return result


async def _cancel_stop_orders(exchange, symbol, stops, conf):
    for order in stops:
        algo_id = order.get("algoId") or order.get("id")
        if not algo_id:
            continue
        try:
            await _cancel_algo(exchange, symbol, algo_id, conf)
        except Exception:
            pass


async def _cancel_program_stops_for_flat(exchange, symbol, side, conf):
    """仓位已经归零时，清理本机器人旧的 STOP，防止重新开仓后继承旧兜底单。"""
    try:
        orders = await _get_open_algo_orders(exchange, symbol, conf, force=True)
        stops = [o for o in orders if _is_program_stop(o, side, "BOTH")]
        if stops:
            await _cancel_stop_orders(exchange, symbol, stops, conf)
            logger.warning(f"[{symbol}/{side}] 🧹 仓位归零，清理旧保护STOP {len(stops)} 张。")
    except Exception as exc:
        logger.warning(f"[{symbol}/{side}] 清理旧保护STOP失败: {exc}")


async def _create_full_close_stop(exchange, symbol, position, side, stop_price, conf):
    trigger_str = exchange.price_to_precision(symbol, stop_price)
    result = await create_close_position_stop(
        exchange, symbol, side, _raw_position_side(position), stop_price,
        _make_client_algo_id(symbol, side), conf, RUNTIME.rest)
    RUNTIME.orders_cache.pop(symbol, None)

    logger.success(f"[{symbol}] 🎯 成功下达 灾难STOP兜底单，触发价: {trigger_str}")
    return result


# ---------------------------------------------------------------------------
# Execution Strategy
# ---------------------------------------------------------------------------

async def _market_reduce_and_confirm(exchange, symbol, side, position, requested_qty, reason, conf, expected_version, pos_state):
    """紧急止损：市价吃单 (Taker)"""
    raw_ps = _raw_position_side(position)
    before = _position_size(position)
    if int(pos_state.get("position_version", 0)) != expected_version:
        raise RuntimeError("仓位版本已变化，拒绝按旧快照下单")

    qty = _f(exchange.amount_to_precision(symbol, min(before, requested_qty)), 0.0)
    if not qty or qty <= 0:
        raise RuntimeError(f"{reason}: 下单数量无效")

    params = {"reduceOnly": True}
    if raw_ps != "BOTH":
        params["positionSide"] = raw_ps

    order = await _rest(exchange, "create_market_order", symbol, "sell" if side == "long" else "buy", qty,
                        priority="HIGH", conf=conf, params=params)
    await asyncio.sleep(0.5)
    fresh = await _position_fresh(exchange, symbol, side, conf, priority="HIGH")
    after = _position_size(fresh)

    logger.success(f"[{symbol}] 💰 {reason} (市价吃单) 执行成功！仓位从 {before} -> {after}")
    return order, fresh, after


async def _limit_reduce_with_maker_retry(
    exchange, symbol, side, position, requested_qty, reason, conf, expected_version, pos_state,
    max_retries=15, check_interval_sec=1.0, timeout_sec=10.0, allow_market_fallback=True, maker_only=False
):
    """非紧急减仓：限价挂单循环。maker_only=True 时禁止市价保底。max_retries<=0 表示持续循环。"""
    raw_ps = _raw_position_side(position)
    before = _position_size(position)
    if int(pos_state.get("position_version", 0)) != expected_version:
        raise RuntimeError("仓位版本已变化，拒绝按旧快照下单")

    qty = _f(exchange.amount_to_precision(symbol, min(before, requested_qty)), 0.0)
    if not qty or qty <= 0:
        raise RuntimeError(f"{reason}: 下单数量无效")

    order_side = "sell" if side == "long" else "buy"
    params = {"reduceOnly": True}
    if raw_ps != "BOTH":
        params["positionSide"] = raw_ps
    # 机器人减仓单统一打标，便于清理重启/异常后遗留的重复减仓单。
    params["newClientOrderId"] = f"PM_WS_R_{uuid.uuid4().hex[:20]}"
    if maker_only:
        # Binance Futures GTX = Post Only；若会立即成交，交易所拒单，随后下一轮重新挂。
        params["timeInForce"] = "GTX"

    remaining_qty = qty

    attempt = 0
    while max_retries <= 0 or attempt < max_retries:
        attempt += 1
        ticker = await _fetch_ticker(exchange, symbol, conf, priority="HIGH", force=True)
        if order_side == "sell":
            limit_price = ticker.get("ask") or ticker.get("last") or ticker.get("close")
        else:
            limit_price = ticker.get("bid") or ticker.get("last") or ticker.get("close")

        price_str = exchange.price_to_precision(symbol, limit_price)
        q_str = exchange.amount_to_precision(symbol, remaining_qty)

        logger.info(f"[{symbol}] ⏳ 非紧急止损【Maker挂单】第 {attempt + 1}/{max_retries} 次尝试 | 挂单价: {price_str} | 数量: {q_str}")

        order_id = None
        try:
            order = await _rest(
                exchange, "create_limit_order", symbol, order_side, q_str, price_str,
                priority="HIGH", conf=conf, params=params
            )
            order_id = order.get("id")
        except Exception as e:
            logger.error(f"[{symbol}] 限价单下发失败: {e}")
            await asyncio.sleep(1)
            continue

        start_wait = time.time()
        order_filled = False
        while time.time() - start_wait < timeout_sec:
            await asyncio.sleep(check_interval_sec)
            try:
                fetched_order = await _rest(exchange, "fetch_order", order_id, symbol, priority="HIGH", conf=conf)
                status = str(fetched_order.get("status")).upper()
                filled = _f(fetched_order.get("filled"), 0.0)

                if status in ("CLOSED", "FILLED") or filled >= remaining_qty:
                    logger.success(f"[{symbol}] ✅ 限价止损单已完全成交！")
                    order_filled = True
                    break
                elif status == "CANCELED":
                    remaining_qty = max(0.0, remaining_qty - filled)
                    break
            except Exception as e:
                logger.warning(f"[{symbol}] 查询限价单状态异常: {e}")

        if order_filled:
            remaining_qty = 0
            break

        try:
            fetched_order = await _rest(exchange, "fetch_order", order_id, symbol, priority="HIGH", conf=conf)
            filled = _f(fetched_order.get("filled"), 0.0)
            remaining_qty = max(0.0, remaining_qty - filled)

            await _rest(exchange, "cancel_order", order_id, symbol, priority="HIGH", conf=conf)
            logger.info(f"[{symbol}] 限价单超时未成交，撤单重试。剩余: {remaining_qty}")
        except Exception as e:
            logger.warning(f"[{symbol}] 撤销限价单失败: {e}")

        if remaining_qty <= 0:
            break

    if remaining_qty > 0 and allow_market_fallback:
        logger.warning(f"[{symbol}] 限价单重试 {max_retries} 次后仍剩余 {remaining_qty}，启动市价单保底平仓")
        await _market_reduce_and_confirm(
            exchange, symbol, side, position, remaining_qty, f"{reason}(保底市价)", conf, expected_version, pos_state
        )
    elif remaining_qty > 0:
        logger.info(f"[{symbol}] 🔁 {reason} Maker挂单仍有 {remaining_qty} 未成交，保持循环挂单，不吃单。")

    fresh = await _position_fresh(exchange, symbol, side, conf, priority="HIGH")
    after = _position_size(fresh)
    logger.success(f"[{symbol}] 💰 {reason} 执行结束！仓位从 {before} -> {after}")
    return fresh, after


async def _cancel_bot_reduce_orders(exchange, symbol, side, conf, reason="重复减仓单清理"):
    """只清理本机器人创建的未完成 reduceOnly 限价减仓单。"""
    try:
        orders = await _rest(exchange, "fetch_open_orders", symbol, priority="HIGH", conf=conf)
        if not isinstance(orders, list):
            return 0
        canceled = 0
        expected_side = "sell" if side == "long" else "buy"
        for order in orders:
            try:
                info = order.get("info") if isinstance(order.get("info"), dict) else {}
                client_id = str(order.get("clientOrderId") or order.get("clientAlgoId") or info.get("clientOrderId") or info.get("origClientOrderId") or "")
                reduce_only = order.get("reduceOnly")
                if reduce_only is None:
                    reduce_only = info.get("reduceOnly")
                if not client_id.startswith("PM_WS_R_") or str(reduce_only).lower() not in ("true", "1"):
                    continue
                if str(order.get("type") or "").lower() not in ("limit", "limit_maker"):
                    continue
                if str(order.get("status") or "open").lower() not in ("open", "new", "partially_filled"):
                    continue
                if str(order.get("side") or "").lower() not in ("", expected_side):
                    continue
                oid = str(order.get("id") or "")
                if not oid:
                    continue
                await _rest(exchange, "cancel_order", oid, symbol, priority="HIGH", conf=conf)
                canceled += 1
            except Exception as exc:
                logger.warning(f"[{symbol}] 清理机器人旧减仓单失败: {exc}")
        if canceled:
            logger.warning(f"[{symbol}] 🧹 {reason}：已取消 {canceled} 张机器人旧减仓单。")
        return canceled
    except Exception as exc:
        logger.warning(f"[{symbol}] 查询机器人旧减仓单失败: {exc}")
        return 0


# ---------------------------------------------------------------------------
# 双轨治理：接管开仓端遗留的固定 SL/TP/TS 条件单
# ---------------------------------------------------------------------------

# 开仓端 order_id.VALID_PREFIXES 中的条件单前缀（SL=固定止损 TP=固定止盈 TS=移动止盈）。
# 守护端自己的单据前缀为 PM_WS_SL_ / PM_WS_R_，不会被这些前缀误伤。
EXTERNAL_CONDITIONAL_PREFIXES = ("SL", "TP", "TS")


def _is_external_conditional_order(order):
    """识别开仓端遗留的固定 SL/TP/TS 条件单（按 clientOrderId 前缀）。"""
    if not isinstance(order, dict):
        return False
    info = order.get("info") if isinstance(order.get("info"), dict) else {}
    client_id = str(
        order.get("clientOrderId") or order.get("clientAlgoId")
        or info.get("clientOrderId") or info.get("origClientOrderId") or ""
    )
    return any(client_id.startswith(p) for p in EXTERNAL_CONDITIONAL_PREFIXES)


async def _take_over_external_stops(exchange, symbol, side, pos, conf):
    """双轨治理：撤销开仓端遗留的 SL/TP/TS 条件单，止盈止损由守护端独家管理。

    安全顺序：先确认守护端自己的保护 STOP 已挂出；未就位则本轮不撤
    （避免撤掉交易所兜底后守护端故障导致裸仓），由调用方下轮重试。
    返回：-1 = 守护端 STOP 未就位（调用方应下轮重试）；>=0 = 撤销张数（接管流程已完成）。
    """
    stops = await _find_stop_orders(exchange, symbol, side, pos, 0, conf, force=True)
    if not stops:
        logger.warning(f"[{symbol}/{side}] ⏳ 接管外部SL/TP/TS：守护端保护STOP未就位，本轮跳过。")
        return -1

    expected_side = "sell" if side == "long" else "buy"
    canceled = 0

    # 1) 普通挂单簿中的条件单（STOP_MARKET / TAKE_PROFIT_MARKET / TRAILING_STOP_MARKET）
    try:
        orders = await _rest(exchange, "fetch_open_orders", symbol, priority="HIGH", conf=conf)
        for order in orders if isinstance(orders, list) else []:
            if not _is_external_conditional_order(order):
                continue
            order_side = str(order.get("side") or "").lower()
            if order_side and order_side != expected_side:
                continue
            oid = str(order.get("id") or "")
            if not oid:
                continue
            try:
                await _rest(exchange, "cancel_order", oid, symbol, priority="HIGH", conf=conf)
                canceled += 1
            except Exception as exc:
                logger.warning(f"[{symbol}] 撤销外部条件单失败: {exc}")
    except Exception as exc:
        logger.warning(f"[{symbol}] 扫描外部条件单失败: {exc}")

    # 2) Algo 接口的条件单（部分渠道 TRAILING_STOP_MARKET 落在 algo 订单簿）
    try:
        algo_orders = await _get_open_algo_orders(exchange, symbol, conf, force=True)
        for order in algo_orders if isinstance(algo_orders, list) else []:
            if not _is_external_conditional_order(order):
                continue
            algo_id = order.get("algoId") or order.get("id")
            if not algo_id:
                continue
            try:
                await _cancel_algo(exchange, symbol, algo_id, conf)
                canceled += 1
            except Exception as exc:
                logger.warning(f"[{symbol}] 撤销外部algo单失败: {exc}")
    except Exception as exc:
        logger.warning(f"[{symbol}] 扫描外部algo条件单失败: {exc}")

    if canceled:
        logger.warning(
            f"[{symbol}/{side}] 🤝 已接管开仓端遗留 SL/TP/TS 条件单 {canceled} 张，"
            f"止盈止损由守护端独家管理。")
    return canceled


async def _full_exit_with_revalidation(exchange, symbol, side, position, reason, conf, pos_state):
    expected_version = int(pos_state.get("position_version", 0))
    fresh = await _position_fresh(exchange, symbol, side, conf, priority="HIGH")
    if not fresh:
        return True, None
    if int(pos_state.get("position_version", 0)) != expected_version:
        raise RuntimeError("全平前仓位版本已变化，重新评估")

    before = _position_size(fresh)
    _, after_pos, after = await _market_reduce_and_confirm(
        exchange, symbol, side, fresh, before, reason, conf, expected_version, pos_state
    )
    return after <= 1e-10, after_pos


# ---------------------------------------------------------------------------
# Stop maintenance（交易所 STOP 维护，含止盈利润保护升级）
# ---------------------------------------------------------------------------

LAST_STOP_ORDER_TIME = {}
LAST_STOP_MAINTAIN_TIME = {}


async def _ensure_disaster_stop(exchange, symbol, side, pos, current_price, conf, ohlcv_rows=None, force_replace=False, pos_state=None):
    if not bool(conf.get("exchange_hard_stop_enabled", True)):
        return

    now_ts = time.time()
    interval = float(conf.get("stop_maintenance_interval_sec", 60.0))

    if now_ts - LAST_STOP_MAINTAIN_TIME.get(symbol, 0) < interval and not force_replace:
        return

    LAST_STOP_MAINTAIN_TIME[symbol] = now_ts

    try:
        strategy = None
        try:
            if ohlcv_rows:
                strategy = _strategy_levels_from_rows(ohlcv_rows, conf)
        except Exception as strategy_exc:
            logger.warning(f"[{symbol}] EMA/结构止损计算失败，退回 ATR 兜底: {strategy_exc}")

        if strategy:
            stop, distance = _calculate_dynamic_protection_stop(exchange, symbol, side, current_price, strategy, conf)
        else:
            if ohlcv_rows:
                atr = _atr_from_rows(ohlcv_rows, int(conf.get("hard_stop_atr_period", 14)))
            else:
                tf = str(conf.get("hard_stop_timeframe", "1h"))
                atr = await _closed_atr(exchange, symbol, tf, int(conf.get("hard_stop_atr_period", 14)), conf)
            stop, distance = _calculate_disaster_stop(exchange, symbol, side, current_price, atr, conf)

        # 分级止盈后，交易所 STOP 必须升级为利润保护线。
        tp_protected_stop, tp_stage = (None, 0)
        if pos_state and bool(conf.get("take_profit_enabled", True)):
            try:
                tp_protected_stop, tp_stage = _take_profit_protection_stop(pos_state, side, conf, current_price)
                if tp_protected_stop and tp_protected_stop > 0:
                    if side == "long" and tp_protected_stop < current_price:
                        stop = max(stop, float(tp_protected_stop))
                    elif side == "short" and tp_protected_stop > current_price:
                        stop = min(stop, float(tp_protected_stop))
                    stop = float(exchange.price_to_precision(symbol, stop))
                    distance = abs(current_price - stop) / current_price
                    previous_tp_stage = int(pos_state.get("tp_protection_stage", 0) or 0)
                    pos_state["tp_protected_stop"] = stop
                    pos_state["tp_protection_stage"] = tp_stage
                    if tp_stage > previous_tp_stage or (previous_tp_stage == 0 and tp_stage == 1):
                        logger.success(
                            f"[{symbol}] 🛡️ 盈利保护已启动/升级 | 浮盈触发阈值:{float(conf.get('profit_protection_trigger_r', 0.5)):.2f}R | "
                            f"保护阶段:TP{tp_stage} | STOP:{stop:.8f}"
                        )
                    logger.success(
                        f"[{symbol}] 🔐 止盈后利润保护 | TP{tp_stage} | "
                        f"保护止损:{stop:.8f} | 当前:{current_price:.8f} | 距离:{distance:.2%}"
                    )
            except Exception as tp_stop_exc:
                logger.warning(f"[{symbol}] 止盈后保护止损计算失败，继续使用策略止损: {tp_stop_exc}")

        # 连续移动止损（trailing_stop_mode='continuous'）：浮盈达到 trailing_trigger_r
        # 后，追踪线按 current_price ± trailing_atr_multiple×ATR 随价格平滑推进；
        # 与阶梯保护取盈利方向的 max/min，推进仍受"只许盈利方向 + 最小有效距离"约束防抖。
        if pos_state:
            try:
                atr_for_trail = float(strategy.get("atr") or 0.0) if strategy else 0.0
                if atr_for_trail <= 0 and ohlcv_rows:
                    atr_for_trail = float(_atr_from_rows(
                        ohlcv_rows, int(conf.get("hard_stop_atr_period", 14))) or 0.0)
                if atr_for_trail <= 0:
                    tf = str(conf.get("hard_stop_timeframe", "1h"))
                    atr_for_trail = float(await _closed_atr(
                        exchange, symbol, tf, int(conf.get("hard_stop_atr_period", 14)), conf) or 0.0)

                trail_stop, floating_r = _continuous_trailing_stop(
                    pos_state, side, current_price, atr_for_trail, conf)
                if trail_stop and trail_stop > 0:
                    if side == "long":
                        stop = max(stop, float(trail_stop))
                    else:
                        stop = min(stop, float(trail_stop))
                    stop = float(exchange.price_to_precision(symbol, stop))
                    distance = abs(current_price - stop) / current_price
                    pos_state["trailing_stop"] = float(trail_stop)
                    _status_log(
                        "trailing", symbol, side, "INFO",
                        f"[{symbol}] 📈 连续移动止损 | 浮盈:{floating_r:.2f}R | "
                        f"追踪线:{float(trail_stop):.8f} | ATR:{atr_for_trail:.8f} | "
                        f"综合STOP:{stop:.8f}",
                        float(conf.get("status_log_interval_sec", 900.0)),
                    )
            except Exception as trail_exc:
                logger.warning(f"[{symbol}] 连续移动止损计算失败，本轮沿用阶梯保护: {trail_exc}")

        # 一仓一 STOP：读取全部保护 STOP；重复时全部清理，只重建一个。
        stops = await _find_stop_orders(exchange, symbol, side, pos, current_price, conf, force=True)
        duplicate_stops = len(stops) > 1
        existing_trigger = _algo_trigger(stops[0]) if stops else None
        if strategy:
            _status_log(
                "stop_overview", symbol, side, "INFO",
                f"[{symbol}] 🛡️ 止盈/止损位 | 方向:{side} | 当前价:{current_price:.8f} | "
                f"策略止损:{stop:.8f} | 距离:{distance:.2%} | "
                f"EMA26:{strategy['ema_fast']:.8f} | EMA83:{strategy['ema_slow']:.8f} | "
                f"ATR14:{strategy['atr']:.8f} | 结构止损:{strategy['long_structure'] if side == 'long' else strategy['short_structure']:.8f} | "
                f"趋势:{strategy['trend']} | TP保护阶段:{tp_stage} | TP保护止损:{tp_protected_stop if tp_protected_stop else '未启用'} | 交易所STOP:{existing_trigger if existing_trigger is not None else '不存在'}",
                float(conf.get("status_log_interval_sec", 900.0)),
            )
        else:
            _status_log(
                "stop_overview", symbol, side, "INFO",
                f"[{symbol}] 🛡️ 止损位 | 方向:{side} | 当前价:{current_price:.8f} | "
                f"ATR兜底止损:{stop:.8f} | 距离:{distance:.2%} | "
                f"交易所STOP:{existing_trigger if existing_trigger is not None else '不存在'}",
                float(conf.get("status_log_interval_sec", 900.0)),
            )

        needs_update = False
        material_move = False
        if stops:
            if existing_trigger is not None:
                # 只允许STOP向盈利方向推进；反方向绝不放宽。
                if side == "long":
                    if stop < existing_trigger:
                        stop = existing_trigger
                else:
                    if stop > existing_trigger:
                        stop = existing_trigger

                stop = float(exchange.price_to_precision(symbol, stop))
                existing_trigger = float(exchange.price_to_precision(symbol, existing_trigger))

                # 不再使用旧的1.5%固定阈值。
                # 但也不能因为当前价/ATR轻微变化就每几个tick取消重挂。
                # 有效推进距离 = max(价格百分比门槛, ATR比例门槛)。
                try:
                    atr_for_threshold = float(strategy.get("atr") or 0.0) if strategy else 0.0
                except Exception:
                    atr_for_threshold = 0.0
                if atr_for_threshold <= 0 and ohlcv_rows:
                    try:
                        atr_for_threshold = float(_atr_from_rows(ohlcv_rows, int(conf.get("hard_stop_atr_period", 14))) or 0.0)
                    except Exception:
                        atr_for_threshold = 0.0

                min_move_pct = max(0.0, float(conf.get("stop_min_update_pct", 0.0005)))
                min_move_atr_ratio = max(0.0, float(conf.get("stop_min_update_atr_ratio", 0.05)))
                min_move = max(existing_trigger * min_move_pct, atr_for_threshold * min_move_atr_ratio)
                actual_move = (stop - existing_trigger) if side == "long" else (existing_trigger - stop)
                material_move = actual_move >= min_move and actual_move > 0

                if material_move:
                    needs_update = True
                else:
                    # 细微变化直接沿用原STOP，不取消、不重挂。
                    stop = existing_trigger
                    if actual_move > 0:
                        # 完全没变化（推进为0）时零信息量，直接不打；有提议但被门槛挡住才节流输出
                        _status_log(
                            "stop_hold", symbol, side, "DEBUG",
                            f"[{symbol}] 🧊 STOP变化过小，保持原单 | "
                            f"旧:{existing_trigger:.8f} 新:{stop:.8f} | "
                            f"实际推进:{actual_move:.8f} | 最小有效推进:{min_move:.8f}",
                            float(conf.get("status_log_interval_sec", 900.0)),
                        )

            if duplicate_stops:
                # 重复STOP与价格推进阈值无关，必须立即清理，只保留一个。
                logger.warning(f"[{symbol}] ⚠️ 检测到 {len(stops)} 个重复保护STOP，全部清理后只保留1个。")
                needs_update = True

        # force_replace只用于新仓/加仓/仓位变化等风险周期变化。
        # 如果STOP价格本身没有有效变化，则不因为force_replace而无意义地取消重挂。
        if stops and not needs_update:
            return

        if stops:
            await _cancel_stop_orders(exchange, symbol, stops, conf)

        await _create_full_close_stop(exchange, symbol, pos, side, stop, conf)
        if pos_state is not None:
            pos_state["last_stop_price"] = float(stop)
            pos_state["last_stop_update_ts"] = int(time.time() * 1000)
            try:
                state = _load_state()
                skey = _state_key(symbol, side)
                if isinstance(state.get(skey), dict):
                    state[skey]["last_stop_price"] = float(stop)
                    state[skey]["last_stop_update_ts"] = int(time.time() * 1000)
                    if pos_state is not None:
                        state[skey]["tp_protected_stop"] = pos_state.get("tp_protected_stop")
                        state[skey]["tp_protection_stage"] = int(pos_state.get("tp_protection_stage", 0) or 0)
                    _save_state(state)
            except Exception:
                pass
        logger.success(
            f"[{symbol}] 🔒 交易所STOP止损已设置 | 方向:{side} | "
            f"触发价:{stop:.8f} | 当前价:{current_price:.8f} | 距离:{distance:.2%} | 类型:STOP_MARKET"
        )
        LAST_STOP_ORDER_TIME[symbol] = time.time()

    except Exception as e:
        logger.error(f"[{symbol}] 维护灾难止损出错: {e}")
