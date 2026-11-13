"""止损判定：策略结构位、动态保护止损与灾难止损（T08 自 engine.py 拆出）。

纯价格计算，不触碰交易所；交易所 STOP 挂单管理见 exits.py。
"""

from .market_data import _ema_structure_from_rows


def _strategy_levels_from_rows(rows, conf):
    fast = int(conf.get("ema_fast_period", 26))
    slow = int(conf.get("ema_slow_period", 83))
    atr_period = int(conf.get("ma_atr_period", 14))
    lookback = int(conf.get("structure_lookback", 12))
    return _ema_structure_from_rows(
        rows, fast_period=fast, slow_period=slow, atr_period=atr_period,
        lookback=lookback, buffer_atr=float(conf.get("structure_buffer_atr", 0.50))
    )


def _calculate_dynamic_protection_stop(exchange, symbol, side, current_price, strategy, conf):
    """交易所兜底单：结构位 + ATR，不把 EMA 当成直接止损线。
    只允许止损随着盈利方向移动，调用方负责与已有订单比较。
    """
    atr = float(strategy.get("atr") or 0)
    if atr <= 0:
        return _calculate_disaster_stop(exchange, symbol, side, current_price, atr, conf)

    buffer = max(0.0, float(conf.get("structure_buffer_atr", 0.50)))
    fallback_mult = max(1.0, float(conf.get("hard_stop_atr_multiplier", 6.0)))
    max_dist = max(0.01, float(conf.get("dynamic_stop_max_distance_pct", 0.12)))
    min_dist = max(0.0, float(conf.get("hard_stop_min_distance_pct", 0.05)))

    if side == "long":
        candidate = float(strategy["swing_low"]) - atr * buffer
        fallback = current_price * (1.0 - fallback_mult * atr / current_price)
        # 结构止损过近/过远时退回 ATR 保护，避免刚好贴着价格或离得异常远。
        dist = (current_price - candidate) / current_price
        if dist < min_dist or dist > max_dist:
            candidate = fallback
        stop = min(candidate, current_price * (1.0 - min_dist))
    else:
        candidate = float(strategy["swing_high"]) + atr * buffer
        fallback = current_price * (1.0 + fallback_mult * atr / current_price)
        dist = (candidate - current_price) / current_price
        if dist < min_dist or dist > max_dist:
            candidate = fallback
        stop = max(candidate, current_price * (1.0 + min_dist))

    return float(exchange.price_to_precision(symbol, stop)), (abs(current_price - stop) / current_price)


def _calculate_disaster_stop(exchange, symbol, side, current_price, atr_value, conf):
    min_pct = max(0.0, float(conf.get("hard_stop_min_distance_pct", 0.05)))
    atr_mult = max(0.0, float(conf.get("hard_stop_atr_multiplier", 6.0)))
    distance = max(min_pct, (atr_value * atr_mult / current_price) if atr_value else 0.0)
    stop = current_price * (1.0 - distance if side == "long" else 1.0 + distance)
    return float(exchange.price_to_precision(symbol, stop)), distance


def _continuous_trailing_stop(pos_state, side, current_price, atr, conf):
    """连续移动止损（纯计算）：浮盈达到 trailing_trigger_r 后，止损线按
    ``current_price ± trailing_atr_multiple × ATR`` 随价格平滑追踪。

    与阶梯保护（_take_profit_protection_stop）互补：调用方负责与阶梯/策略
    止损取盈利方向的 max/min。返回 (追踪止损价或 None, 浮盈R)。

    安全约束：
    - mode != 'continuous' 或缺少 entry/risk/ATR 时不追踪，返回 None；
    - 追踪线必须在开仓价的盈利侧（浮盈为正才有意义），亏损侧直接放弃。
    """
    mode = str(conf.get("trailing_stop_mode", "step") or "step").lower()
    if mode != "continuous":
        return None, 0.0

    price = float(current_price or 0.0)
    atr = float(atr or 0.0)
    if price <= 0 or atr <= 0:
        return None, 0.0

    entry = float(pos_state.get("tp_entry_price") or 0.0)
    risk = float(pos_state.get("tp_risk_distance") or 0.0)
    if entry <= 0 or risk <= 0:
        return None, 0.0

    floating_r = ((price - entry) / risk) if side == "long" else ((entry - price) / risk)
    trigger_r = max(0.0, float(conf.get("trailing_trigger_r", 1.0)))
    if floating_r < trigger_r:
        return None, floating_r

    mult = max(0.5, float(conf.get("trailing_atr_multiple", 2.0)))
    trail = price - atr * mult if side == "long" else price + atr * mult

    # 追踪线必须在盈利侧：多单 trail > entry、空单 trail < entry，否则不启用。
    if side == "long" and trail <= entry:
        return None, floating_r
    if side == "short" and trail >= entry:
        return None, floating_r

    return float(trail), floating_r
