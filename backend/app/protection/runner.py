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

from . import cooldown, engine, ledger, risk_model, tp_orders
from .config import load_protection_config
from .notifier import send_alert

Key = Tuple[str, str]

# 「仓位消失」定性阈值：最后轮询价距兜底 STOP 在 1% 以内 → 认定为止损触发。
# 真实成交价事后无法反查（条件市价单在交易所侧成交），只能按这个距离判断。
_STOP_TOUCH_TOL = 0.01


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


# 旧版本会把「默认值」原样存进 position_protection，于是升级默认值对老配置完全无效。
# 值恰好等于旧默认时视为「用户没改过」，让它跟随新默认（2026-11-15 跟踪宽度 2.5→1.5）。
LEGACY_DEFAULTS = {'trailing_atr_mult': 2.5}


def _is_legacy_default(key: str, value: Any) -> bool:
    legacy = LEGACY_DEFAULTS.get(key)
    if legacy is None:
        return False
    try:
        return abs(float(value) - legacy) < 1e-9
    except (TypeError, ValueError):
        return False


def load_config() -> Dict[str, Any]:
    """v2 参数 = V2_DEFAULTS ∪ 用户覆盖（用户没写的字段一律用默认值）。

    键名被淘汰的旧参数（R 基准的保本/追踪、预挂止盈的核对间隔等）直接丢弃：
    它们在新模型里没有对应语义，留着只会让「用户改过的值」静默失效。
    """
    raw = load_protection_config().get('position_protection', {}) or {}
    conf = dict(risk_model.V2_DEFAULTS)
    for key, value in raw.items():
        if value is None or key in risk_model.LEGACY_KEYS or _is_legacy_default(key, value):
            continue
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
        # 删行前先把上下文取出来：这里是「仓位怎么没的」唯一的现场证据
        state = ledger.load(symbol, side) or {}
        stop = _f(state.get('stop'))
        last = _f(state.get('last_price'))
        entry = _f((state.get('plan') or {}).get('entry'))
        contracts = _f(state.get('contracts'))
        msg, hit_stop = _describe_disappearance(side, stop, last, entry, contracts)
        ledger.delete(symbol, side)
        ledger.log_event(symbol, side, 'flat', msg,
                         level='warning' if hit_stop else 'info',
                         stop=stop or None, last_price=last or None,
                         entry=entry or None, contracts=contracts or None,
                         triggered_stop=hit_stop)
        # 静默删行 = 用户只能事后从交易所账单发现仓位没了。必须留痕 + 外发。
        V2.note_action(symbol, side, msg, 'warning' if hit_stop else 'info')
        if hit_stop:
            send_alert(
                conf, '风控提示: 兜底止损单已被交易所触发',
                f'[{symbol}] {side} STOP {stop:.8g} 触发，仓位 {contracts:.6g} 已全平'
                f'（最后价 {last:.8g}）',
                symbol=symbol)
        try:
            await engine._cancel_program_stops_for_flat(exchange, symbol, side, conf)
            await engine._cancel_bot_reduce_orders(
                exchange, symbol, side, conf, reason='仓位已平，清理旧减仓单')
            await tp_orders.cancel_all_tp_orders(
                exchange, symbol, side, conf, reason='仓位已平，清理止盈挂单')
        except Exception as exc:  # noqa: BLE001 - 清理失败不影响守护
            logger.warning(f'[{symbol}/{side}] 平仓后清理异常: {exc}')
        logger.info(f'[{symbol}/{side}] 🧹 仓位已消失：{msg}')

    for key in list(V2.disappeared_since):
        if key in active:
            V2.disappeared_since.pop(key, None)


def _describe_disappearance(side: str, stop: float, last: float, entry: float,
                            contracts: float) -> Tuple[str, bool]:
    """给「仓位消失」定性：是兜底 STOP 被交易所触发，还是被手动/其它任务平掉。

    判定依据：最后轮询价是否已贴到（或穿过）STOP 线。真实触发价无法事后反查
    （兜底单是条件市价，交易所侧成交），距 STOP 1% 以内即认定为止损触发；
    超出这个范围则如实标注「非兜底单触发」，避免把人工平仓误报成风控动作。
    """
    touched = stop > 0 and last > 0 and (
        last <= stop * (1 + _STOP_TOUCH_TOL) if side == 'long'
        else last >= stop * (1 - _STOP_TOUCH_TOL))
    if touched:
        gap = abs(last - stop) / stop
        entry_text = f'，开仓 {entry:.8g}' if entry > 0 else ''
        return (
            f'交易所兜底STOP {stop:.8g} 已触发（最后价 {last:.8g}，距线 {gap:.2%}{entry_text}），'
            f'仓位 {contracts:.6g} 由条件单市价全平', True)
    if stop > 0 and last > 0:
        return (
            f'仓位 {contracts:.6g} 已消失：最后价 {last:.8g} 距兜底STOP {stop:.8g} '
            f'还有 {abs(last - stop) / stop:.2%}，判定为手动/其它任务平仓', False)
    return f'仓位 {contracts:.6g} 已消失（本周期未记录STOP），判定为手动/其它任务平仓', False


