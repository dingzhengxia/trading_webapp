"""仓位保护运行时状态：SQLite 状态持久化、Runtime 单例、动作锁/冷却与状态日志节流（T08 自 engine.py 拆出）。

判定/动作语义零改动，仅做物理拆分。
"""

import asyncio
import math
import time
import uuid

from loguru import logger

from ..core.database import get_value, set_value
from ..core.guarded_exchange import raw_rest_method
from ..core.rest_guardian import create_guardian
from .config import _f

# 风控动作运行时锁：防止异步循环/并发检查导致 TP/T1/T2/T3 重复执行
_ACTION_EXECUTION_LOCK = set()

def _risk_action_lock_key(symbol, side, pos_state, action):
    return f"{symbol}:{side}:{pos_state.get('risk_cycle_id', 'unknown')}:{action}"

def _try_lock_risk_action(symbol, side, pos_state, action):
    key = _risk_action_lock_key(symbol, side, pos_state, action)
    if key in _ACTION_EXECUTION_LOCK:
        return False
    _ACTION_EXECUTION_LOCK.add(key)
    return True


# 与风险周期无关的动作级冷却：即使周期被异常重建（身份字段抖动/仓位闪断），
# 同一 symbol+side 的 T1/T2 也不能在短时间内反复减仓。
LAST_RISK_ACTION_TS: dict = {}


def _risk_action_on_cooldown(symbol, side, action, conf):
    interval = _f((conf or {}).get("risk_action_min_interval_sec"), 0.0) or 0.0
    if interval <= 0:
        return False
    last = LAST_RISK_ACTION_TS.get((symbol, side, action), 0.0)
    return (time.time() - last) < interval


def _mark_risk_action_done(symbol, side, action):
    LAST_RISK_ACTION_TS[(symbol, side, action)] = time.time()


def _load_state():
    """从 SQLite（protection_state 表，key='state'）读取仓位保护状态。"""
    try:
        data = get_value("protection_state", "state", {})
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning(f"读取仓位保护状态失败: {exc}")
        return {}


def _save_state(state):
    """写入 SQLite。失败时返回 False，运行时状态仍保存在进程内，避免旧周期被读回。"""
    try:
        set_value("protection_state", "state", state)
        return True
    except Exception as exc:
        logger.error(f"保存仓位保护状态失败: {exc}")
        return False


def _state_key(symbol, side):
    return f"{symbol}_{side}"


def _position_side(position):
    if not position:
        return None
    side = str(position.get("side") or "").lower()
    if side in ("long", "short"):
        return side
    info = position.get("info") or {}
    ps = str(info.get("positionSide") or "").upper()
    if ps == "LONG":
        return "long"
    if ps == "SHORT":
        return "short"
    amount = _f(info.get("positionAmt"), 0.0) or 0.0

    if amount > 0:
        return "long"
    elif amount < 0:
        return "short"
    else:
        return None


def _position_size(position):
    if not position:
        return 0.0
    v = _f(position.get("contracts"))
    if v is not None:
        return abs(v)
    return abs(_f((position.get("info") or {}).get("positionAmt"), 0.0) or 0.0)


def _raw_position_side(position):
    ps = str((position.get("info") or {}).get("positionSide") or "BOTH").upper()
    if ps in ("BOTH", "LONG", "SHORT"):
        return ps
    return "BOTH"


def _timeframe_ms(tf):
    unit = tf[-1].lower()
    n = int(tf[:-1])
    multiplier = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
    return n * multiplier[unit]


