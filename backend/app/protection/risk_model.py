# backend/app/protection/risk_model.py
"""仓位保护 v2：纯决策模型（无 IO、无交易所调用）。

为什么单独拆一层
- v1 把「判断」和「下单」揉在一个 500 行的协程里，改一个阈值都要连交易所一起想，
  参数也没法离线验证。这里把判断抽成纯函数：输入「仓位快照 + 风险周期状态」，
  输出「动作列表」，可以单测、可以拿历史 K 线回放。

坐标约定
- long : 四档减仓线严格递减  t1 > t2 > t3 > t4，灾难线在 t4 之下；
- short: 四档减仓线严格递增  t1 < t2 < t3 < t4，灾难线在 t4 之上；
- 所有 ratio 都是「占本风险周期初始仓位」的比例，四档合计 = 1.0；
- R = |开仓价 - T1|，止盈与保本都以 R 为单位，避免不同币波动率下参数失真。

优先级（同一轮只出一个减仓动作）
1. 击穿灾难线     -> 全平（不确认、不等收盘）
2. 击穿结构档位   -> 累计减仓（实时价 + 持续确认）
3. 到达止盈档位   -> 累计止盈
4. 止损上移       -> 与上面独立，永远重算，且只允许朝盈利方向移动
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

EPS = 1e-12
MIN_REMAINING = 0.02  # 低于 2% 视为已平，不再下单


# ---------------------------------------------------------------------------
# 默认参数（用户配置深合并在 runner.load_config 里完成）
# ---------------------------------------------------------------------------
V2_DEFAULTS: Dict[str, Any] = {
    'engine_version': 'v2',
    'dry_run': False,
    'v2_timeframe': '2h',
    'v2_poll_interval_sec': 3.0,
    'v2_decision_concurrency': 4,
    # 四档减仓：越破越重，合计 100%
    'tier_ratios': [0.15, 0.20, 0.25, 0.40],
    # 每档参考的结构回看根数（最后一档与第三档同源，只靠 ATR 缓冲拉远）
    'tier_lookbacks': [7, 26, 83, 83],
    'tier_atr_buffer': 0.5,
    'tier_min_gap_atr': 0.8,
    # 每档的「持续确认」秒数；0 = 立即触发（灾难档）
    'tier_confirm_sec': [30, 45, 60, 0],
    # 破位深度分级（A）：实时价越过档位线 X 个 ATR 时，按档衰减确认秒数。
    # 深度 >= fast_depth_atr[k] -> 确认秒数 *= fast_confirm_mult[k+1]。
    # 2026-11 历史标定（BTC/ETH/SOL/DOGE 1m 回放，tools/sl_calibration/）：
    # 破 T1 后 30s 内继续深入 >=1.5 ATR 的概率 8%（T2 12%），p90 额外损失 1.4 ATR——
    # 该尾部即急速破位，直接跳过确认；<0.5 ATR 的浅破位维持原确认防噪声。
    'tier_fast_depth_atr': [0.5, 1.0, 1.5],
    'tier_fast_confirm_mult': [1.0, 0.5, 0.25, 0.0],
    'risk_min_pct': 0.015,
    'risk_max_pct': 0.08,
    # 交易所 STOP 只做兜底：放在灾难线再往外 1.5 ATR，保证内部四档先动作
    'disaster_atr_buffer': 1.5,
    'tp_r_multiples': [1.0, 2.0, 3.0],
    'tp_ratios': [0.25, 0.30, 0.30],
    # TP 单轮单档（D）：同一轮巡检最多触发一个 TP 档。
    # 标定：首次触 TP 的 1m 里 ~50% 是插针（收盘回线下），且插针后 4h 内 93~96% 会再次触及——
    # 单轮单档让插针只卖掉第一档、保留阶梯，真突破也只多等 3s/档。
    'tp_one_level_per_round': True,
    # 执行层（B/C）：
    'tier_marketable_retries': 3,     # maker 失败后吃单价重试次数
    'reduce_market_fallback': True,   # 吃单价也失败后允许市价兜底（三级降级最后一级）
    'reduce_retry_fast_sec': 10.0,    # 减仓未成交的快速重试冷却（交易所异常仍用 90s）
    'breakeven_trigger_r': 0.5,
    'breakeven_buffer_pct': 0.002,
    'profit_lock_buffer_pct': 0.001,
    'trailing_start_r': 1.0,
    'trailing_atr_mult': 2.5,
    'stop_min_update_pct': 0.0015,
    'stop_min_update_atr_ratio': 0.15,
    'action_retry_cooldown_sec': 90.0,
    'tier_maker_retries': 3,
    'tier_maker_only_until': 2,
    'tp_keep_ratio': 0.15,
    'emergency_enabled': True,
    'emergency_timeframe': '15m',
    'emergency_atr_multiplier': 3.0,
    'emergency_atr_period': 14,
    'emergency_structure_lookback': 4,
    # 「放量」门槛：本根 15m 量需超过过去 20 根（有成交 K 线）均量的倍数。
    # 原默认 1.0 等于「高于平均即算放量」，几乎不过滤——2026-11-13 TQQQ/NVDA 误杀即由此来。
    'emergency_vol_multiplier': 3.0,
    # 放量分支（无结构确认）的位移门槛倍数：比结构分支更严，因为少了破位确认这道关。
    'emergency_vol_atr_multiplier': 4.0,
    # 位移的绝对下限（占价格比例）：兜住「ATR 被窄幅整理压低 → 一根中等 K 线成数倍 ATR」。
    # 2026-11-13 AAPL 三倍 ATR 仅 0.63%，一根 0.67% 回落即被全平；1% 可挡住而真闪崩仍触发。
    'emergency_min_move_pct': 0.01,
    'flat_confirm_sec': 30.0,
    # E 结构重估（docs/v2-replan-design.md）：持仓期间周期性重算档位线/灾难线。
    # 已触发档冻结、未触发档只许外移（评审定稿）、灾难线与现价保持 buffer*ATR。
    'replan_enabled': True,
    'replan_interval_sec': 86400.0,   # 定时触发：距上次重估/建仓 24h
    'replan_atr_up_ratio': 1.5,       # 波动率放大触发
    'replan_atr_down_ratio': 0.6,     # 波动率萎缩触发
    'replan_cooldown_sec': 3600.0,    # 重估后 1h 内不再重估（防抖）
}


@dataclass(frozen=True)
class Snapshot:
    """一轮巡检拿到的、判断所需要的全部市场事实。"""
    symbol: str
    side: str                 # 'long' | 'short'
    entry: float              # 本周期开仓均价
    price: float              # 当前标记价
    last_close: float         # 最近一根已收盘 K 线的收盘价
    contracts: float          # 当前持仓数量
    base_contracts: float     # 本周期初始持仓数量
    atr: float
    structure: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # 7/26/83 根结构位
    closed_ts: int = 0
    now: float = 0.0


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _floats(value: Any, fallback: Sequence[float]) -> List[float]:
    if not isinstance(value, (list, tuple)) or len(value) != len(fallback):
        return [float(x) for x in fallback]
    try:
        return [float(x) for x in value]
    except (TypeError, ValueError):
        return [float(x) for x in fallback]


def _ints(value: Any) -> List[int]:
    if not isinstance(value, (list, tuple, set)):
        return []
    out: List[int] = []
    for item in value:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def _beyond(price: float, level: float, side: str) -> bool:
    """价格是否已经越过某条线（long 向下破，short 向上破）。"""
    return price <= level if side == 'long' else price >= level


def floating_r(entry: float, risk: float, side: str, price: float) -> Optional[float]:
    if risk <= 0 or entry <= 0 or price <= 0:
        return None
    return ((price - entry) / risk) if side == 'long' else ((entry - price) / risk)


# ---------------------------------------------------------------------------
# 风险计划：一个仓位在每个风险周期开始时只算一次
# ---------------------------------------------------------------------------
def build_plan(side: str, entry: float, atr: float,
               structure: Sequence[float], conf: Dict[str, Any],
               now: float = 0.0) -> Dict[str, Any]:
    """把结构位 + ATR 折算成四档减仓线、R、止盈价和交易所兜底线。

    结构决定「在哪减」，ATR 决定「破多远才算破」；两者相乘做缓冲，
    所以波动放大时减仓线自动拉远，缩小时自动收紧，不需要分币种调参。
    """
    if side not in ('long', 'short'):
        raise ValueError(f'非法方向: {side}')
    if entry <= 0 or atr <= 0:
        raise ValueError('entry/atr 必须为正')
    if len(structure) != 3:
        raise ValueError('structure 需要 7/26/83 三档结构位')

    ratios = _floats(conf.get('tier_ratios'), V2_DEFAULTS['tier_ratios'])
    ratios = [max(0.0, x) for x in ratios]
    total = sum(ratios)
    if total <= 0:
        raise ValueError('tier_ratios 合计必须大于 0')
    ratios = [x / total for x in ratios]  # 归一化，避免用户填出 120%

    buffer_mult = max(0.0, _f(conf.get('tier_atr_buffer'), 0.5))
    gap_mult = max(0.1, _f(conf.get('tier_min_gap_atr'), 0.8))

    s1, s2, s3 = (float(x) for x in structure)

    # 候选线：结构位外侧再加 ATR 缓冲；越深的一档缓冲越宽，避免四档挤在一起
    if side == 'long':
        raw = [s1 - atr * buffer_mult,
               s2 - atr * buffer_mult * 1.2,
               s3 - atr * buffer_mult * 1.6,
               s3 - atr * buffer_mult * 3.0]
    else:
        raw = [s1 + atr * buffer_mult,
               s2 + atr * buffer_mult * 1.2,
               s3 + atr * buffer_mult * 1.6,
               s3 + atr * buffer_mult * 3.0]

    # T1 必须落在 [risk_min_pct, risk_max_pct]：太近会被噪声扫掉，太远单笔风险失控
    min_pct = max(0.0, _f(conf.get('risk_min_pct'), 0.015))
    max_pct = max(min_pct + 0.001, _f(conf.get('risk_max_pct'), 0.08))
    if side == 'long':
        t1 = min(max(raw[0], entry * (1.0 - max_pct)), entry * (1.0 - min_pct))
    else:
        t1 = max(min(raw[0], entry * (1.0 + max_pct)), entry * (1.0 + min_pct))

    levels = [float(t1)]
    unit = atr * gap_mult
    for i in (1, 2, 3):
        # 距开仓价至少 (i+1) 个 ATR 间距；再与上一档拉开半个间距，保证严格单调
        if side == 'long':
            cand = min(raw[i], entry - unit * (i + 1))
            cand = min(cand, levels[-1] - unit * 0.5)
        else:
            cand = max(raw[i], entry + unit * (i + 1))
            cand = max(cand, levels[-1] + unit * 0.5)
        levels.append(float(cand))

    risk = abs(entry - levels[0])

    tp_mults = _floats(conf.get('tp_r_multiples'), V2_DEFAULTS['tp_r_multiples'])
    if not (0 < tp_mults[0] < tp_mults[1] < tp_mults[2]):
        tp_mults = [1.0, 2.0, 3.0]
    tp_ratios = _floats(conf.get('tp_ratios'), V2_DEFAULTS['tp_ratios'])
    keep = max(0.0, min(0.9, _f(conf.get('tp_keep_ratio'), 0.15)))
    tp_ratios = [max(0.0, x) for x in tp_ratios]
    tp_total = sum(tp_ratios)
    if tp_total > (1.0 - keep):
        scale = (1.0 - keep) / tp_total
        tp_ratios = [x * scale for x in tp_ratios]

    if side == 'long':
        tp_prices = [entry + risk * m for m in tp_mults]
        disaster = levels[3] - atr * max(0.0, _f(conf.get('disaster_atr_buffer'), 1.5))
    else:
        tp_prices = [entry - risk * m for m in tp_mults]
        disaster = levels[3] + atr * max(0.0, _f(conf.get('disaster_atr_buffer'), 1.5))

    return {
        'entry': float(entry),
        'risk': float(risk),
        'levels': levels,
        'ratios': ratios,
        'tp_prices': [float(x) for x in tp_prices],
        'tp_ratios': tp_ratios,
        'disaster_stop': float(disaster),
        'atr_at_plan': float(atr),
        'built_at': float(now or 0.0),
    }


# ---------------------------------------------------------------------------
# E 结构重估：持仓期间重算档位线与灾难线（docs/v2-replan-design.md）
# ---------------------------------------------------------------------------
def replan_plan(plan: Dict[str, Any], side: str, structure: Sequence[float],
                atr: float, current_price: float, conf: Dict[str, Any],
                now: float, tiers_done: Sequence[int],
                reason: str = 'scheduled') -> Optional[Dict[str, Any]]:
    """重算未触发档位线与灾难线，返回新的 plan 副本；无需/不安全重估时返回 None。

    硬约束（评审定稿，逐条可单测）：
    1. 已触发档位冻结，不参与重算；
    2. 未触发档位只许外移（long：新线 <= 旧线；short 对称）——内移会在重算瞬间
       造成「价格已在线外」的假破位，等于自动在回调低点触发减仓；
    3. 档位间保持单调 + 最小间距；灾难线与现价保持 disaster_atr_buffer*ATR；
    4. entry/risk/tp_prices 等 R 语义字段终身锁定，一律沿用旧 plan；
    5. 重估本身只返回 plan，不发任何交易动作。
    """
    if not bool(conf.get('replan_enabled', True)):
        return None
    entry = _f(plan.get('entry'))
    risk = _f(plan.get('risk'))
    old_levels = [_f(x) for x in (plan.get('levels') or [])]
    if entry <= 0 or risk <= 0 or atr <= 0 or current_price <= 0 or len(old_levels) != 4:
        return None
    if len(structure) != 3 or len(set(float(x) for x in structure)) < 2:
        return None  # 结构退化（ATR 兜底路径），重算无意义
    if int(_f(plan.get('replan_count'))) >= 30:
        return None  # 异常熔断：正常 24h 一次远用不到

    try:
        fresh = build_plan(side, entry, atr, structure, conf, now=_f(plan.get('built_at')))
    except Exception:
        return None

    done = set(_ints(tiers_done))
    merged = list(old_levels)
    for i in range(4):
        if i in done:
            continue  # 约束 1：已触发档冻结
        new_lv = _f(fresh['levels'][i])
        # 约束 2：只许外移（远离现价），内移沿用旧线
        if side == 'long' and new_lv < merged[i]:
            merged[i] = new_lv
        elif side == 'short' and new_lv > merged[i]:
            merged[i] = new_lv

    # 约束 3：单调 + 最小间距（从浅到深逐档推；未触发档不得被推回内移方向）
    unit = atr * max(0.1, _f(conf.get('tier_min_gap_atr'), 0.8))
    for i in (1, 2, 3):
        if side == 'long':
            if merged[i] > merged[i - 1] - unit * 0.5:
                merged[i] = merged[i - 1] - unit * 0.5
            if i not in done and merged[i] > old_levels[i]:
                merged[i] = old_levels[i]
        else:
            if merged[i] < merged[i - 1] + unit * 0.5:
                merged[i] = merged[i - 1] + unit * 0.5
            if i not in done and merged[i] < old_levels[i]:
                merged[i] = old_levels[i]

    # 灾难线：跟新 T4 重建，且与现价保持最小距离（防止重估把它拉到现价附近误杀全平）
    buffer = max(0.0, _f(conf.get('disaster_atr_buffer'), 1.5))
    if side == 'long':
        disaster = min(merged[3] - atr * buffer, current_price - atr * buffer)
    else:
        disaster = max(merged[3] + atr * buffer, current_price + atr * buffer)

    changed = merged != old_levels or abs(disaster - _f(plan.get('disaster_stop'))) > EPS
    atr_changed = abs(atr - _f(plan.get('atr_at_plan'))) > atr * 0.01
    if not changed and not atr_changed:
        return None

    new_plan = dict(plan)
    new_plan['levels'] = [float(x) for x in merged]
    new_plan['disaster_stop'] = float(disaster)
    new_plan['atr_at_plan'] = float(atr)
    new_plan['replanned_at'] = float(now)
    new_plan['replan_count'] = int(_f(plan.get('replan_count'))) + 1
    new_plan['replan_reason'] = str(reason)
    return new_plan


def new_state(cycle_id: str, side: str, entry: float, base_contracts: float,
              plan: Dict[str, Any], now: float) -> Dict[str, Any]:
    return {
        'cycle_id': cycle_id,
        'side': side,
        'base_contracts': float(base_contracts),
        'contracts': float(base_contracts),
        'version': 1,
        'plan': plan,
        'tiers_done': [],
        'tp_done': [],
        'pending': {},
        'stop': None,
        'peak': float(entry),
        'trough': float(entry),
        'opened_at_ms': 0,
        'created_at': float(now),
        'updated_at': float(now),
        'attempts': {},
    }


# ---------------------------------------------------------------------------
# 决策
# ---------------------------------------------------------------------------
def _remaining_ratio(state: Dict[str, Any], snap: Snapshot) -> float:
    base = _f(state.get('base_contracts'), snap.base_contracts) or snap.base_contracts
    if base <= 0:
        return 0.0
    return max(0.0, min(1.0, snap.contracts / base))


def decide(state: Dict[str, Any], snap: Snapshot, conf: Dict[str, Any]) -> Dict[str, Any]:
    """核心决策：返回 {'actions': [...], 'patch': {...}}。

    patch 由调用方合并回状态并落库；actions 由调用方按顺序执行。
    纯函数：同样的 state + snap + conf 一定得到同样的结果。
    """
    plan = state.get('plan') or {}
    levels = [_f(x) for x in (plan.get('levels') or [])]
    entry = _f(plan.get('entry'))
    risk = _f(plan.get('risk'))
    side = snap.side
    price = _f(snap.price)
    now = _f(snap.now)

    if len(levels) != 4 or entry <= 0 or risk <= 0 or price <= 0:
        return {'actions': [], 'patch': {}, 'reason': 'plan_invalid'}

    remaining = _remaining_ratio(state, snap)
    patch: Dict[str, Any] = {}

    # 跟踪极值，供移动止损使用（只在本周期内累积）
    patch['peak'] = max(_f(state.get('peak'), entry), price)
    patch['trough'] = min(_f(state.get('trough'), entry), price)

    tiers_done = set(_ints(state.get('tiers_done')))
    tp_done = set(_ints(state.get('tp_done')))
    pending = {str(k): _f(v) for k, v in (state.get('pending') or {}).items()}
    ratios = _floats(plan.get('ratios'), V2_DEFAULTS['tier_ratios'])
    confirm_secs = _floats(conf.get('tier_confirm_sec'), V2_DEFAULTS['tier_confirm_sec'])
    tp_prices = [_f(x) for x in (plan.get('tp_prices') or [])]
    tp_ratios = _floats(plan.get('tp_ratios'), V2_DEFAULTS['tp_ratios'])

    # ---------- 1. 灾难线：不确认、不等收盘，直接全平 ----------
    disaster = _f(plan.get('disaster_stop'))
    if disaster > 0 and _beyond(price, disaster, side):
        patch['pending'] = {}
        return {
            'actions': [{
                'type': 'exit', 'ratio': remaining, 'tag': 'disaster',
                'level': 'error',
                'reason': f'击穿灾难线 {disaster:.8g}',
            }],
            'patch': patch,
        }

    # ---------- 2. 结构档位：实时价 + 持续确认（深度分级加速，见 A） ----------
    atr_now = _f(snap.atr) or _f(plan.get('atr_at_plan'))
    fast_depths = _floats(conf.get('tier_fast_depth_atr'), V2_DEFAULTS['tier_fast_depth_atr'])
    fast_mults = _floats(conf.get('tier_fast_confirm_mult'), V2_DEFAULTS['tier_fast_confirm_mult'])
    breached: List[int] = []
    for i, level in enumerate(levels):
        if i in tiers_done:
            pending.pop(str(i), None)
            continue
        if not _beyond(price, level, side):
            pending.pop(str(i), None)  # 回到线内，确认计时清零
            continue
        confirm = confirm_secs[i] if i < len(confirm_secs) else 0.0
        if confirm > 0 and atr_now > 0:
            # 破位深度（ATR 归一）：越深确认越短，急速破位直接跳过
            depth = ((level - price) if side == 'long' else (price - level)) / atr_now
            for j, th in enumerate(fast_depths):
                if depth >= th:
                    confirm *= fast_mults[j + 1] if j + 1 < len(fast_mults) else 0.0
        if confirm <= 0:
            breached.append(i)
            continue
        since = pending.get(str(i))
        if since is None:
            pending[str(i)] = now
        elif now - since >= confirm:
            breached.append(i)
    patch['pending'] = pending

    actions: List[Dict[str, Any]] = []
    if breached:
        ratio = sum(ratios[i] for i in breached if i < len(ratios))
        ratio = min(ratio, remaining)
        label = '/'.join(str(i + 1) for i in breached)
        if ratio > 0 and remaining > MIN_REMAINING:
            actions.append({
                'type': 'reduce', 'ratio': round(ratio, 6),
                'tiers': breached, 'tag': f'tier:{label}',
                'level': 'error' if max(breached) >= 2 else 'warning',
                'reason': f'结构破位 T{label}',
            })

    # ---------- 3. 止盈（与减仓互斥：同一轮只出一个减仓动作） ----------
    elif tp_prices and len(tp_done) < len(tp_prices):
        hits = [i for i, p in enumerate(tp_prices)
                if i not in tp_done and p > 0 and (
                    price >= p if side == 'long' else price <= p)]
        # D 单轮单档：插针扫过多档时只卖第一档，保留阶梯等回触（标定 93~96% 4h 内回触）
        if hits and bool(conf.get('tp_one_level_per_round', True)):
            hits = hits[:1]
        if hits:
            ratio = sum(tp_ratios[i] for i in hits if i < len(tp_ratios))
            ratio = min(ratio, max(0.0, remaining - MIN_REMAINING))
            label = '/'.join(str(i + 1) for i in hits)
            if ratio > 0:
                actions.append({
                    'type': 'reduce', 'ratio': round(ratio, 6),
                    'tps': hits, 'tag': f'tp:{label}',
                    'level': 'success',
                    'reason': f'分批止盈 TP{label}',
                })

    # ---------- 4. 止损上移（独立计算，只朝盈利方向走） ----------
    stop_action = _stop_action(state, snap, plan, conf, tiers_done)
    if stop_action:
        actions.append(stop_action)

    return {'actions': actions, 'patch': patch, 'reason': 'ok'}


def _stop_action(state: Dict[str, Any], snap: Snapshot, plan: Dict[str, Any],
                 conf: Dict[str, Any], tiers_done: set) -> Optional[Dict[str, Any]]:
    """计算本轮应当挂到交易所的兜底 STOP。

    交易所 STOP 的职责是「引擎挂了也要保住仓位」，所以它的起点是灾难线；
    随着减仓推进、浮盈扩大，才逐步抬到保本 / 锁利 / ATR 追踪位。
    """
    side = snap.side
    price = _f(snap.price)
    entry = _f(plan.get('entry'))
    risk = _f(plan.get('risk'))
    levels = [_f(x) for x in (plan.get('levels') or [])]
    atr = _f(snap.atr) or _f(plan.get('atr_at_plan'))
    if price <= 0 or entry <= 0 or risk <= 0 or len(levels) != 4:
        return None

    be_buf = max(0.0, _f(conf.get('breakeven_buffer_pct'), 0.002))
    lock_buf = max(0.0, _f(conf.get('profit_lock_buffer_pct'), 0.001))
    fr = floating_r(entry, risk, side, price)
    tp_done = set(_ints(state.get('tp_done')))

    candidates = [_f(plan.get('disaster_stop')) or levels[3]]
    if fr is not None and fr >= _f(conf.get('breakeven_trigger_r'), 0.5):
        candidates.append(entry * (1 + be_buf) if side == 'long' else entry * (1 - be_buf))
    if 0 in tp_done:
        candidates.append(entry * (1 + be_buf) if side == 'long' else entry * (1 - be_buf))
    if 1 in tp_done and plan.get('tp_prices'):
        tp1 = _f(plan['tp_prices'][0])
        if tp1 > 0:
            candidates.append(tp1 * (1 + lock_buf) if side == 'long' else tp1 * (1 - lock_buf))

    # 每减一档，止损推进到下一档：敞口和仓位同步收紧
    if tiers_done:
        deepest = max(tiers_done)
        nxt = min(deepest + 1, 3)
        candidates.append(levels[nxt])

    start_r = _f(conf.get('trailing_start_r'), 1.0)
    mult = _f(conf.get('trailing_atr_mult'), 2.5)
    if atr > 0 and fr is not None and fr >= start_r:
        peak = _f(state.get('peak'), price)
        trough = _f(state.get('trough'), price)
        candidates.append(peak - mult * atr if side == 'long' else trough + mult * atr)

    candidates = [c for c in candidates if c > 0]
    if not candidates:
        return None
    desired = max(candidates) if side == 'long' else min(candidates)

    # 止损绝不能落在价格错误一侧，否则会变成立即成交的市价单
    guard = max(1e-6, price * 0.002)
    if side == 'long':
        desired = min(desired, price - guard)
    else:
        desired = max(desired, price + guard)
    if desired <= 0:
        return None

    current = _f(state.get('stop'))
    if current <= 0:
        # 首次挂单：直接放兜底线，让内部四档先动作
        return {'type': 'stop', 'price': desired, 'tag': 'stop:init',
                'reason': '建立交易所兜底STOP', 'level': 'info'}

    improvement = (desired - current) if side == 'long' else (current - desired)
    if improvement <= 0:
        return None  # 绝不放宽
    threshold = max(price * _f(conf.get('stop_min_update_pct'), 0.0015),
                    atr * _f(conf.get('stop_min_update_atr_ratio'), 0.15))
    if improvement < threshold:
        return None  # 变化太小，不折腾交易所

    return {'type': 'stop', 'price': desired, 'tag': 'stop:move',
            'reason': '止损上移', 'level': 'info'}