# ---------------------------------------------------------------------------
# 单仓准备：拉数据 → 判断是否新周期 → 生成快照 → 决策
# ---------------------------------------------------------------------------
def _is_new_position(state: Optional[Dict[str, Any]], opened_ms: int) -> bool:
    """这笔仓位是不是「账本里那笔」以外的新仓位（新开 / 平掉重开）。

    只保留两个可信判据：开仓时间变了、开仓时间晚于账本建立时间。
    加仓/减仓**不是**新仓位——它由 risk_model.detect_intervention 处理成状态演化，
    整行重建会丢掉已触发档位与止损价（2026-11-15 那一串错位的根因）。
    """
    if not state or not isinstance(state.get('plan'), dict):
        return True
    old_opened = int(_f(state.get('opened_at_ms')))
    if opened_ms > 0 and old_opened > 0 and abs(opened_ms - old_opened) > 3000:
        return True
    # 引擎停机期间「平仓又重开」：账本记录的建立时间早于本次开仓时间
    created = _f(state.get('created_at'))
    if opened_ms > 0 and created > 0 and opened_ms / 1000.0 > created + 60:
        return True
    return False


def _maybe_replan(state: Dict[str, Any], plan: Dict[str, Any], structure,
                 atr: float, price: float, conf: Dict[str, Any],
                 now: float) -> Optional[Tuple[Dict[str, Any], str]]:
    """E 重估触发器：定时 / 波动率剧变，先到先触发；冷却期内一律跳过。

    返回 (new_plan, reason) 或 None。约束与重算范围见 risk_model.replan_plan。
    """
    if not bool(conf.get('replan_enabled', True)):
        return None
    if int(_f(plan.get('replan_count'))) >= 30:
        return None
    reference = _f(plan.get('replanned_at')) or _f(plan.get('built_at'))
    cooldown = max(0.0, _f(conf.get('replan_cooldown_sec'), 3600.0))
    if reference > 0 and now - reference < cooldown:
        return None

    atr_plan = _f(plan.get('atr_at_plan'))
    reason: Optional[str] = None
    if atr > 0 and atr_plan > 0:
        ratio = atr / atr_plan
        if ratio >= max(1.0, _f(conf.get('replan_atr_up_ratio'), 1.5)):
            reason = 'atr_jump'
        elif 0 < ratio <= max(0.01, _f(conf.get('replan_atr_down_ratio'), 0.6)):
            reason = 'atr_drop'
    if reason is None and reference > 0 \
            and now - reference >= max(cooldown, _f(conf.get('replan_interval_sec'), 86400.0)):
        reason = 'scheduled'
    if reason is None:
        return None

    try:
        new_plan = risk_model.replan_plan(
            plan, str(state.get('side') or plan.get('side') or 'long'),
            structure, atr, price, conf, now,
            risk_model._ints(state.get('tiers_done')), reason=reason)
    except Exception as exc:  # noqa: BLE001 - 重估失败不影响本轮守护
        logger.warning(f'replan 异常，跳过: {exc}')
        return None
    return (new_plan, reason) if new_plan else None


# 每个 (symbol|side) 上次核对交易所 STOP 的时间
LAST_STOP_VERIFY: Dict[str, float] = {}


def _build_plan_safe(side: str, entry: float, atr: float, structure, conf,
                     now: float, symbol: str) -> Dict[str, Any]:
    """建计划；参数写坏时退回默认值——绝不让仓位裸奔。"""
    try:
        return risk_model.build_plan(side, entry, atr, structure, conf, now=now)
    except Exception as exc:  # noqa: BLE001
        logger.error(f'[{symbol}/{side}] 风险计划参数非法，退回默认四档: {exc}')
        safe = dict(risk_model.V2_DEFAULTS)
        safe['tier_confirm_sec'] = conf.get('tier_confirm_sec', safe['tier_confirm_sec'])
        return risk_model.build_plan(side, entry, atr, structure, safe, now=now)


