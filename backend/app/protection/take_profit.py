"""止盈阶梯：固定 R 初始化、TP1/TP2/躺平命中判定与利润保护性 STOP（T08 自 engine.py 拆出）。"""

from loguru import logger

from .config import _f


def _tp3_remaining_ratio(conf):
    """躺平 保留仓位比例：未设置/None => 0（全平）；设置 0~1 => 保留该比例。"""
    raw = conf.get("tp3_ratio", None)
    if raw is None or raw == "":
        return 0.0
    try:
        value = float(raw)
    except Exception:
        return 0.0
    # 兼容填写 20 表示 20%，但推荐配置写 0.20。
    if value > 1.0:
        value /= 100.0
    return min(1.0, max(0.0, value))


def _tp3_action_text(conf):
    ratio = _tp3_remaining_ratio(conf)
    return "全平" if ratio <= 0 else f"保留{ratio:.0%}"


def _initialize_take_profit_levels(pos_state, side, entry_price, strategy_stop, conf):
    """为当前风险周期固定初始 R，并计算 TP1/TP2/躺平。

    TP 使用风险周期开始时的初始风险，不跟随动态止损移动，避免行情上涨后 TP
    被不断推远/拉近。若当前策略止损不在仓位亏损侧，则暂不初始化。
    """
    if not bool(conf.get("take_profit_enabled", True)):
        return False
    if entry_price <= 0 or strategy_stop <= 0:
        return False

    if side == "long":
        risk = entry_price - strategy_stop
    else:
        risk = strategy_stop - entry_price

    # 策略保护线必须在开仓价的亏损方向；否则不能拿它制造有效 R。
    if risk <= max(entry_price * 0.0001, 1e-12):
        return False

    old_cycle = pos_state.get("tp_risk_distance")
    if old_cycle and float(old_cycle) > 0 and pos_state.get("tp1_price"):
        return True

    tp1_r = float(conf.get("tp1_r_multiple", 1.0))
    tp2_r = float(conf.get("tp2_r_multiple", 2.0))
    tp3_r = float(conf.get("tp3_r_multiple", 3.0))
    if not (0 < tp1_r < tp2_r < tp3_r):
        raise ValueError("TP 的 R 倍数必须满足 0 < TP1 < TP2 < 躺平")

    if side == "long":
        tp1 = entry_price + risk * tp1_r
        tp2 = entry_price + risk * tp2_r
        tp3 = entry_price + risk * tp3_r
    else:
        tp1 = entry_price - risk * tp1_r
        tp2 = entry_price - risk * tp2_r
        tp3 = entry_price - risk * tp3_r

    pos_state.update({
        "tp_entry_price": float(entry_price),
        "tp_initial_stop": float(strategy_stop),
        "tp_risk_distance": float(risk),
        "tp1_price": float(tp1),
        "tp2_price": float(tp2),
        "tp3_price": float(tp3),
        "tp_protected_stop": pos_state.get("tp_protected_stop"),
        "tp_protection_stage": int(pos_state.get("tp_protection_stage", 0)),
        "tp1_triggered": bool(pos_state.get("tp1_triggered", False)),
        "tp2_triggered": bool(pos_state.get("tp2_triggered", False)),
        "tp3_triggered": bool(pos_state.get("tp3_triggered", False)),
    })
    return True


