# backend/app/protection/risk_model.py
"""仓位保护决策模型（纯函数：无 IO、无交易所调用、可离线回放）。

为什么重写这一层
- 旧模型有「风险周期」这个概念：一旦识别到加仓就整行重建（`new_state`），
  已触发档位 / 峰值 / 止损价 / 初始仓位全部归零。人工加一次仓，
  程序就把「已经卖过几档」忘掉，止损也被重新当成首次挂单——
  2026-11-15 ETH/BNB 的止损错位、BTC 重复减仓单都是这条路径的产物。
  新模型没有「重建周期」：只有一个持续演化的状态，加仓/减仓是状态转移。

四条不变量（后续所有分支都从这里推）
1. 仓位真值只有交易所的 (数量 q, 均价 E)。账本只记「不变量」和「历史动作」，
   不记「应该有多少仓位」。
2. 分批比例的分母是「规模锚 S = 历史最大持仓量」，只增不减。
   → 人工减仓后 q 变小，比例不会漂移（不会永远卖不完）；
   → 人工加仓后 S 抬到新 q，新仓位自动纳入后续批次。
3. 止损阶梯按 ATR 计（ATR 是「正常波动尺度」，跨币可比）；
   止盈阶梯按 R 计，R 与 TP 价在建计划时冻结——不冻结就永远到不了。
4. 止损只允许朝盈利方向移动，唯一例外是「加仓」：持仓均价被抬高后，
   旧止损可能贴到新均价上，必须按新基准重算（含下移），并强制留痕。

执行优先级（同一轮只出一个减仓动作，止损动作与之独立）
1. 击穿灾难线   → 全平（不确认、不等收盘）
2. 击穿结构档位 → 累计减仓（实时价 + 持续确认，破得越深确认越短）
3. 止盈         → 「先突破、再回落」才卖（引擎 3s 判定，不在交易所预挂）
4. 止损上移     → 每轮重算，只朝盈利方向走
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

EPS = 1e-12
MIN_REMAINING = 0.02   # 低于规模锚的 2% 视为已平，不再下单
PLAN_VERSION = 2       # 计划结构版本：老账本读进来会按新基准重算一次

# ---------------------------------------------------------------------------
# 默认参数（用户配置深合并在 runner.load_config 里完成）
# ---------------------------------------------------------------------------
V2_DEFAULTS: Dict[str, Any] = {
    'engine_version': 'v2',
    'dry_run': False,
    'v2_timeframe': '2h',
    'v2_poll_interval_sec': 3.0,
    'v2_decision_concurrency': 4,

    # ---- 结构减仓四档 ----
    # 越破越重，合计 100%：最后一档（T4）就是「结构彻底失效」的清仓档。
    'tier_ratios': [0.15, 0.20, 0.25, 0.40],
    # 每档参考的结构回看根数（只用第一档：T1 由最近的结构位决定，其余三档是预算等分）
    'tier_lookbacks': [7, 26, 83],
    'tier_atr_buffer': 0.5,
    # 每档的「持续确认」秒数；0 = 立即触发（灾难档）
    'tier_confirm_sec': [30, 45, 60, 0],
    # 破位深度分级：实时价越过档位线 X 个 ATR 时按档衰减确认秒数。
    # 2026-11 历史标定（BTC/ETH/SOL/DOGE 1m 回放，tools/sl_calibration/）：
    # 破 T1 后 30s 内继续深入 >=1.5 ATR 的概率 8%，该尾部即急速破位，直接跳过确认。
    'tier_fast_depth_atr': [0.5, 1.0, 1.5],
    'tier_fast_confirm_mult': [1.0, 0.5, 0.25, 0.0],

    # ---- 风险尺度 ----
    # T1 的允许区间：太近会被噪声扫掉，太远单笔风险失控。
    'risk_min_pct': 0.015,
    # T1 的距离上限（结构位太远时把 T1 收回来，否则一次回撤就吃掉 6~8%）
    't1_max_pct': 0.04,
    # 单笔最大亏损 = 灾难线的位置（相对持仓均价）。
    # 灾难线不再「T4 再往外推 1.5 ATR」——那是把「结构失效」当成「风险预算」，
    # 结果 BTC 的兜底单跑到 −11.3%，比任何一个结构位都远（2026-11-15 反馈）。
    'risk_max_pct': 0.06,

    # ---- 人工干预识别 ----
    # 均价变化超过 2bp = 一定加过仓（减仓不改变均价，币安平均成本法）
    'entry_change_tol_pct': 0.0002,
    # 数量变化超过 0.2% = 加减仓（挡住交易所精度抖动）
    'qty_change_tol_pct': 0.002,
    # 人工减仓幅度超过这个比例才外发提示（避免手动平一点就弹一次）
    'intervention_alert_pct': 0.10,

    # ---- 止盈阶梯 ----
    # 1.5R / 2.5R / 4R，减 20% / 25% / 30%，剩 25% 交给追踪止损。
    'tp_r_multiples': [1.5, 2.5, 4.0],
    'tp_ratios': [0.20, 0.25, 0.30],
    'tp_keep_ratio': 0.25,
    # 止盈触发口径：价格必须先「真正越过」TP（含这段缓冲）才算突破，
    # 之后跌回 TP 才卖。直接把单子挂在 TP 上，第一根插针就成交，
    # 后面走出的大行情一点吃不到（2026-11-15 用户口径）。
    'tp_breakout_confirm_pct': 0.001,

    # ---- 止损阶梯（全部按 ATR 计）----
    # 保本触发：浮盈达到 2×ATR 才把止损推到成本。
    # 旧口径用 0.5R：BTC 的 R=6.24% 而 2h ATR 只有 1.87%，0.5R=3.1% 就保本，
    # 止损从 −6.2% 一步跳到成本价，回撤容忍度只剩 3%，1.7 个 ATR 的正常波动就出局。
    'breakeven_trigger_atr': 2.0,
    'breakeven_buffer_pct': 0.001,
    'breakeven_atr_ratio': 0.4,
    'profit_lock_buffer_pct': 0.001,
    # 追踪起点 2.5×ATR，宽度 1.5×ATR：浮盈 2.5ATR 时锁住 1ATR，回撤容忍 1.5ATR。
    'trailing_start_atr': 2.5,
    'trailing_atr_mult': 1.5,
    # 止损线离现价的最小安全距离：贴太近等于市价单，一个 tick 就出局。
    # 旧值只有 0.2% 价格，BTC 的 1 ATR=1.87%，等于把止损放在噪声里。
    'stop_min_room_atr': 0.6,
    'stop_min_room_pct': 0.003,
    # 止损推进多少才值得撤单重挂（防抖，避免每 3 秒刷交易所）
    'stop_min_update_pct': 0.0015,
    'stop_min_update_atr_ratio': 0.15,
    'stop_verify_interval_sec': 15.0,

    # ---- 执行层 ----
    'tier_marketable_retries': 3,     # maker 失败后吃单价重试次数
    'reduce_market_fallback': True,   # 吃单价也失败后允许市价兜底
    'reduce_retry_fast_sec': 10.0,    # 减仓未成交的快速重试冷却
    'action_retry_cooldown_sec': 90.0,
    'tier_maker_retries': 3,
    'tier_maker_only_until': 2,

    # ---- 结构重估（只动未触发的档位线，只许外移）----
    'replan_enabled': True,
    'replan_interval_sec': 86400.0,
    'replan_atr_up_ratio': 1.5,
    'replan_atr_down_ratio': 0.6,
    'replan_cooldown_sec': 3600.0,

    # ---- 黑天鹅（唯一允许吃单的全平路径）----
    'emergency_enabled': True,
    'emergency_timeframe': '1h',
    'emergency_atr_multiplier': 3.0,
    'emergency_atr_period': 14,
    'emergency_structure_lookback': 4,
    'emergency_vol_multiplier': 3.0,
    'emergency_vol_atr_multiplier': 4.0,
    'emergency_min_move_pct': 0.01,
    'emergency_cooldown_sec': 900.0,
    'emergency_block_new_entries': False,
    'tradable_volume_ratio': 0.10,
    'tradable_range_ratio': 0.25,
    'tradable_min_bars': 16,
    'flat_confirm_sec': 30.0,
}

# 旧版本把默认值原样存进 position_protection，升级默认值对老配置完全无效。
# 键名本身也换了（R 基准 → ATR 基准），老键一律丢弃，由新默认接管。
LEGACY_KEYS = (
    'breakeven_trigger_r', 'trailing_start_r', 'trailing_trigger_r',
    'tp_slice_cap', 'tp_verify_interval_sec', 'tp_rearm_min_interval_sec',
    'entry_replan_pct', 'disaster_atr_buffer', 'plan_version',
)


@dataclass(frozen=True)
class Snapshot:
    """一轮巡检拿到的、判断所需要的全部市场事实。"""
    symbol: str
    side: str                 # 'long' | 'short'
    entry: float              # 交易所持仓均价（唯一真值）
    price: float              # 当前标记价
    last_close: float         # 最近一根已收盘 K 线的收盘价
    contracts: float          # 当前持仓数量
    atr: float
    structure: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # 7/26/83 根结构位
    closed_ts: int = 0
    now: float = 0.0
    # 交易所上真实存在的兜底 STOP 触发价（0 = 查过但没找到）。
    # 账本里的 state['stop'] 只是「我们上次挂了什么」，用户可以在 App 里手改，
    # 所以「要不要补挂/能不能上移」必须以交易所为准。
    exchange_stop: float = 0.0
    # 本轮是否真的查过交易所（节流：stop_verify_interval_sec）
    exchange_checked: bool = False
    # 本轮是否刚因「加仓」重算了风险基准。为 True 时止损允许下移一次。
    rebased: bool = False
    # 本周期内累计已实现减仓量（账本口径，仅用于展示）
    base_contracts: float = 0.0


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


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _beyond(price: float, level: float, side: str) -> bool:
    """价格是否已经越过某条线（long 向下破，short 向上破）。"""
    return price <= level if side == 'long' else price >= level


def _dist(entry: float, level: float, side: str) -> float:
    """档位相对持仓均价的距离（正数 = 亏损方向的百分比距离）。"""
    if entry <= 0:
        return 0.0
    return (entry - level) / entry if side == 'long' else (level - entry) / entry


def _price_at(entry: float, dist: float, side: str) -> float:
    """距离 → 价位（dist 为正 = 亏损方向）。"""
    return entry * (1.0 - dist) if side == 'long' else entry * (1.0 + dist)


def floating_r(entry: float, risk: float, side: str, price: float) -> Optional[float]:
    if risk <= 0 or entry <= 0 or price <= 0:
        return None
    return ((price - entry) / risk) if side == 'long' else ((entry - price) / risk)


def size_anchor(state: Dict[str, Any], contracts: float) -> float:
    """规模锚 S：历史最大持仓量，只增不减。

    它是所有分批比例的分母。用「当前仓位」做分母会让止盈永远卖不完
    （分母随卖出变小）；用「建仓时的初始仓位」做分母会让人工加仓的新仓位
    永远不参与分批。取历史最大值的语义是「按我这笔单子最大时的规模分批」。
    """
    anchor = _f(state.get('size_anchor')) or _f(state.get('base_contracts')) or contracts
    return max(anchor, contracts)


# ---------------------------------------------------------------------------
# 风险计划
# ---------------------------------------------------------------------------
def _geometry(entry: float, atr: float, conf: Dict[str, Any]) -> Tuple[float, float, float]:
    """风险几何（全部用「相对持仓均价的距离」，正数 = 亏损方向）。

    返回 (d_min, d_max, d_t1_far)：
    · d_min  = T1 的最近距离 = max(risk_min_pct, 0.8×ATR) —— 低于 0.8 ATR 的止损
      就在噪声里，正常回撤必被扫；
    · d_max  = 单笔最大亏损（灾难线），至少给 d_min 留 1.5 倍呼吸空间；
    · d_t1_far = T1 的最远距离，结构位再远也把第一档收回来。
    """
    atr_pct = atr / entry if entry > 0 else 0.0
    d_min = max(_f(conf.get('risk_min_pct'), 0.015), 0.8 * atr_pct)
    d_max = max(_f(conf.get('risk_max_pct'), 0.06), d_min * 1.5)
    d_t1_far = _clamp(_f(conf.get('t1_max_pct'), 0.04), d_min, d_max * 0.85)
    return d_min, d_max, d_t1_far


def build_plan(side: str, entry: float, atr: float,
               structure: Sequence[float], conf: Dict[str, Any],
               now: float = 0.0) -> Dict[str, Any]:
    """结构位 + ATR → 四档减仓线 / R / 止盈阶梯 / 灾难线。

    档位算法（以 long 为例，short 对称，全程用「距离」运算避免多空符号分叉）
    · T1 = 最近的结构位再往外 0.5×ATR，距离夹在 [d_min, d_t1_far]——
      结构位定义「这单什么时候算错了」，ATR 只负责把它推到噪声之外；
    · T2/T3/T4 = T1 到灾难线之间 25%/50%/75% 等距：结构位只决定第一档，
      之后是「亏损预算怎么分段消耗」。这样四档永远落在预算内、永远严格单调，
      不会因为某个周期结构位特别远就把最后一档顶到 −8%、−11%；
    · 灾难线 = d_max（单笔最大亏损），不再由 T4 再外推 buffer。
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
    ratios = [x / total for x in ratios]          # 归一化，避免用户填出 120%

    buffer_mult = max(0.0, _f(conf.get('tier_atr_buffer'), 0.5))
    d_min, d_max, d_t1_far = _geometry(entry, atr, conf)

    s1 = float(structure[0])
    struct_d = _dist(entry, s1, side)
    # 结构位落在均价错误一侧（例如 long 的结构位在均价上方）时不参与决策
    d1 = d_max if struct_d <= 0 else struct_d + atr * buffer_mult / entry
    d1 = _clamp(d1, d_min, d_t1_far)

    dists = [d1 + (d_max - d1) * (i / 4.0) for i in range(4)]
    levels = [_price_at(entry, d, side) for d in dists]
    disaster = _price_at(entry, d_max, side)
    risk = abs(entry - levels[0])

    tp_mults = _floats(conf.get('tp_r_multiples'), V2_DEFAULTS['tp_r_multiples'])
    if not (0 < tp_mults[0] < tp_mults[1] < tp_mults[2]):
        tp_mults = [1.5, 2.5, 4.0]
    tp_ratios = [max(0.0, x) for x in
                 _floats(conf.get('tp_ratios'), V2_DEFAULTS['tp_ratios'])]
    keep = _clamp(_f(conf.get('tp_keep_ratio'), 0.25), 0.0, 0.9)
    tp_total = sum(tp_ratios)
    if tp_total > (1.0 - keep) > 0:
        tp_ratios = [x * (1.0 - keep) / tp_total for x in tp_ratios]

    sign = 1.0 if side == 'long' else -1.0
    return {
        'version': PLAN_VERSION,
        'side': side,
        'entry': float(entry),
        'risk': float(risk),
        'levels': [float(x) for x in levels],
        'ratios': ratios,
        'tp_prices': [float(entry + sign * risk * m) for m in tp_mults],
        'tp_ratios': tp_ratios,
        'disaster_stop': float(disaster),
        'disaster_pct': float(d_max),
        'atr_at_plan': float(atr),
        'built_at': float(now or 0.0),
    }