def _log_rebase(symbol: str, side: str, plan: Dict[str, Any], entry: float,
                contracts: float, reason: str, label: str) -> None:
    """风险基准重建的现场记录：加仓后「旧线 → 新线」是复盘止损错位的第一手证据。"""
    old_entry = _f(plan.get('entry'))
    ledger.log_event(symbol, side, 'rebase',
                     f'{label}；基准 {old_entry:.6g} → {entry:.6g}，持仓 {contracts:.6g}',
                     level='warning', reason=reason, entry=entry,
                     prev_entry=old_entry, contracts=contracts)
    logger.warning(f'[{symbol}/{side}] ♻️ {label}')


async def _exchange_stop_price(exchange, conf: Dict[str, Any], symbol: str, side: str,
                               pos: Dict[str, Any], price: float,
                               now: float) -> Optional[float]:
    """交易所上真实存在的保护 STOP 触发价：0 = 查过了、没有；None = 本轮没查。

    为什么必须查交易所而不是只信账本 state['stop']：账本记的是「我们上次挂了什么」，
    用户可以在币安 App 里把那张单撤掉或改价。只看账本会出两种错：
    · 手动撤单后永远不补挂 —— 决策算出的 desired 和账本里的旧价差不多，判定「无需推进」；
    · 止损上移永远和旧价比，交易所那边其实早就没有兜底单了。
    节流到 stop_verify_interval_sec（默认 15s），并复用 _find_stop_orders 的
    orders_cache（TTL 10s），所以每个 symbol 最多 15s 一次 openOrders。
    """
    if not bool(conf.get('exchange_hard_stop_enabled', True)):
        return None
    key = f'{symbol}|{side}'
    interval = max(0.0, _f(conf.get('stop_verify_interval_sec'), 15.0))
    last = LAST_STOP_VERIFY.get(key)
    if interval > 0 and last is not None and now - last < interval:
        return None
    LAST_STOP_VERIFY[key] = now
    try:
        stops = await engine._find_stop_orders(
            exchange, symbol, side, pos, price, conf, force=False)
    except Exception as exc:  # noqa: BLE001 - 查询失败退回账本口径，不影响本轮守护
        logger.warning(f'[{symbol}/{side}] 核对交易所保护STOP失败: {exc}')
        return None
    if not stops:
        return 0.0
    # 一仓多张 STOP 时取「最靠盈利方向」的那张作为真相，与 _apply_stop 的口径一致
    triggers = [float(t) for t in (engine._algo_trigger(o) for o in stops) if t]
    if not triggers:
        return 0.0
    return max(triggers) if side == 'long' else min(triggers)


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
    new_position = _is_new_position(state, opened_ms)
    rebased = False

    if new_position:
        plan = _build_plan_safe(side, entry, atr, structure, conf, now, symbol)
        prev = state or {}
        state = risk_model.new_state(uuid.uuid4().hex, side, entry, contracts, plan, now)
        state['opened_at_ms'] = int(opened_ms)
        state['position_version'] = 1
        # 新仓位第一轮先把交易所上残留的旧止盈单扫一遍（引擎重启/换周期都可能留下）
        state['tp_sweep_pending'] = True
        logger.info(
            f'[{symbol}/{side}] 🆕 建立风险计划 | 开仓:{entry:.6f} 持仓:{contracts:.6g} '
            f'ATR:{atr:.6f} R:{plan["risk"]:.6f}({plan["risk"] / entry:.2%}) | '
            f'四档:{"/".join(f"{x:.6f}" for x in plan["levels"])} | '
            f'灾难线:{plan["disaster_stop"]:.6f}({plan["disaster_pct"]:.2%})')
        ledger.log_event(symbol, side, 'cycle_new', '建立风险计划',
                         entry=entry, atr=atr, risk=plan['risk'], levels=plan['levels'],
                         disaster=plan['disaster_stop'], contracts=contracts)
        if prev and _f(prev.get('contracts')) > 0:
            ledger.log_event(symbol, side, 'cycle_reopen',
                             f'旧仓位 {_f(prev.get("contracts")):.6g} 已不在，'
                             f'按新仓位 {contracts:.6g} @ {entry:.6g} 重建',
                             level='warning', entry=entry)
    else:
        plan = state['plan']
        atr = atr or _f(plan.get('atr_at_plan'))

        # ---- 人工干预：加仓 / 减仓 / 旧版计划迁移 ----
        if int(_f(plan.get('version'))) < risk_model.PLAN_VERSION:
            rebased = True
            _log_rebase(symbol, side, plan, entry, contracts,
                        reason='plan_migrate', label='计划升级（旧版坐标系）')
        else:
            hit = risk_model.detect_intervention(state, side, contracts, entry, conf)
            if hit and hit['kind'] == 'add':
                rebased = True
                label = (f'人工/外部加仓 +{hit["delta_qty"]:.6g}（约 @{hit["implied_price"]:.6g}），'
                         f'均价 {hit["prev_entry"]:.6g} → {entry:.6g}')
                _log_rebase(symbol, side, plan, entry, contracts, reason='add', label=label)
                send_alert(conf, '仓位变动: 检测到加仓，已按新均价重算止损/止盈',
                           f'[{symbol}] {side} {label}；持仓 {contracts:.6g}，'
                           f'规模锚 {max(_f(state.get("size_anchor")), contracts):.6g}',
                           symbol=symbol)
            elif hit and hit['kind'] == 'reduce':
                note = (f'人工/外部减仓 {hit["delta_qty"]:.6g}'
                        f'（{hit["qty_pct"]:+.1%}），剩余 {contracts:.6g}')
                state.setdefault('interventions', []).append(
                    {'ts': now, 'kind': 'reduce', **{k: hit[k] for k in
                     ('delta_qty', 'qty_pct', 'prev_qty', 'prev_entry')}})
                state['interventions'] = state['interventions'][-20:]
                ledger.log_event(symbol, side, 'intervention', note, level='info',
                                 delta_qty=hit['delta_qty'], contracts=contracts)
                logger.info(f'[{symbol}/{side}] 👤 {note}')
                if abs(hit['qty_pct']) >= _f(conf.get('intervention_alert_pct'), 0.10):
                    send_alert(conf, '仓位变动: 检测到减仓',
                               f'[{symbol}] {side} {note}', symbol=symbol)

        if rebased:
            plan = risk_model.rebase_plan(plan, side, entry, atr, structure, conf, now) \
                or _build_plan_safe(side, entry, atr, structure, conf, now, symbol)
            state['plan'] = plan
            # 新阶梯要重新确认突破；已完成的档（tiers_done/tp_done）一律保留，不重复卖
            state['tp_armed'] = []
            state['pending'] = {}
            logger.info(
                f'[{symbol}/{side}] ♻️ 风险基准重建#{plan.get("rebase_count")} | '
                f'均价:{entry:.6f} R:{plan["risk"]:.6f} | '
                f'四档:{"/".join(f"{x:.6f}" for x in plan["levels"])} | '
                f'灾难线:{plan["disaster_stop"]:.6f} | 已完成 T'
                f'{"/".join(str(i + 1) for i in risk_model._ints(state.get("tiers_done"))) or "无"}'
                f' TP{"/".join(str(i + 1) for i in risk_model._ints(state.get("tp_done"))) or "无"}')
        else:
            # E 结构重估：定时 / ATR 剧变触发（先到先触发），重算未触发档位线与灾难线。
            # 约束（冻结/只外移/最小间距/R 锁定）全部在 risk_model.replan_plan 内实现；
            # dry_run 时只记事件不落盘，便于先观察重算结果是否合理。
            replan = _maybe_replan(state, plan, structure, atr, price, conf, now)
            if replan is not None:
                new_plan, reason = replan
                old_levels = [_f(x) for x in (plan.get('levels') or [])]
                old_disaster = _f(plan.get('disaster_stop'))
                moved = ' '.join(
                    f'T{i + 1} {o:.6g}->{n:.6g}'
                    for i, (o, n) in enumerate(zip(old_levels, new_plan['levels'])) if o != n)
                summary = f'重估#{new_plan["replan_count"]}({reason}): {moved or "档位未变"} ' \
                          f'灾难 {old_disaster:.6g}->{new_plan["disaster_stop"]:.6g} ATR {plan.get("atr_at_plan"):.6g}->{atr:.6g}'
                if bool(conf.get('dry_run', False)):
                    ledger.log_event(symbol, side, 'replan_dry', f'{summary}（dry_run，未落盘）',
                                     level='info', old_levels=old_levels,
                                     new_levels=new_plan['levels'])
                else:
                    state['plan'] = new_plan
                    plan = new_plan
                    logger.info(f'[{symbol}/{side}] 🔁 {summary}')
                    ledger.log_event(symbol, side, 'replan', summary, level='info',
                                     old_levels=old_levels, new_levels=new_plan['levels'],
                                     old_disaster=old_disaster,
                                     new_disaster=new_plan['disaster_stop'])

    # 止盈口径迁移：旧版本把 reduceOnly 限价单预挂在交易所，价格一碰 TP 就被撮合，
    # 「先突破、再回落」根本来不及判断。现在全部交给引擎（3s 一轮），旧单必须撤掉。
    if state.get('tp_mode') != 'engine':
        state['tp_mode'] = 'engine'
        state['tp_sweep_pending'] = True

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

    # 交易所 STOP 事实核对（节流）：以交易所为准，才能发现「用户手动撤了/改了」
    exchange_stop = await _exchange_stop_price(exchange, conf, symbol, side, pos, price, now)

    snap = risk_model.Snapshot(
        symbol=symbol, side=side, entry=_f(plan.get('entry'), entry),
        price=price, last_close=last_close, contracts=contracts,
        atr=atr, structure=structure, closed_ts=closed_ts, now=now,
        exchange_stop=float(exchange_stop or 0.0),
        exchange_checked=exchange_stop is not None,
        rebased=rebased,
        base_contracts=_f(state.get('size_anchor'), contracts),
    )

    decision = risk_model.decide(state, snap, conf)

    # 黑天鹅：独立一支，命中直接压过所有结构/止盈动作
    emergency = await _check_emergency(exchange, conf, symbol, side, state, snap)
    if emergency:
        decision['actions'] = [emergency]

    state.update(decision.get('patch') or {})
    # 仓位以交易所为唯一真值：手动平一部分不会经过 _apply_reduce，
    # 账本里的 contracts 不跟着同步，前端和日志就会一直显示旧仓位。
    state['contracts'] = contracts
    # 干预检测的基线：本轮看到的交易所事实。下一轮拿它比对，就能把
    # 「平均成本变了 = 加过仓」「量变少了 = 减过仓」这两件事分辨出来。
    state['q_seen'] = contracts
    state['e_seen'] = entry
    state['size_anchor'] = risk_model.size_anchor(state, contracts)
    state['exchange_entry'] = entry
    state['last_price'] = price
    state['last_atr'] = atr
    if new_position or rebased:
        ledger.save(symbol, side, state)

    return {
        'symbol': symbol, 'side': side, 'pos': pos, 'state': state,
        'snap': snap, 'actions': decision.get('actions') or [],
    }


