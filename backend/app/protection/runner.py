# backend/app/protection/runner.py
"""仓位保护 v2 引擎：单循环批量调度 + 一仓一行账本 + 纯函数决策。

和 v1 的差别（不是换参数，是换结构）
1. 不再「一仓一协程」：v1 里 44 个协程各自拉 K 线、各自 force 查挂单，请求量随
   仓位数量线性增长，只能靠熔断兜底。v2 一个循环批量拉仓位与 ticker，K 线/挂单
   全部走缓存，请求量基本恒定。
2. 判断交给 risk_model（纯函数），执行复用 engine 里已验证的下单原语
   （maker 循环、市价兜底、算法单兼容），所以「怎么下单」没有变。
3. 状态一仓一行（ledger），不会出现跨币种整表覆盖。
4. 每个动作写审计事件，能回看「什么时候、因为哪条线、减了多少」。

可回滚：配置 `position_protection.engine_version` 设成 `v1` 即回到旧引擎。
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger

from . import engine, ledger, risk_model
from .config import load_protection_config
from .notifier import send_alert
from .stops import _continuous_trailing_stop

Key = Tuple[str, str]


class _Runtime:
    """v2 运行时视图，仅供状态接口展示，不参与决策。"""

    def __init__(self) -> None:
        self.last_cycle_ts = 0.0
        self.cycle_count = 0
        self.active: Set[Key] = set()
        self.recent_actions: List[Dict[str, Any]] = []
        self.last_error: Optional[str] = None
        self.disappeared_since: Dict[Key, float] = {}

    def note_action(self, symbol: str, side: str, text: str, level: str = 'info') -> None:
        self.recent_actions.append({
            'ts': time.time(), 'symbol': symbol, 'side': side,
            'text': text, 'level': level,
        })
        if len(self.recent_actions) > 100:
            del self.recent_actions[:-100]


V2 = _Runtime()


def load_config() -> Dict[str, Any]:
    """v2 参数 = V2_DEFAULTS ∪ 用户覆盖（用户没写的字段一律用默认值）。"""
    raw = load_protection_config().get('position_protection', {}) or {}
    conf = dict(risk_model.V2_DEFAULTS)
    for key, value in raw.items():
        if value is not None:
            conf[key] = value
    return conf


def _f(value: Any, default: float = 0.0) -> float:
    return engine._f(value, default) or 0.0


# ---------------------------------------------------------------------------
# 市场数据
# ---------------------------------------------------------------------------
async def _refresh_tickers(exchange, conf: Dict[str, Any]) -> None:
    """一次批量拉全市场 ticker 灌进 engine 的缓存，后续单币读取零请求。"""
    try:
        tickers = await engine._rest(exchange, 'fetch_tickers', priority='LOW', conf=conf)
        now = time.monotonic()
        if isinstance(tickers, dict):
            for symbol, data in tickers.items():
                engine.RUNTIME.ticker_cache[symbol] = (now, data)
    except Exception as exc:  # noqa: BLE001 - 批量失败时降级为单币拉取
        logger.debug(f'[v2] 批量 tickers 失败，降级单币: {exc}')


def _price_of(ticker: Dict[str, Any]) -> float:
    if not isinstance(ticker, dict):
        return 0.0
    return _f(ticker.get('mark')) or _f(ticker.get('last')) or _f(ticker.get('close'))


async def _price(exchange, symbol: str, conf: Dict[str, Any]) -> float:
    try:
        ticker = await engine._fetch_ticker(exchange, symbol, conf, priority='LOW')
        return _price_of(ticker)
    except Exception:
        return 0.0


def _structure_from_df(df, side: str, lookbacks: List[int]) -> Tuple[float, float, float]:
    picks: List[float] = []
    for lb in lookbacks[:3]:
        bars = df.iloc[-max(2, int(lb)):]
        picks.append(float(bars['low'].min()) if side == 'long' else float(bars['high'].max()))
    return picks[0], picks[1], picks[2]


# ---------------------------------------------------------------------------
# 生命周期：仓位消失 → 确认超时 → 清账本 + 清旧挂单
# ---------------------------------------------------------------------------
async def _sweep_lifecycle(exchange, conf: Dict[str, Any], active: Set[Key]) -> None:
    """账本对账：清掉「账本里有、但交易所已无此仓位」的幽灵行。

    关键：对账基准是**账本全集 vs 本轮真实持仓**，不再依赖进程内存里的
    previous_active —— 否则引擎重启后内存集合丢失，平仓后的旧账本行
    永远不会被清理，前端"守护中的仓位"会越积越多（幽灵仓位）。
    flat_confirm_sec 缓冲防接口偶发漏报。
    """
    now = time.time()
    confirm = max(0.0, _f(conf.get('flat_confirm_sec'), 30.0))
    # 账本 key 是 'symbol|side' 字符串，active 是 (symbol, side) tuple —— 先统一成 tuple。
    ledger_keys = {ledger.split_key(k) for k in ledger.all_positions().keys()}
    disappeared = ledger_keys - active

    for key in disappeared:
        since = V2.disappeared_since.setdefault(key, now)
        if confirm > 0 and (now - since) < confirm:
            continue  # 接口偶发漏报，先不下结论（账本行保留，下轮复核）
        V2.disappeared_since.pop(key, None)
        symbol, side = key  # disappeared 元素已是 (symbol, side) tuple
        ledger.delete(symbol, side)
        ledger.log_event(symbol, side, 'flat', '仓位已消失，清除本风险周期并清理旧挂单')
        try:
            await engine._cancel_program_stops_for_flat(exchange, symbol, side, conf)
            await engine._cancel_bot_reduce_orders(
                exchange, symbol, side, conf, reason='仓位已平，清理旧减仓单')
        except Exception as exc:  # noqa: BLE001 - 清理失败不影响守护
            logger.warning(f'[{symbol}/{side}] 平仓后清理异常: {exc}')
        logger.info(f'[{symbol}/{side}] 🧹 仓位已消失：下次开仓建立全新风险周期')

    for key in list(V2.disappeared_since):
        if key in active:
            V2.disappeared_since.pop(key, None)


# ---------------------------------------------------------------------------
# 单仓准备：拉数据 → 判断是否新周期 → 生成快照 → 决策
# ---------------------------------------------------------------------------
def _is_new_cycle(state: Optional[Dict[str, Any]], side: str, entry: float,
                  contracts: float, opened_ms: int) -> bool:
    if not state or not isinstance(state.get('plan'), dict):
        return True
    # 只在「加仓」时换周期。减仓导致的交易所字段抖动绝不再触发换周期（v1 的 T1 自激根因）。
    base = _f(state.get('base_contracts'))
    if base > 0 and contracts > base * 1.005:
        return True
    old_opened = int(_f(state.get('opened_at_ms')))
    if opened_ms > 0 and old_opened > 0 and abs(opened_ms - old_opened) > 3000:
        return True
    # 引擎停机期间「平仓又重开」：账本记录的建立时间早于本次开仓时间，必须换周期
    created = _f(state.get('created_at'))
    if opened_ms > 0 and created > 0 and opened_ms / 1000.0 > created + 60:
        return True
    return False


async def _prepare(exchange, conf: Dict[str, Any], symbol: str, side: str,
                   pos: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    now = time.time()
    timeframe = str(conf.get('v2_timeframe') or conf.get('timeframe') or '2h')
    lookbacks = risk_model._floats(conf.get('tier_lookbacks'), risk_model.V2_DEFAULTS['tier_lookbacks'])
    limit = max(int(max(lookbacks)) + 30, 120)

    entry = _f(pos.get('entryPrice'))
    contracts = engine._position_size(pos)
    if contracts <= 0 or entry <= 0:
        return None

    rows = await engine._fetch_ohlcv(exchange, symbol, timeframe, limit, conf, priority='LOW')
    if not rows or len(rows) < 40:
        return None

    try:
        strategy = engine._strategy_levels_from_rows(rows, conf)
        atr = float(strategy['atr'])
        df = strategy['df']
        structure = _structure_from_df(df, side, lookbacks)
        last_close = float(strategy['last_close'])
        closed_ts = int(strategy['closed_ts'])
    except Exception as exc:  # noqa: BLE001 - EMA 失败时退化为纯 ATR 兜底
        logger.warning(f'[{symbol}] v2 结构计算失败，退化为 ATR 兜底: {exc}')
        try:
            atr = float(engine._atr_from_rows(rows, 14))
        except Exception:
            return None
        last_close = float(rows[-2][4])
        closed_ts = int(rows[-2][0])
        structure = (last_close, last_close, last_close)

    price = await _price(exchange, symbol, conf) or last_close

    state = ledger.load(symbol, side)
    opened_ms = engine._position_open_time_ms(pos)
    new_cycle = _is_new_cycle(state, side, entry, contracts, opened_ms)

    if new_cycle:
        try:
            plan = risk_model.build_plan(side, entry, atr, structure, conf, now=now)
        except Exception as exc:  # noqa: BLE001 - 参数写坏时退回默认值，绝不让仓位裸奔
            logger.error(f'[{symbol}/{side}] v2 风险计划参数非法，退回默认四档: {exc}')
            safe = dict(risk_model.V2_DEFAULTS)
            safe['tier_confirm_sec'] = conf.get('tier_confirm_sec', safe['tier_confirm_sec'])
            plan = risk_model.build_plan(side, entry, atr, structure, safe, now=now)
        state = risk_model.new_state(uuid.uuid4().hex, side, entry, contracts, plan, now)
        state['opened_at_ms'] = int(opened_ms)
        state['position_version'] = 1
        logger.info(
            f'[{symbol}/{side}] 🆕 v2 新风险周期 | 开仓:{entry:.6f} ATR:{atr:.6f} '
            f'R:{plan["risk"]:.6f}({plan["risk"] / entry:.2%}) | '
            f'四档:{"/".join(f"{x:.6f}" for x in plan["levels"])} | '
            f'灾难线:{plan["disaster_stop"]:.6f}')
        ledger.log_event(symbol, side, 'cycle_new', '建立新风险周期',
                         entry=entry, atr=atr, risk=plan['risk'], levels=plan['levels'])
    else:
        plan = state['plan']
        atr = atr or _f(plan.get('atr_at_plan'))

    # 双轨治理（每轮检查，幂等 + 60s 节流）：接管开仓端遗留 SL/TP/TS 条件单。
    # -1 = 守护端 STOP 未就位（标志不置，节流后下轮重试）；>=0 = 接管流程完成。
    if bool(conf.get('take_over_external_stops', False)) \
            and not state.get('external_stops_taken_over') \
            and now - _f(state.get('external_stops_check_ts')) > 60:
        state['external_stops_check_ts'] = now
        try:
            taken = await engine._take_over_external_stops(exchange, symbol, side, pos, conf)
            if taken >= 0:
                state['external_stops_taken_over'] = True
        except Exception as exc:  # noqa: BLE001 - 接管失败不影响守护
            logger.warning(f'[{symbol}/{side}] 接管外部SL/TP/TS失败，下轮重试: {exc}')

    snap = risk_model.Snapshot(
        symbol=symbol, side=side, entry=_f(plan.get('entry'), entry),
        price=price, last_close=last_close, contracts=contracts,
        base_contracts=_f(state.get('base_contracts'), contracts),
        atr=atr, structure=structure, closed_ts=closed_ts, now=now,
    )

    decision = risk_model.decide(state, snap, conf)

    # 连续移动止损：追踪线与决策 STOP 取盈利方向更优者；没有 stop 动作时补一张。
    # 放在黑天鹅检查之前：emergency 命中时仍会压过本动作（安全优先级不变）。
    trail_stop = _v2_trailing_stop(state, side, snap, atr, conf)
    if trail_stop and trail_stop > 0:
        patched = False
        for act in decision.get('actions') or []:
            if act.get('type') != 'stop':
                continue
            current = _f(act.get('price'))
            act['price'] = max(current, trail_stop) if side == 'long' else (
                min(current, trail_stop) if current > 0 else trail_stop)
            patched = True
        if not patched:
            decision.setdefault('actions', []).append({
                'type': 'stop', 'price': trail_stop, 'tag': 'trailing',
                'level': 'info', 'reason': '连续移动止损'})

    # 黑天鹅：独立一支，命中直接压过所有结构/止盈动作
    emergency = await _check_emergency(exchange, conf, symbol, side, state, snap)
    if emergency:
        decision['actions'] = [emergency]

    state.update(decision.get('patch') or {})
    state['last_price'] = price
    state['last_atr'] = atr
    if new_cycle:
        ledger.save(symbol, side, state)

    return {
        'symbol': symbol, 'side': side, 'pos': pos, 'state': state,
        'snap': snap, 'actions': decision.get('actions') or [],
    }


def _v2_trailing_stop(state: Dict[str, Any], side: str, snap: 'risk_model.Snapshot',
                      atr: float, conf: Dict[str, Any]) -> Optional[float]:
    """v2 连续移动止损：浮盈达到 trailing_trigger_r 后按 ATR 平滑追踪。

    带 min_move 防抖（避免每轮撤单重挂刷交易所）；追踪线只许向盈利方向推进。
    返回需要写入的追踪价，或 None（不更新）。
    """
    if str(conf.get('trailing_stop_mode', 'step') or 'step').lower() != 'continuous':
        return None
    plan = state.get('plan') or {}
    trail_state = {'tp_entry_price': plan.get('entry'), 'tp_risk_distance': plan.get('risk')}
    trail, _floating_r = _continuous_trailing_stop(trail_state, side, snap.price, atr, conf)
    if not trail or trail <= 0:
        return None
    current_stop = _f(state.get('stop'))
    if current_stop <= 0:
        return trail  # 账本还没有 STOP：首个兜底单直接用追踪线
    min_move = max(
        snap.price * _f(conf.get('stop_min_update_pct'), 0.0005),
        atr * _f(conf.get('stop_min_update_atr_ratio'), 0.05))
    improved = (trail - current_stop) if side == 'long' else (current_stop - trail)
    return trail if improved >= min_move else None


async def _check_emergency(exchange, conf: Dict[str, Any], symbol: str, side: str,
                           state: Dict[str, Any], snap: risk_model.Snapshot) -> Optional[Dict[str, Any]]:
    if not bool(conf.get('emergency_enabled', True)):
        return None
    interval = max(5.0, _f(conf.get('emergency_check_interval_sec'), 20.0))
    last = _f(state.get('last_emergency_check'))
    if last and snap.now - last < interval:
        return None
    state['last_emergency_check'] = snap.now
    try:
        triggered, details = await engine._emergency_signal(exchange, symbol, side, conf)
    except Exception as exc:  # noqa: BLE001 - 单次失败不阻断主循环
        logger.debug(f'[{symbol}] 黑天鹅检查异常: {exc}')
        return None
    if not triggered or not details:
        return None
    ok, _ = await engine._two_source_price_ok(exchange, symbol, details.get('ws_price', 0), side, conf)
    if not ok:
        return None
    reason = f"黑天鹅 {details.get('reason', '异常波动')}"
    return {'type': 'exit', 'ratio': 1.0, 'tag': 'emergency', 'level': 'error', 'reason': reason}


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------
def _dry_run(conf: Dict[str, Any], state: Dict[str, Any], tag: str) -> bool:
    """演练模式：只记录动作、不下单；同一个动作只记一次，避免每 3 秒刷日志。"""
    if not bool(conf.get('dry_run', False)):
        return False
    seen = state.setdefault('shadow', {})
    if tag not in seen:
        seen[tag] = time.time()
        logger.warning(f'[v2][DRY-RUN] 本应执行 {tag}（演练模式不真实下单）')
    return True


async def _apply_reduce(exchange, conf: Dict[str, Any], bundle: Dict[str, Any],
                        act: Dict[str, Any]) -> None:
    symbol, side = bundle['symbol'], bundle['side']
    state, snap, pos = bundle['state'], bundle['snap'], bundle['pos']
    tag = str(act.get('tag') or 'reduce')
    now = time.time()

    if _dry_run(conf, state, tag):
        return

    # 失败重试冷却：下单异常后不要每轮重试，避免刷单
    attempts = state.setdefault('attempts', {})
    last = _f(attempts.get(tag))
    cooldown = max(0.0, _f(conf.get('action_retry_cooldown_sec'), 90.0))
    if last and now - last < cooldown:
        return
    attempts[tag] = now

    ok, _ = await engine._two_source_price_ok(exchange, symbol, snap.price, side, conf)
    if not ok:
        logger.warning(f'[{symbol}] 双源价格不一致，本轮不执行 {tag}')
        return

    fresh = await engine._position_fresh(exchange, symbol, side, conf, priority='HIGH')
    if not fresh:
        ledger.delete(symbol, side)
        return
    current = engine._position_size(fresh)
    base = _f(state.get('base_contracts'), current) or current

    if act['type'] == 'exit' or _f(act.get('ratio')) >= 0.999:
        success, _ = await engine._full_exit_with_revalidation(
            exchange, symbol, side, fresh, act.get('reason', '保护性全平'), conf, state)
        if success:
            ledger.log_event(symbol, side, 'exit', act.get('reason', '全平'), level='error')
            ledger.delete(symbol, side)
            V2.note_action(symbol, side, act.get('reason', '全平'), 'error')
        return

    qty = min(current, base * _f(act.get('ratio')))
    if qty <= 0:
        return

    tiers = act.get('tiers') or []
    maker_only = True
    if tiers:
        maker_only = (max(tiers) + 1) <= int(_f(conf.get('tier_maker_only_until'), 2))

    await engine._cancel_bot_reduce_orders(exchange, symbol, side, conf, reason=f'{tag}前')
    _, after = await engine._limit_reduce_with_maker_retry(
        exchange, symbol, side, fresh, qty, act.get('reason', '保护性减仓'), conf,
        int(_f(state.get('position_version'), 1)), state,
        max_retries=int(_f(conf.get('tier_maker_retries'), 3)),
        check_interval_sec=1.0, timeout_sec=10.0,
        allow_market_fallback=not maker_only, maker_only=maker_only,
    )

    if after >= current - max(1e-12, current * 1e-8):
        logger.warning(f'[{symbol}] {tag} 未成交（{current} -> {after}），保留档位下轮重试')
        ledger.save(symbol, side, state)
        return

    state['contracts'] = after
    state['position_version'] = int(_f(state.get('position_version'), 1)) + 1
    if tiers:
        state['tiers_done'] = sorted(set(risk_model._ints(state.get('tiers_done'))) | set(tiers))
    if act.get('tps'):
        state['tp_done'] = sorted(set(risk_model._ints(state.get('tp_done'))) | set(act['tps']))
    state['last_action_ts'] = now
    ledger.save(symbol, side, state)

    text = f"{act.get('reason')}：{current:.6g} → {after:.6g}（减 {_f(act.get('ratio')):.0%}）"
    ledger.log_event(symbol, side, 'reduce', text, level=str(act.get('level') or 'warning'),
                     ratio=act.get('ratio'), after=after,
                     tiers=tiers, tps=act.get('tps') or [])
    V2.note_action(symbol, side, text, str(act.get('level') or 'warning'))
    send_alert(conf, f"风控提示: {act.get('reason', '减仓')}", f'[{symbol}] {text}', symbol=symbol)


async def _apply_stop(exchange, conf: Dict[str, Any], bundle: Dict[str, Any],
                      act: Dict[str, Any]) -> None:
    symbol, side = bundle['symbol'], bundle['side']
    state, snap, pos = bundle['state'], bundle['snap'], bundle['pos']
    desired = _f(act.get('price'))
    if desired <= 0:
        return
    if _dry_run(conf, state, str(act.get('tag') or 'stop')):
        return

    stops = await engine._find_stop_orders(
        exchange, symbol, side, pos, snap.price, conf, force=False)
    if stops:
        current = engine._algo_trigger(stops[0])
        if current is not None:
            better = desired > current if side == 'long' else desired < current
            if not better:
                # 交易所已有更优的兜底单：以它为准，账本同步
                if abs(_f(state.get('stop')) - float(current)) > 1e-9:
                    state['stop'] = float(current)
                    ledger.save(symbol, side, state)
                return
        await engine._cancel_stop_orders(exchange, symbol, stops, conf)

    await engine._create_full_close_stop(exchange, symbol, pos, side, desired, conf)
    state['stop'] = desired
    ledger.save(symbol, side, state)
    ledger.log_event(symbol, side, 'stop', f'兜底STOP {desired:.8g}',
                     level='info', price=desired)


async def _execute(exchange, conf: Dict[str, Any], bundle: Dict[str, Any]) -> None:
    symbol, side = bundle['symbol'], bundle['side']
    actions = bundle['actions']
    if not actions:
        if bundle.get('_dirty'):
            ledger.save(symbol, side, bundle['state'])
        return

    async with engine.RUNTIME.action_lock(symbol, side):
        for act in actions:
            try:
                if act['type'] == 'stop':
                    await _apply_stop(exchange, conf, bundle, act)
                else:
                    await _apply_reduce(exchange, conf, bundle, act)
            except Exception as exc:  # noqa: BLE001 - 单个动作失败不影响其它仓位
                logger.error(f'[{symbol}/{side}] v2 执行 {act.get("tag")} 失败: {exc}')
                ledger.log_event(symbol, side, 'error',
                                 f'{act.get("tag")} 执行失败: {exc}', level='error')


# ---------------------------------------------------------------------------
# 主循环
# ---------------------------------------------------------------------------
async def protect_positions_main_v2(exchange) -> None:
    conf = load_config()
    if not bool(conf.get('enabled', False)):
        logger.info('仓位保护 v2 已禁用')
        return

    engine._algo_methods(exchange)
    logger.info('🛡️ 仓位保护 v2 启动：批量巡检 + 一仓一行账本 + 纯函数决策')
    logger.info(f'🛡️ v2 参数 | 周期:{conf.get("v2_timeframe")} | 四档:{conf.get("tier_ratios")} '
                f'| 确认秒:{conf.get("tier_confirm_sec")} | 演练模式:{bool(conf.get("dry_run"))}')

    while True:
        started = time.time()
        try:
            conf = load_config()
            if not bool(conf.get('enabled', False)):
                logger.info('🛡️ 仓位保护 v2 配置已关闭，引擎退出')
                return

            positions = await engine._fetch_positions(exchange, conf, force=False)
            await _refresh_tickers(exchange, conf)

            active: Dict[Key, Dict[str, Any]] = {}
            for pos in positions:
                side = engine._position_side(pos)
                symbol = pos.get('symbol')
                if not symbol or side not in ('long', 'short'):
                    continue
                if engine._position_size(pos) <= 0:
                    continue
                active[(symbol, side)] = pos

            await _sweep_lifecycle(exchange, conf, set(active))
            V2.active = set(active)

            if active:
                sem = asyncio.Semaphore(max(1, int(_f(conf.get('v2_decision_concurrency'), 4))))

                async def guarded(item):
                    symbol, side = item
                    async with sem:
                        try:
                            return await _prepare(exchange, conf, symbol, side, active[item])
                        except Exception as exc:  # noqa: BLE001
                            logger.error(f'[{symbol}/{side}] v2 巡检异常: {exc}')
                            return None

                prepared = await asyncio.gather(*(guarded(k) for k in active))
                bundles = [b for b in prepared if b]
                # 执行并发进行：Maker 循环会等成交，不能阻塞其它仓位的保护
                await asyncio.gather(*(_execute(exchange, conf, b) for b in bundles))
                for b in bundles:
                    ledger.save(b['symbol'], b['side'], b['state'])

            V2.last_cycle_ts = time.time()
            V2.cycle_count += 1

            if V2.cycle_count % 100 == 0:
                logger.info(f'💓 [v2 心跳] 第 {V2.cycle_count} 轮 | 守护 {len(active)} 个方向 | '
                            f'请求 {engine.RUNTIME.rest.stats().get("request_count", 0)} 次')

            interval = max(1.0, _f(conf.get('v2_poll_interval_sec'), 3.0))
            await asyncio.sleep(max(0.2, interval - (time.time() - started)))

        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 主循环必须存活
            V2.last_error = f'{type(exc).__name__}: {exc}'
            logger.error(f'v2 风控主循环异常: {exc}', exc_info=True)
            await asyncio.sleep(5.0)


# ---------------------------------------------------------------------------
# 状态（供 /api/protection 使用，不发交易所请求）
# ---------------------------------------------------------------------------
def status() -> Dict[str, Any]:
    """返回给前端的仓位行，字段与 v1 保持兼容，另加 v2 专属字段。"""
    rows: List[Dict[str, Any]] = []
    for key, state in ledger.all_positions().items():
        symbol, side = ledger.split_key(key)
        # 幽灵行兜底：对账修复前的残留行（仓位已平但账本未清）不再展示。
        if _f(state.get('contracts'), 0.0) <= 0:
            continue
        plan = state.get('plan') or {}
        levels = plan.get('levels') or []
        tps = plan.get('tp_prices') or [None, None, None]
        done = set(risk_model._ints(state.get('tiers_done')))
        tp_done = set(risk_model._ints(state.get('tp_done')))
        rows.append({
            'symbol': symbol,
            'side': side,
            'contracts': state.get('contracts'),
            'entry_price': plan.get('entry'),
            'mark_price': state.get('last_price'),
            'stop_price': state.get('stop'),
            'protected_stop': None,
            'tp1_price': tps[0] if len(tps) > 0 else None,
            'tp2_price': tps[1] if len(tps) > 1 else None,
            'tp3_price': tps[2] if len(tps) > 2 else None,
            't1_done': 0 in done,
            't2_done': 1 in done,
            't3_done': 2 in done,
            't4_done': 3 in done,
            'tp1_done': 0 in tp_done,
            'tp2_done': 1 in tp_done,
            'tp3_done': 2 in tp_done,
            # v2 专属：四档线、R、灾难线、周期
            'engine': 'v2',
            'cycle_id': state.get('cycle_id'),
            'risk': plan.get('risk'),
            'tier_levels': levels,
            'disaster_stop': plan.get('disaster_stop'),
            'base_contracts': state.get('base_contracts'),
            'updated_at': state.get('updated_at'),
        })
    rows.sort(key=lambda r: (r['symbol'], r['side']))
    return {
        'cycle_count': V2.cycle_count,
        'last_cycle_ts': V2.last_cycle_ts,
        'positions': rows,
        'recent_actions': V2.recent_actions[-30:],
        'last_error': V2.last_error,
    }