def rebase_plan(plan: Dict[str, Any], side: str, entry: float, atr: float,
                structure: Sequence[float], conf: Dict[str, Any],
                now: float) -> Optional[Dict[str, Any]]:
    """加仓后按新持仓均价重建风险基准（档位 / R / 止盈 / 灾难线一起换）。

    这是「止损只许上移」的唯一例外，也是档位唯一允许内移的时机：
    持仓均价变了，旧坐标系的每条线都失去意义。

    保留的是「进度」：tiers_done / tp_done 一律不动（卖过的档不再卖），
    peak / trough 也不动（那是行情极值，与仓位无关）。调用方负责清 tp_armed。
    """
    if entry <= 0 or atr <= 0:
        return None
    try:
        fresh = build_plan(side, entry, atr, structure, conf, now=now)
    except Exception:
        return None
    fresh['rebase_count'] = int(_f(plan.get('rebase_count'))) + 1
    fresh['rebased_at'] = float(now)
    fresh['entry_prev'] = _f(plan.get('entry'))
    fresh['built_at'] = _f(plan.get('built_at')) or float(now)
    return fresh


# ---------------------------------------------------------------------------
# 结构重估：只动未触发的档位线，只许外移
# ---------------------------------------------------------------------------
def replan_plan(plan: Dict[str, Any], side: str, structure: Sequence[float],
                atr: float, current_price: float, conf: Dict[str, Any],
                now: float, tiers_done: Sequence[int],
                reason: str = 'scheduled') -> Optional[Dict[str, Any]]:
    """重算未触发档位线与灾难线，返回新的 plan 副本；无需/不安全重估时返回 None。

    硬约束：
    1. 已触发档位冻结，不参与重算；
    2. 未触发档位只许外移（long：新线 <= 旧线）——内移会在重算瞬间造成
       「价格已在线外」的假破位，等于自动在回调低点触发减仓；
    3. 灾难线只许外移，且始终比 T4 更深；
    4. entry/risk/tp_prices 终身锁定（R 与 TP 一动，止盈就永远到不了）；
    5. 只返回 plan，不发任何交易动作。
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
    old_d = [_dist(entry, lv, side) for lv in old_levels]
    old_disaster = _f(plan.get('disaster_stop'))
    # 灾难线只许外移：ATR 缩小时不许把它收回（收回等于放宽止损）
    d_max = max(_dist(entry, old_disaster, side) if old_disaster > 0 else 0.0,
                _f(fresh.get('disaster_pct')))
    # T1 冻结（已触发）或只许外移（未触发）；其余三档按新基准重新等距
    d1 = old_d[0] if 0 in done else max(old_d[0], _dist(entry, fresh['levels'][0], side))
    d1 = min(d1, d_max * 0.85)
    dists = [d1 + (d_max - d1) * (i / 4.0) for i in range(4)]

    merged: List[float] = []
    for i in range(4):
        d = old_d[i] if i in done else max(old_d[i], dists[i])
        if merged:
            # 严格单调：不得比上一档更靠内（已触发档不会被推，可以放心兜底）
            d = max(d, merged[-1] + EPS)
        merged.append(d)

    levels = [_price_at(entry, d, side) for d in merged]
    disaster = _price_at(entry, d_max, side)

    if all(abs(a - b) <= max(EPS, entry * 1e-9)
           for a, b in zip(levels, old_levels)) \
            and abs(disaster - old_disaster) <= max(EPS, entry * 1e-9) \
            and abs(atr - _f(plan.get('atr_at_plan'))) <= atr * 1e-6:
        return None

    new_plan = dict(plan)
    new_plan['levels'] = [float(x) for x in levels]
    new_plan['disaster_stop'] = float(disaster)
    new_plan['disaster_pct'] = float(d_max)
    new_plan['atr_at_plan'] = float(atr)
    new_plan['replanned_at'] = float(now)
    new_plan['replan_count'] = int(_f(plan.get('replan_count'))) + 1
    new_plan['replan_reason'] = str(reason)
    return new_plan


# ---------------------------------------------------------------------------
# 状态
# ---------------------------------------------------------------------------
def new_state(cycle_id: str, side: str, entry: float, base_contracts: float,
              plan: Dict[str, Any], now: float) -> Dict[str, Any]:
    return {
        'cycle_id': cycle_id,
        'side': side,
        'version': 2,
        # 仓位真值镜像（每轮由交易所刷新）
        'contracts': float(base_contracts),
        # 规模锚：所有分批比例的分母，只增不减
        'size_anchor': float(base_contracts),
        # 上一轮看到的仓位事实，用于识别人工干预
        'q_seen': float(base_contracts),
        'e_seen': float(entry),
        'plan': plan,
        'tiers_done': [],
        'tp_done': [],
        'tp_armed': [],
        'pending': {},
        'stop': None,
        'peak': float(entry),
        'trough': float(entry),
        'opened_at_ms': 0,
        'created_at': float(now),
        'updated_at': float(now),
        'attempts': {},
        'interventions': [],
    }


# ---------------------------------------------------------------------------
# 人工干预识别
# ---------------------------------------------------------------------------
def detect_intervention(state: Optional[Dict[str, Any]], side: str,
                        contracts: float, entry: float,
                        conf: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """识别「这笔仓位被人工（或别的策略）加过 / 减过」。

    判据只用两个交易所事实，不猜：
    · 持仓均价变了 → 一定加过仓。币安按平均成本法，减仓不改变 entryPrice，
      只有增加仓位才会让它移动。这一条比「比较初始仓位」可靠得多：
      减仓后再加仓回补到初始仓位以下的场景（ETH 0.112→0.333 < base 0.733）
      旧逻辑完全看不见。
    · 数量变了（均价没变）→ 加/减仓。

    返回 {'kind': 'add'|'reduce', 'delta_qty', 'delta_entry', 'implied_price', ...}
    """
    conf = conf or {}
    if not state or not isinstance(state.get('plan'), dict):
        return None
    prev_e = _f(state.get('e_seen')) or _f((state.get('plan') or {}).get('entry'))
    prev_q = (_f(state.get('q_seen')) or _f(state.get('contracts'))
              or _f(state.get('base_contracts')))
    if prev_q <= 0 or contracts <= 0 or prev_e <= 0 or entry <= 0:
        return None

    ent_tol = max(1e-6, _f(conf.get('entry_change_tol_pct'), 0.0002))
    qty_tol = max(1e-6, _f(conf.get('qty_change_tol_pct'), 0.002))
    d_entry = abs(entry - prev_e) / prev_e
    delta_q = contracts - prev_q

    kind: Optional[str] = None
    if d_entry > ent_tol:
        kind = 'add'          # 均价动了只可能是加仓
    elif delta_q > prev_q * qty_tol:
        kind = 'add'          # 加在同价位：均价没动但量变多
    elif delta_q < -prev_q * qty_tol:
        kind = 'reduce'

    if kind is None:
        return None

    implied = entry
    if kind == 'add' and abs(delta_q) > 1e-12:
        # 反解这次加仓的成交均价：均价从 prev_e 移到 entry 的唯一来源就是这一笔
        implied = (entry * contracts - prev_e * prev_q) / delta_q
    return {
        'kind': kind,
        'delta_qty': float(delta_q),
        'delta_entry': float(entry - prev_e),
        'implied_price': float(implied),
        'prev_qty': float(prev_q),
        'prev_entry': float(prev_e),
        'qty_pct': float(delta_q / prev_q),
    }


# ---------------------------------------------------------------------------
# 减仓数量：只有这一处口径
# ---------------------------------------------------------------------------
def sell_qty(state: Dict[str, Any], contracts: float, ratio: float,
             keep_frac: float) -> float:
    """本档卖出量 = min(规模锚 × 档位比例, 当前持仓 × (1 − 保留比例))。

    min 的第二项是硬保险：
    · 人工减仓后 contracts 变小 → 最多卖到保留比例，不会一刀清零；
    · 人工加仓后 size_anchor 抬到新 q → 后续档位按新规模分批。
    旧实现用「本风险周期初始仓位」做分母，加仓后分母过期，
    出现「标称减 25%、实际砍掉剩余 79%」（2026-11-15 BTC）。
    """
    anchor = size_anchor(state, contracts)
    if contracts <= 0 or anchor <= 0 or ratio <= 0:
        return 0.0
    keep = _clamp(keep_frac, 0.0, 0.95)
    return max(0.0, min(anchor * ratio, contracts * (1.0 - keep)))


def tp_breakout_price(tp_price: float, side: str, conf: Dict[str, Any]) -> float:
    """「算突破」的价格：价格必须先越过 TP 这么远，这一档才进入待回落状态。"""
    tp = _f(tp_price)
    if tp <= 0:
        return 0.0
    pct = max(0.0, _f(conf.get('tp_breakout_confirm_pct'),
                      V2_DEFAULTS['tp_breakout_confirm_pct']))
    return tp * (1 + pct) if side == 'long' else tp * (1 - pct)


# ---------------------------------------------------------------------------
# 决策
# ---------------------------------------------------------------------------
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
    contracts = _f(snap.contracts)

    if len(levels) != 4 or entry <= 0 or risk <= 0 or price <= 0:
        return {'actions': [], 'patch': {}, 'reason': 'plan_invalid'}

    anchor = size_anchor(state, contracts)
    remaining = contracts / anchor if anchor > 0 else 0.0
    patch: Dict[str, Any] = {}

    # 跟踪极值，供移动止损使用（只在本周期内累积）
    patch['peak'] = max(_f(state.get('peak'), entry), price)
    patch['trough'] = min(_f(state.get('trough'), entry), price)

    tiers_done = set(_ints(state.get('tiers_done')))
    pending = {str(k): _f(v) for k, v in (state.get('pending') or {}).items()}
    ratios = _floats(plan.get('ratios'), V2_DEFAULTS['tier_ratios'])
    confirm_secs = _floats(conf.get('tier_confirm_sec'), V2_DEFAULTS['tier_confirm_sec'])

    # ---------- 1. 灾难线：不确认、不等收盘，直接全平 ----------
    disaster = _f(plan.get('disaster_stop'))
    if disaster > 0 and _beyond(price, disaster, side):
        patch['pending'] = {}
        return {
            'actions': [{
                'type': 'exit', 'ratio': 1.0, 'qty': contracts, 'tag': 'disaster',
                'level': 'error',
                'reason': f'击穿灾难线 {disaster:.8g}（单笔亏损上限）',
            }],
            'patch': patch,
        }

    # ---------- 2. 结构档位：实时价 + 持续确认（深度分级加速） ----------
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
    if breached and remaining > MIN_REMAINING:
        ratio = min(sum(ratios[i] for i in breached if i < len(ratios)), remaining)
        # 最后一档（T4）= 结构彻底失效，允许清仓；其余档至少留 10% 给后续
        keep_frac = 0.0 if max(breached) >= 3 else 0.10
        qty = sell_qty(state, contracts, ratio, keep_frac)
        label = '/'.join(str(i + 1) for i in breached)
        if qty > 0:
            actions.append({
                'type': 'reduce', 'ratio': round(ratio, 6), 'qty': qty,
                'tiers': breached, 'tag': f'tier:{label}',
                'level': 'error' if max(breached) >= 2 else 'warning',
                'reason': f'结构破位 T{label}',
            })

    # ---------- 3. 止盈：程序判定「突破 → 回落」（不预挂到交易所） ----------
    tp_prices = [_f(x) for x in (plan.get('tp_prices') or [])]
    tp_ratios = _floats(plan.get('tp_ratios'), V2_DEFAULTS['tp_ratios'])
    tp_done = set(_ints(state.get('tp_done')))
    armed = set(_ints(state.get('tp_armed')))
    if tp_prices and not actions:
        peak = _f(patch.get('peak'), price)
        trough = _f(patch.get('trough'), price)
        # ① 登记突破：从低档往高档扫，没越过的档之后的不可能越过
        for i, tp in enumerate(tp_prices):
            if i in tp_done or tp <= 0 or i in armed:
                continue
            confirm = tp_breakout_price(tp, side, conf)
            crossed = peak >= confirm if side == 'long' else trough <= confirm
            if not crossed:
                break
            armed.add(i)
            patch['tp_armed'] = sorted(armed)
        # ② 回落触发：从高档往低档扫。一次跌穿多档时先卖离现价最近的那一档，
        #    否则会先卖掉 TP1（价格早已低于 TP2/TP3），等于把高位那几档贱卖。
        for i in range(len(tp_prices) - 1, -1, -1):
            tp = tp_prices[i]
            if i in tp_done or i not in armed or tp <= 0:
                continue
            pulled_back = price <= tp if side == 'long' else price >= tp
            if not pulled_back:
                continue
            ratio = min(tp_ratios[i] if i < len(tp_ratios) else 0.0, remaining)
            keep = _clamp(_f(conf.get('tp_keep_ratio'), 0.25), 0.0, 0.9)
            qty = sell_qty(state, contracts, ratio, keep)
            if qty > 0 and remaining > MIN_REMAINING:
                actions.append({
                    'type': 'reduce', 'ratio': round(ratio, 6), 'qty': qty,
                    'tps': [i], 'tag': f'tp:{i + 1}',
                    'level': 'success',
                    'reason': f'分批止盈 TP{i + 1}（突破后回落至 {tp:.6g}）',
                })
            break  # 单轮只卖一档，一根针不会把整条阶梯一次打光

    # ---------- 4. 止损上移（独立计算，只朝盈利方向走） ----------
    stop_action = _stop_action(state, snap, plan, conf, tiers_done)
    if stop_action:
        actions.append(stop_action)
    elif snap.exchange_checked and snap.exchange_stop > 0:
        # 交易所 STOP 与账本不一致（例如用户在 App 里手动改过价）：以交易所为准回写
        actual = _f(snap.exchange_stop)
        if abs(_f(state.get('stop')) - actual) > max(actual * 1e-6, 1e-12):
            patch['stop'] = actual

    return {'actions': actions, 'patch': patch, 'reason': 'ok'}


def _stop_move_reason(side: str, entry: float, price: float, desired: float) -> str:
    """给「止损上移」一个能看懂的定性，避免台账里全是「止损上移」。"""
    if entry <= 0:
        return '止损上移'
    if (desired > entry) if side == 'long' else (desired < entry):
        return '止损上移到保本/锁盈'
    return '止损上移（档位推进）'


def _stop_action(state: Dict[str, Any], snap: Snapshot, plan: Dict[str, Any],
                 conf: Dict[str, Any], tiers_done: set) -> Optional[Dict[str, Any]]:
    """计算本轮应当挂到交易所的兜底 STOP。

    交易所 STOP 的职责是「引擎挂了也要保住仓位」，起点是灾难线；
    随着减仓推进、浮盈扩大，逐步抬到保本 / 锁利 / ATR 追踪位。

    候选全部按 ATR 归一（不按 R）：
    · R 由结构决定，与波动尺度脱钩——BTC 的 R=6.24% 而 2h ATR 只有 1.87%，
      用 0.5R 触发保本，回撤容忍只剩 3%，1.7 个 ATR 就出局；
    · ATR 是「正常波动尺度」，浮盈 2 ATR 保本、2.5 ATR 起追踪，跨币一致。
    """
    side = snap.side
    price = _f(snap.price)
    entry = _f(plan.get('entry'))
    risk = _f(plan.get('risk'))
    levels = [_f(x) for x in (plan.get('levels') or [])]
    atr = _f(snap.atr) or _f(plan.get('atr_at_plan'))
    if price <= 0 or entry <= 0 or risk <= 0 or len(levels) != 4:
        return None

    be_buf = max(0.0, _f(conf.get('breakeven_buffer_pct'), 0.001))
    be_atr = max(0.0, _f(conf.get('breakeven_atr_ratio'), 0.4))
    lock_buf = max(0.0, _f(conf.get('profit_lock_buffer_pct'), 0.001))
    sign = 1.0 if side == 'long' else -1.0
    # 浮盈以 ATR 计：+2.3 表示"赚了 2.3 个 ATR"
    gap_atr = ((price - entry) / atr * sign) if atr > 0 else None
    tp_done = set(_ints(state.get('tp_done')))
    tp_prices = [_f(x) for x in (plan.get('tp_prices') or [])]

    candidates: List[float] = [_f(plan.get('disaster_stop')) or levels[3]]

    # L1 破位推进：破了第 i 档，止损就跟到第 i+1 档（敞口与仓位同步收紧）
    if tiers_done:
        nxt = min(max(tiers_done) + 1, 3)
        candidates.append(levels[nxt])

    # L2 保本：浮盈 >= breakeven_trigger_atr×ATR
    if gap_atr is not None and gap_atr >= _f(conf.get('breakeven_trigger_atr'), 2.0):
        offset = max(entry * be_buf, atr * be_atr)
        candidates.append(entry + sign * offset)

    # L3 锁利：已止盈的档，止损推到该档之上
    for i in tp_done:
        if 0 <= i < len(tp_prices) and tp_prices[i] > 0:
            candidates.append(tp_prices[i] * (1 + sign * lock_buf))

    # L4 追踪：浮盈 >= trailing_start_atr×ATR 后按 peak − k×ATR 跟随
    if gap_atr is not None and gap_atr >= _f(conf.get('trailing_start_atr'), 2.5) and atr > 0:
        peak = _f(state.get('peak'), price)
        trough = _f(state.get('trough'), price)
        mult = _f(conf.get('trailing_atr_mult'), 1.5)
        candidates.append(peak - mult * atr if side == 'long' else trough + mult * atr)

    candidates = [c for c in candidates if c > 0]
    if not candidates:
        return None
    desired = max(candidates) if side == 'long' else min(candidates)

    # 止损绝不能落在价格错误一侧（否则是立即成交的市价单），也不能贴太近：
    # 至少要留 stop_min_room_atr×ATR 的呼吸空间，否则一个 tick 就打掉。
    room = max(atr * _f(conf.get('stop_min_room_atr'), 0.6),
               price * _f(conf.get('stop_min_room_pct'), 0.003))
    if side == 'long':
        desired = min(desired, price - room)
    else:
        desired = max(desired, price + room)
    if desired <= 0:
        return None

    # 交易所没单：用户手动撤了 / 被触发 / 当初挂单失败。
    # 这时不能拿账本旧价做「有没有推进」的比较——账本以为还在，就永远不会补挂。
    ledger_stop = _f(state.get('stop'))
    actual = _f(snap.exchange_stop) if snap.exchange_checked else 0.0
    if snap.exchange_checked and actual <= 0:
        tag = 'stop:restore' if ledger_stop > 0 else 'stop:init'
        reason = ('交易所STOP已不在（被撤销或已触发），重新挂出' if ledger_stop > 0
                  else '建立交易所兜底STOP')
        return {'type': 'stop', 'price': desired, 'tag': tag, 'reason': reason,
                'level': 'warning' if ledger_stop > 0 else 'info',
                'previous_stop': ledger_stop, 'force': True}

    current = actual if actual > 0 else ledger_stop
    if current <= 0:
        return {'type': 'stop', 'price': desired, 'tag': 'stop:init',
                'reason': '建立交易所兜底STOP', 'level': 'info',
                'previous_stop': 0.0, 'force': True}

    improvement = (desired - current) if side == 'long' else (current - desired)
    if improvement <= 0:
        # 加仓后持仓均价被抬高，旧止损可能贴到新均价上：这一轮必须按新基准重算，
        # 允许一次下移（其余任何场景都不许放宽）。
        if not snap.rebased:
            return None
        return {'type': 'stop', 'price': desired, 'tag': 'stop:rebase',
                'reason': '加仓后按新持仓均价重算止损',
                'level': 'warning', 'previous_stop': current, 'force': True}

    threshold = max(price * _f(conf.get('stop_min_update_pct'), 0.0015),
                    atr * _f(conf.get('stop_min_update_atr_ratio'), 0.15))
    if improvement < threshold:
        return None  # 变化太小，不折腾交易所

    return {'type': 'stop', 'price': desired, 'tag': 'stop:move',
            'reason': _stop_move_reason(side, entry, price, desired),
            'level': 'info', 'previous_stop': current, 'force': False}