async def _check_emergency(exchange, conf: Dict[str, Any], symbol: str, side: str,
                           state: Dict[str, Any], snap: risk_model.Snapshot) -> Optional[Dict[str, Any]]:
    if not bool(conf.get('emergency_enabled', True)):
        return None
    interval = max(5.0, _f(conf.get('emergency_check_interval_sec'), 20.0))
    last = _f(state.get('last_emergency_check'))
    if last and snap.now - last < interval:
        return None
    state['last_emergency_check'] = snap.now
    # 把「本仓入场价 / 入场时间」带进信号：位移只按持仓期间那段行情算，
    # 否则「崩盘途中开仓 → 拿入场前的跌幅判自己闪崩」会立刻全平（2026-11-14 ETH）。
    opened_ms = _f(state.get('opened_at_ms'))
    entry_ts = opened_ms / 1000.0 if opened_ms > 0 else _f(state.get('created_at'))
    try:
        triggered, details = await engine._emergency_signal(
            exchange, symbol, side, conf,
            entry_price=_f(snap.entry), entry_ts=entry_ts)
    except Exception as exc:  # noqa: BLE001 - 单次失败不阻断主循环
        logger.debug(f'[{symbol}] 黑天鹅检查异常: {exc}')
        return None
    if not triggered or not details:
        return None
    ok, _ = await engine._two_source_price_ok(exchange, symbol, details.get('ws_price', 0), side, conf)
    if not ok:
        return None
    # 带上实际位移与阈值：出问题时这一条就能自证，不必再翻容器日志
    scope = '入场后位移' if details.get('anchored_at_entry') else '本根位移'
    reason = (
        f"黑天鹅 {details.get('reason', '异常波动')}"
        f"（{scope} {_f(details.get('move')):.4g} / 阈值 {_f(details.get('threshold')):.4g}）"
    )
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
        # 双源价差是插针行情下的常态，不是交易所故障：用短冷却快速重试。
        # 原来入口处已写入 attempts[tag]=now，等于 90s 才允许再试——减仓会被这一段
        # 卡到价格回落后才成交，用户看到的就是「回调了才减仓」。
        attempts[tag] = now - cooldown + max(1.0, _f(conf.get('reduce_retry_fast_sec'), 10.0))
        return

    fresh = await engine._position_fresh(exchange, symbol, side, conf, priority='HIGH')
    if not fresh:
        ledger.delete(symbol, side)
        bundle['_exited'] = True
        return
    current = engine._position_size(fresh)

    if act['type'] == 'exit' or _f(act.get('ratio')) >= 0.999:
        reason = str(act.get('reason') or '保护性全平')
        success, _ = await engine._full_exit_with_revalidation(
            exchange, symbol, side, fresh, reason, conf, state)
        if success:
            ledger.log_event(symbol, side, 'exit', reason, level='error',
                             before=current, after=0.0, tag=tag)
            ledger.delete(symbol, side)
            bundle['_exited'] = True
            # 仓位没了，交易所上残留的止盈挂单必须一起撤：reduceOnly 单在无仓位时
            # 会被拒/悬挂，留着下次开仓会继承一张「价格早已越过」的旧单。
            await tp_orders.cancel_all_tp_orders(exchange, symbol, side, conf,
                                                 reason='全平后清理止盈挂单')
            V2.note_action(symbol, side, reason, 'error')
            # 全平是仓位保护里最重的动作，必须外发：此前这里只写台账，
            # 钉钉与前端日志都收不到，用户只能事后从交易所账单里发现仓位没了。
            send_alert(conf, f"风控警告: {reason}",
                       f"[{symbol}] {side} 已市价全平 {current:.6g} → 0", symbol=symbol)
            # 黑天鹅是「状态型」信号：一根 K 线跌够幅度后，在它走完前每次开仓都会命中。
            # 记一段同币冷却，防开仓计划/信号在同一个崩盘窗口里反复建仓（开了 16 秒又被平）。
            if tag == 'emergency':
                cooldown.note_emergency_flat(symbol, side, reason, conf)
        else:
            # 全平失败 = 仓位仍在裸奔，同样必须外发，不能静默
            logger.error(f'[{symbol}] 全平未完成（{reason}），仓位仍在 {current:.6g}，下轮重试')
            ledger.log_event(symbol, side, 'error', f'{reason} 全平未完成，仓位仍为 {current:.6g}',
                             level='error', before=current, tag=tag)
            send_alert(conf, f"风控警告: {reason} 全平未完成",
                       f"[{symbol}] {side} 全平未成交，仓位仍为 {current:.6g}，请人工确认",
                       symbol=symbol)
        return

    tiers = act.get('tiers') or []
    tps = act.get('tps') or []

    # 卖出量由决策层算好（规模锚 × 档位比例，且不超过「当前持仓 ×(1−保留比例)」）。
    # 这里再用刚拉到的最新持仓夹一次：决策到下单之间可能已经被人平掉一部分。
    qty = min(current, _f(act.get('qty')))
    if qty <= 0:
        return

    maker_only = True
    if tiers:
        maker_only = (max(tiers) + 1) <= int(_f(conf.get('tier_maker_only_until'), 2))

    await engine._cancel_bot_reduce_orders(exchange, symbol, side, conf, reason=f'{tag}前')
    _, after = await engine._limit_reduce_with_maker_retry(
        exchange, symbol, side, fresh, qty, act.get('reason', '保护性减仓'), conf,
        int(_f(state.get('position_version'), 1)), state,
        max_retries=int(_f(conf.get('tier_maker_retries'), 3)),
        check_interval_sec=1.0, timeout_sec=10.0,
        marketable_retries=int(_f(conf.get('tier_marketable_retries'), 3)),
        # B 三级降级：maker(GTX) → 吃单价 → 市价兜底。市价只在最后一级。
        allow_market_fallback=bool(conf.get('reduce_market_fallback', True)),
        maker_only=maker_only,
        # 止盈不排队等 maker：价格已经跌破 TP，挂在盘口上方只会越等越低，
        # 最后变成「回撤之后才卖」。直接以可成交价出手，吃掉 TP 附近的这段。
        skip_maker=bool(tps),
    )

    if after >= current - max(1e-12, current * 1e-8):
        logger.warning(f'[{symbol}] {tag} 未成交（{current} -> {after}），保留档位下轮重试')
        # 止盈未成交必须留痕：这是「价格到过目标位却没卖掉」的唯一证据。
        if tps:
            ledger.log_event(symbol, side, 'skip',
                             f"{act.get('reason') or tag} 未成交（{current:.6g} → {after:.6g}），"
                             f"下轮重试", level='warning', trigger=tag, tps=tps)
        # C 冷却分级：未成交 ≠ 交易所异常。行情在跑，未成交用短冷却快速重试；
        # 交易所报错走异常路径，仍按 action_retry_cooldown_sec(90s) 冷却。
        attempts[tag] = now - cooldown + max(1.0, _f(conf.get('reduce_retry_fast_sec'), 10.0))
        ledger.save(symbol, side, state)
        return

    state['contracts'] = after
    # 我们自己的成交也要同步基线：否则下一轮的干预检测会把这次减仓
    # 误判成「人工减仓」，白写一条事件、白发一条提示。
    state['q_seen'] = after
    state['size_anchor'] = risk_model.size_anchor(state, after)
    state['position_version'] = int(_f(state.get('position_version'), 1)) + 1
    if tiers:
        state['tiers_done'] = sorted(set(risk_model._ints(state.get('tiers_done'))) | set(tiers))
    if tps:
        state['tp_done'] = sorted(set(risk_model._ints(state.get('tp_done'))) | set(tps))
    state['last_action_ts'] = now
    ledger.save(symbol, side, state)

    text = f"{act.get('reason')}：{current:.6g} → {after:.6g}（实减 {current - after:.6g}）"
    ledger.log_event(symbol, side, 'reduce', text, level=str(act.get('level') or 'warning'),
                     ratio=act.get('ratio'), after=after, tiers=tiers, tps=tps)
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

    # 补挂前强制刷新一次：条件单列表可能有秒级延迟，若刚补上的那张还没出现在缓存里，
    # 直接用缓存会重复创建，很快变成「一仓多张 STOP」。
    tag = str(act.get('tag') or '')
    force = bool(act.get('force'))
    stops = await engine._find_stop_orders(
        exchange, symbol, side, pos, snap.price, conf, force=force or tag == 'stop:restore')
    if stops:
        # 一仓多张 STOP 时以「最靠盈利方向」的那张为准，其余全部撤掉
        triggers = [float(t) for t in (engine._algo_trigger(o) for o in stops) if t]
        current = (max(triggers) if side == 'long' else min(triggers)) if triggers else None
        if current is not None and not force:
            better = desired > current if side == 'long' else desired < current
            if not better:
                # 交易所已有更优的兜底单：以它为准，账本同步
                if abs(_f(state.get('stop')) - current) > 1e-9:
                    state['stop'] = current
                    ledger.save(symbol, side, state)
                return
        await engine._cancel_stop_orders(exchange, symbol, stops, conf)

    await engine._create_full_close_stop(exchange, symbol, pos, side, desired, conf)
    state['stop'] = desired
    ledger.save(symbol, side, state)
    # 记「建立」还是「上移」，并带上上一档：这条事件就是日后复盘
    # 「止损怎么被推到保本、然后被扫掉」的唯一凭据
    previous = _f(act.get('previous_stop'))
    label = str(act.get('reason') or '兜底STOP')
    ledger.log_event(symbol, side, 'stop',
                     f'{label} {desired:.8g}' + (f'（原 {previous:.8g}）' if previous > 0 else ''),
                     level='info', price=desired, trigger=str(act.get('tag') or ''))
    # 补挂是「仓位曾经裸奔过」的信号，必须推送：用户手动撤单后通常不会再回来看页面
    if str(act.get('tag') or '') == 'stop:restore':
        send_alert(conf, '⚠️ 交易所止损单已不在，已重新挂出',
                   f'[{symbol}] 兜底 STOP {desired:.8g}'
                   + (f'（账本原记 {previous:.8g}）' if previous > 0 else ''),
                   symbol=symbol)