def _take_profit_protection_stop(pos_state, side, conf, current_price=None):
    """计算当前风险周期的利润保护 STOP。

    保护分三层：
    1. 浮盈达到 profit_protection_trigger_r（默认 0.5R）：先把 STOP 推到
       开仓价附近，优先目标是本金保护；
    2. TP1 完成：STOP 继续保持在开仓价的盈利侧；
    3. TP2 完成：STOP 推到 TP1 附近；TP3 若保留仓位：STOP 推到 TP2 附近。

    返回 (保护止损价格, 保护阶段)。阶段 1 也用于“0.5R 浮盈保本”，
    因为它和 TP1 后的保本保护最终落在同一个保护层级。
    """
    entry = _f(pos_state.get("tp_entry_price"), 0.0)
    risk = _f(pos_state.get("tp_risk_distance"), 0.0)
    tp1 = _f(pos_state.get("tp1_price"), 0.0)
    if entry <= 0 or risk <= 0:
        return None, 0

    be_buf = max(0.0, float(conf.get("tp_breakeven_buffer_pct", 0.0020)))
    lock_buf = max(0.0, float(conf.get("tp_profit_lock_buffer_pct", 0.0010)))

    # 已完成 TP 的保护优先级最高。
    if pos_state.get("tp3_triggered"):
        tp2 = _f(pos_state.get("tp2_price"), 0.0)
        tp3_cfg = conf.get("tp3_ratio", None)
        if tp3_cfg is not None and 0.0 < float(tp3_cfg) < 1.0 and tp2 > 0:
            stop = tp2 * (1.0 + lock_buf) if side == "long" else tp2 * (1.0 - lock_buf)
            return stop, 3

    if pos_state.get("tp2_triggered") and tp1 > 0:
        stop = tp1 * (1.0 + lock_buf) if side == "long" else tp1 * (1.0 - lock_buf)
        return stop, 2

    # TP1 完成，或者尚未 TP1 但浮盈已经达到 0.5R，都进入保本保护。
    profit_protection_enabled = bool(conf.get("profit_protection_enabled", True))
    trigger_r = max(0.0, float(conf.get("profit_protection_trigger_r", 0.5)))
    floating_r = None
    if current_price is not None:
        price = _f(current_price, 0.0)
        if price > 0:
            floating_r = ((price - entry) / risk) if side == "long" else ((entry - price) / risk)

    if pos_state.get("tp1_triggered") or (
        profit_protection_enabled and floating_r is not None and floating_r >= trigger_r
    ):
        stop = entry * (1.0 + be_buf) if side == "long" else entry * (1.0 - be_buf)
        return stop, 1

    return None, 0


def _take_profit_hit(pos_state, side, current_price):
    """返回当前应该执行的最高级别止盈：3/2/1/0。

    关键安全校验：TP 价格必须与当前仓位方向、TP 入口价格形成正确的单调关系。
    如果发现 躺平 跑到了开仓价的错误一侧（例如多单 entry=8.x，但 躺平=7.x），
    说明状态是旧周期/脏状态，绝对不能触发平仓。
    """
    if not pos_state.get("tp_risk_distance"):
        return 0
    if pos_state.get("tp3_triggered"):
        return 0

    entry = _f(pos_state.get("tp_entry_price"), 0.0)
    tp1 = _f(pos_state.get("tp1_price"), 0.0)
    tp2 = _f(pos_state.get("tp2_price"), 0.0)
    tp3 = _f(pos_state.get("tp3_price"), 0.0)
    price = _f(current_price, 0.0)

    # 严格验证 TP 阶梯，任何异常都只记录/跳过，不允许误平仓。
    if min(entry, tp1, tp2, tp3, price) <= 0:
        return 0
    if side == "long":
        valid = entry < tp1 < tp2 < tp3
        if not valid:
            logger.error(
                f"[{pos_state.get('risk_cycle_id','?')}] 🚫 TP状态异常，拒绝执行止盈！ "
                f"方向:多 | Entry:{entry:.8f} | TP1:{tp1:.8f} | TP2:{tp2:.8f} | 躺平:{tp3:.8f} | 当前:{price:.8f}"
            )
            return 0
        if price >= tp3:
            return 3
        if price >= tp2 and not pos_state.get("tp2_triggered"):
            return 2
        if price >= tp1 and not pos_state.get("tp1_triggered"):
            return 1
    else:
        valid = entry > tp1 > tp2 > tp3
        if not valid:
            logger.error(
                f"[{pos_state.get('risk_cycle_id','?')}] 🚫 TP状态异常，拒绝执行止盈！ "
                f"方向:空 | Entry:{entry:.8f} | TP1:{tp1:.8f} | TP2:{tp2:.8f} | 躺平:{tp3:.8f} | 当前:{price:.8f}"
            )
            return 0
        if price <= tp3:
            return 3
        if price <= tp2 and not pos_state.get("tp2_triggered"):
            return 2
        if price <= tp1 and not pos_state.get("tp1_triggered"):
            return 1
    return 0