def _current_candle_close_ms(timeframe, now_ms=None):
    now_ms = int(now_ms or time.time() * 1000)
    size = _timeframe_ms(timeframe)
    return ((now_ms // size) + 1) * size


def _position_open_time_ms(position):
    """尽可能从交易所仓位对象提取本次仓位/加仓的时间戳。

    Binance 不同 CCXT 版本字段可能不同，因此按可信字段顺序读取；
    如果交易所没有提供，调用方会退回到本地首次发现时间。
    """
    if not position:
        return 0
    info = position.get("info") or {}
    candidates = (
        position.get("openedAt"), position.get("openTime"),
        info.get("openTime"), info.get("openedAt"), info.get("createTime"),
    )
    for value in candidates:
        v = _f(value, 0) or 0
        if v > 0:
            # 秒级时间戳统一转毫秒
            if v < 10_000_000_000:
                v *= 1000
            return int(v)
    return 0


class Runtime:
    def __init__(self):
        # 独立 guardian 实例（经 rest_guardian.create_guardian 工厂创建，保持
        # "RestGuardian( 只在 rest_guardian.py 实例化" 的静态审计口径）；
        # protection 有自己的 api_* 默认值（conf 随每次 _rest 调用传入）。
        self.rest = create_guardian()
        self.action_locks = {}
        self.positions_cache = (0.0, None)
        self.global_positions_map = {}
        self.ticker_cache = {}
        self.orders_cache = {}
        self.ohlcv_cache = {}
        self.last_circuit_notice = 0.0
        # 仓位生命周期保护：防止“手动平仓 -> 数小时后重新开仓”继承旧风险周期。
        self.previous_active_keys = set()
        self.force_new_cycle_keys = set()
        # 运行时一次性动作闩锁；即使状态文件短暂写入失败，也不能重复推送/减仓。
        self.risk_action_latches = set()
        # 状态文件不可写时，新周期仍保存在进程内，避免下一轮又读回旧周期。
        self.runtime_position_states = {}
        # 仓位“闪断”防抖：记录某方向第一次消失的时间，确认超过 flat_confirm_sec 才重建周期。
        self.disappeared_since = {}

    def action_lock(self, symbol, side):
        key = (symbol, side)
        if key not in self.action_locks:
            self.action_locks[key] = asyncio.Lock()
        return self.action_locks[key]


RUNTIME = Runtime()


# ---------------------------------------------------------------------------
# 逐轮状态日志节流：止盈/止损位、黑天鹅监控这类状态行每仓每轮一条，
# 仓位一多控制台/日志文件就被刷满。事件类日志（success/warning/error）不经过这里。
# ---------------------------------------------------------------------------
_STATUS_LOG_LAST = {}


def _status_log(kind, symbol, side, level, message, interval_sec):
    """同一 (kind, symbol, side) 的状态行至多每 interval_sec 秒输出一条。"""
    key = (kind, symbol, side)
    now = time.time()
    if now - _STATUS_LOG_LAST.get(key, 0.0) < max(0.0, float(interval_sec)):
        return
    if len(_STATUS_LOG_LAST) > 4096:
        cutoff = now - max(float(interval_sec), 3600.0) * 2
        for stale in [k for k, ts in _STATUS_LOG_LAST.items() if ts < cutoff]:
            _STATUS_LOG_LAST.pop(stale, None)
    _STATUS_LOG_LAST[key] = now
    logger.log(level, message)


async def _rest(exchange, method_name, *args, priority="NORMAL", conf=None, **kwargs):
    # exchange 可能是 GuardedExchange 代理：raw_rest_method 解包原始方法，
    # 保证 protection 的 guardian 恰好包一层（不与代理层双重限流）。
    func = raw_rest_method(exchange, method_name)
    return await RUNTIME.rest.call(func, *args, priority=priority, conf=conf, **kwargs)


def _reconcile_position_state(state, key, symbol, side, contracts, timeframe, position=None, conf=None):
    ps = state.get(key)
    if not isinstance(ps, dict):
        ps = {
            "base_contracts": contracts,
            "contracts": contracts,
            "t1_done": False,
            "t2_done": False,
            "t1_triggered": False,
            "t2_triggered": False,
            "t3_triggered": False,
            "risk_cycle_id": uuid.uuid4().hex,
            "last_position_entry_price": _f((position or {}).get("entryPrice"), 0.0),
            "exchange_entry_time_ms": _position_open_time_ms(position),
            "last_checked_time": 0,
            "last_closed_candle_ts": 0,
            "last_risk_check_time": 0,
            "risk_state": {
                "t1": "normal",
                "t2": "normal",
                "t3": "normal",
                "black_swan": "normal",
                "atr_protection": "normal"
            },
            "position_version": 1,
            "risk_cycle_started_at": int(time.time()),
            "add_immunity_until_ms": 0,
            "entry_time_ms": _position_open_time_ms(position) or int(time.time() * 1000),
            "entry_time_source": "exchange" if _position_open_time_ms(position) else "first_seen",
            "entry_classification": None,
            "risk_entry_price": _f((position or {}).get("entryPrice"), 0.0),
            "risk_entry_price_source": "position_average",
        }
        state[key] = ps
        return ps, True

    # 兼容旧版本 position_protection_state.json，自动补充风控恢复字段
    ps.setdefault("last_closed_candle_ts", int(ps.get("last_checked_time", 0)))
    ps.setdefault("entry_time_ms", _position_open_time_ms(position) or int(time.time() * 1000))
    ps.setdefault("entry_time_source", "exchange" if _position_open_time_ms(position) else "first_seen")
    ps.setdefault("entry_classification", None)
    ps.setdefault("t1_realtime_armed", False)
    ps.setdefault("t1_realtime_armed_initialized", False)
    ps.setdefault("risk_entry_price", _f((position or {}).get("entryPrice"), 0.0))
    ps.setdefault("risk_entry_price_source", "position_average")
    ps.setdefault("last_program_reduce_ts", 0)
    ps.setdefault("t1_triggered", bool(ps.get("t1_done")))
    ps.setdefault("t2_triggered", bool(ps.get("t2_done")))
    ps.setdefault("t3_triggered", False)
    ps.setdefault("tp1_triggered", False)
    ps.setdefault("tp2_triggered", False)
    ps.setdefault("tp3_triggered", False)
    ps.setdefault("tp_entry_price", None)
    ps.setdefault("tp_initial_stop", None)
    ps.setdefault("tp_risk_distance", None)
    ps.setdefault("tp1_price", None)
    ps.setdefault("tp2_price", None)
    ps.setdefault("tp3_price", None)
    ps.setdefault("tp_protected_stop", None)
    ps.setdefault("tp_protection_stage", 0)
    ps.setdefault("last_stop_price", None)
    ps.setdefault("last_stop_update_ts", 0)
    ps.setdefault("risk_cycle_id", uuid.uuid4().hex)
    ps.setdefault("last_position_entry_price", _f((position or {}).get("entryPrice"), 0.0))
    ps.setdefault("exchange_entry_time_ms", _position_open_time_ms(position))
    ps.setdefault("last_risk_check_time", 0)
    ps.setdefault("risk_state", {
        "t1": "done" if ps.get("t1_done") else "normal",
        "t2": "done" if ps.get("t2_done") else "normal",
        "t3": "normal",
        "black_swan": "normal",
        "atr_protection": "normal"
    })

    current_entry_price = _f((position or {}).get("entryPrice"), 0.0)
    current_open_time = _position_open_time_ms(position)
    old_entry_price = _f(ps.get("last_position_entry_price"), 0.0)
    old_open_time = int(ps.get("exchange_entry_time_ms") or 0)

    # 防止“平仓后同数量重新开仓”继承旧风险周期。
    # 优先使用交易所开仓时间；没有可靠时间时，用平均开仓价变化作为辅助身份识别。
    open_time_changed = current_open_time > 0 and old_open_time > 0 and current_open_time != old_open_time
    entry_price_changed = (current_entry_price > 0 and old_entry_price > 0
                           and abs(current_entry_price - old_entry_price) / max(old_entry_price, 1e-12) > 0.001)
    identity_changed = open_time_changed or entry_price_changed

    # 程序自身减仓（T1/T2/TP）可能让交易所侧的“仓位时间/均价”字段发生抖动
    # （部分交易所把 updateTime/重算后的均价映射到这些字段）。
    # 宽限期内只采纳新字段值、不重建风险周期，切断“减仓 -> 换周期 -> T1 立即再减仓”的自激循环。
    grace = _f((conf or {}).get("identity_grace_after_reduce_sec"), 0.0) or 0.0
    last_reduce = int(ps.get("last_program_reduce_ts") or 0)
    if identity_changed and grace > 0 and last_reduce > 0 and (time.time() - last_reduce) < grace:
        logger.warning(
            f"[{symbol}] 🕒 程序减仓后 {grace:.0f}s 宽限期内仓位身份字段变化"
            f"（open:{old_open_time}->{current_open_time} entry:{old_entry_price}->{current_entry_price}），"
            f"疑似交易所 updateTime/均价抖动，保留原风险周期 {ps.get('risk_cycle_id')}"
        )
        ps["exchange_entry_time_ms"] = current_open_time or old_open_time
        ps["last_position_entry_price"] = current_entry_price or old_entry_price
        identity_changed = False

    if identity_changed:
        ps.update({
            "base_contracts": contracts, "contracts": contracts,
            "t1_done": False, "t2_done": False,
            "t1_triggered": False, "t2_triggered": False, "t3_triggered": False,
            "tp1_triggered": False, "tp2_triggered": False, "tp3_triggered": False,
            "tp_entry_price": None, "tp_initial_stop": None, "tp_risk_distance": None,
            "tp1_price": None, "tp2_price": None, "tp3_price": None, "tp_protected_stop": None, "tp_protection_stage": 0,
            "t3_waived": False, "bottom_fish_sl": None,
            "position_version": int(ps.get("position_version", 0)) + 1,
            "risk_cycle_id": uuid.uuid4().hex,
            "risk_cycle_started_at": int(time.time()),
            "entry_time_ms": current_open_time or int(time.time() * 1000),
            "entry_time_source": "exchange" if current_open_time else "reopen_detected",
            "entry_classification": None,
            "t1_realtime_armed": False,
            "t1_realtime_armed_initialized": False,
            "risk_entry_price": current_entry_price or None,
            "risk_entry_price_source": "position_average",
            "processed_entry_version": 0,
            "exchange_entry_time_ms": current_open_time,
            "last_position_entry_price": current_entry_price,
        })
        logger.warning(f"[{symbol}] 🔄 检测到仓位身份变化，开启全新风险周期: {ps['risk_cycle_id']}")
        return ps, True

    if current_entry_price > 0:
        ps["last_position_entry_price"] = current_entry_price
    if current_open_time > 0:
        ps["exchange_entry_time_ms"] = current_open_time

    old = _f(ps.get("contracts"), contracts) or contracts
    changed = not math.isclose(old, contracts, rel_tol=1e-8, abs_tol=1e-10)

    if changed:
        ps["position_version"] = int(ps.get("position_version", 0)) + 1
        if contracts > old + max(1e-10, old * 1e-8):
            ps.update({
                "base_contracts": contracts,
                "contracts": contracts,
                "t1_done": False,
                "t2_done": False,
                "t1_triggered": False,
                "t2_triggered": False,
                "t3_triggered": False,
                "tp1_triggered": False, "tp2_triggered": False, "tp3_triggered": False,
                "tp_entry_price": None, "tp_initial_stop": None, "tp_risk_distance": None,
                "tp1_price": None, "tp2_price": None, "tp3_price": None, "tp_protected_stop": None, "tp_protection_stage": 0,
                "risk_cycle_id": uuid.uuid4().hex,
                "risk_cycle_started_at": int(time.time()),
                "add_immunity_until_ms": _current_candle_close_ms(timeframe),
                "entry_time_ms": int(time.time() * 1000),
                "entry_time_source": "add_detected",
                "entry_classification": None,
                "risk_entry_price": None,
                "risk_entry_price_source": "pending_market_snapshot",
                "processed_entry_version": 0,
            })
            logger.info(f"[{symbol}] ➕ 检测到手动/外部加仓 {old}->{contracts}，建立新风险周期；将重新计算加权开仓价、R、TP1/TP2/躺平及保护STOP。")
        else:
            ps["contracts"] = contracts
            logger.info(f"[{symbol}] 检测到外部减仓 {old}->{contracts}，保留已完成层级状态。")

    return ps, changed