# ---------------------------------------------------------------------------
# 遗留清理：止盈不再预挂到交易所
# ---------------------------------------------------------------------------
# 止盈改回「引擎每 3 秒判断：先突破、再回落才卖」。交易所上遗留的止盈单
# （旧版本留下的 PM_WS_TP_ 前缀 reduceOnly 限价单）会抢在引擎前面成交——
# 价格刚碰到 TP 就被撮合掉，突破回落的判断等于失效。所以每个仓位/周期只清一次。
async def _sweep_legacy_tp_orders(exchange, conf: Dict[str, Any],
                                  bundle: Dict[str, Any]) -> None:
    state = bundle['state']
    if not state.pop('tp_sweep_pending', False):
        return
    try:
        await tp_orders.cancel_all_tp_orders(
            exchange, bundle['symbol'], bundle['side'], conf,
            reason='止盈改为程序判定（突破→回落），清理交易所上的旧止盈单')
        state.pop('tp_order', None)
    except Exception as exc:  # noqa: BLE001 - 清理失败不影响守护，下轮还会重试
        logger.warning(f"[{bundle['symbol']}] 清理旧止盈挂单失败: {exc}")
        state['tp_sweep_pending'] = True


async def _execute(exchange, conf: Dict[str, Any], bundle: Dict[str, Any]) -> None:
    symbol, side = bundle['symbol'], bundle['side']
    actions = bundle['actions']
    # 有遗留止盈单就先撤掉：交易所上的单会抢在引擎判断之前成交
    await _sweep_legacy_tp_orders(exchange, conf, bundle)
    if not actions:
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
    logger.info(f'🎯 止盈 | 阶梯:{conf.get("tp_r_multiples")}R | 比例:{conf.get("tp_ratios")} '
                f'| 保留:{conf.get("tp_keep_ratio")} | 触发:突破 '
                f'+{_f(conf.get("tp_breakout_confirm_pct"), 0.001):.3%} 后回落（引擎 3s 判定）')
    logger.info(f'🛑 止损 | T1 距离 {_f(conf.get("risk_min_pct"), 0.015):.2%}~'
                f'{_f(conf.get("t1_max_pct"), 0.04):.2%} | 灾难线 {_f(conf.get("risk_max_pct"), 0.06):.2%}'
                f' | 保本 {_f(conf.get("breakeven_trigger_atr"), 2.0):.1f}ATR'
                f' | 追踪 {_f(conf.get("trailing_start_atr"), 2.5):.1f}ATR'
                f'/{_f(conf.get("trailing_atr_mult"), 1.5):.1f}ATR')

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
        armed = set(risk_model._ints(state.get('tp_armed')))
        # 止盈不再挂到交易所，前端要区分三种状态：
        #   待突破（还没越过 TP）/ 待回落（已突破，等价格回到 TP）/ 已完成
        tp_wait_level = next((i + 1 for i in range(len(tps))
                              if i not in tp_done and i not in armed and tps[i]), None)
        tp_armed_level = next((i + 1 for i in range(len(tps))
                               if i not in tp_done and i in armed and tps[i]), None)
        rows.append({
            'symbol': symbol,
            'side': side,
            'contracts': state.get('contracts'),
            'entry_price': plan.get('entry'),
            # 交易所真实均价（计划 entry 建周期时锁定；两者不等 = 加仓/重开未被识别）
            'exchange_entry': state.get('exchange_entry'),
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
            # 止盈状态：引擎自己判断（3s 一轮），交易所上没有对应的挂单
            'tp_wait_level': tp_wait_level,      # 还没突破的下一档（等价格越过）
            'tp_armed_level': tp_armed_level,    # 已突破、等回落到 TP 就卖
            'tp_order_level': None,              # 兼容旧前端字段：不再预挂，恒为 None
            'tp_order_price': None,
            # v2 专属：四档线、R、灾难线、规模锚
            'engine': 'v2',
            'cycle_id': state.get('cycle_id'),
            'risk': plan.get('risk'),
            'tier_levels': levels,
            'disaster_stop': plan.get('disaster_stop'),
            'disaster_pct': plan.get('disaster_pct'),
            # 分批比例的分母：历史最大持仓。人工加仓后它会跟进，减仓不会缩。
            'size_anchor': state.get('size_anchor'),
            'base_contracts': state.get('size_anchor'),
            'rebase_count': plan.get('rebase_count'),
            'interventions': state.get('interventions') or [],
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
