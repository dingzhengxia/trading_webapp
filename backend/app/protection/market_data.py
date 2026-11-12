"""仓位保护行情快照与指标计算：K线/ATR/EMA、REST 缓存拉取与黑天鹅信号（T08 自 engine.py 拆出）。"""

import time

import pandas as pd
from loguru import logger

from .config import _f
from .state import RUNTIME, _rest, _position_side, _position_size


# ---------------------------------------------------------------------------
# Indicators & Market signals
# ---------------------------------------------------------------------------

def _closed_df(rows):
    if not rows or len(rows) < 3:
        raise RuntimeError("K线数据不足")
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    return df.iloc[:-1].copy()


def _atr_from_df(df, period):
    if len(df) < period + 1:
        return None
    prev = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev).abs(),
        (df["low"] - prev).abs(),
    ], axis=1).max(axis=1)

    value = _f(tr.rolling(period).mean().iloc[-1])
    return value if value and value > 0 else None


def _atr_from_rows(rows, period):
    atr = _atr_from_df(_closed_df(rows), period)
    if not atr:
        raise RuntimeError("ATR 无效")
    return float(atr)


def _ema_value(series, period):
    if len(series) < period:
        return None
    value = series.ewm(span=period, adjust=False).mean().iloc[-1]
    return _f(value, None)


def _ema_structure_from_rows(rows, fast_period=26, slow_period=83, atr_period=14,
                             lookback=12, buffer_atr=0.50):
    """只使用已收盘K线计算 EMA + 结构位，避免当前未收盘K线造成假触发。"""
    df = _closed_df(rows)
    need = max(slow_period + 2, atr_period + 2, lookback + 2)
    if len(df) < need:
        raise RuntimeError(f"K线不足 {need} 根，无法计算 EMA/结构止损")

    ema_fast = _ema_value(df["close"], fast_period)
    ema_slow = _ema_value(df["close"], slow_period)
    atr = _atr_from_df(df, atr_period)
    if not ema_fast or not ema_slow or not atr:
        raise RuntimeError("EMA/ATR 无效")

    recent = df.iloc[-lookback:]
    swing_low = float(recent["low"].min())
    swing_high = float(recent["high"].max())
    last_close = float(df.iloc[-1]["close"])
    closed_ts = int(df.iloc[-1]["timestamp"])

    # 趋势过滤：EMA26/EMA83 只负责判断趋势，不直接作为止损价。
    trend = "bull" if ema_fast > ema_slow else "bear"
    if abs(ema_fast - ema_slow) <= atr * 0.05:
        trend = "neutral"

    long_structure = swing_low - atr * buffer_atr
    short_structure = swing_high + atr * buffer_atr
    return {
        "ema_fast": float(ema_fast), "ema_slow": float(ema_slow),
        "atr": float(atr), "swing_low": swing_low, "swing_high": swing_high,
        "long_structure": float(long_structure), "short_structure": float(short_structure),
        "last_close": last_close, "closed_ts": closed_ts, "trend": trend, "df": df,
    }


# ---------------------------------------------------------------------------
# REST 拉取（带 RUNTIME 缓存）
# ---------------------------------------------------------------------------

async def _fetch_positions(exchange, conf, symbols=None, priority="NORMAL", force=False):
    ttl = float(conf.get("positions_cache_ttl_sec", 5))
    now = time.monotonic()
    ts, cached = RUNTIME.positions_cache
    if not force and symbols is None and cached is not None and now - ts < ttl:
        return cached

    target_symbols = None if not symbols else symbols
    positions = await _rest(exchange, "fetch_positions", target_symbols, priority=priority, conf=conf)

    if symbols is None:
        RUNTIME.positions_cache = (time.monotonic(), positions)
    return positions


async def _fetch_ticker(exchange, symbol, conf, priority="NORMAL", force=False):
    ttl = float(conf.get("ticker_cache_ttl_sec", 3))
    now = time.monotonic()
    cached = RUNTIME.ticker_cache.get(symbol)
    if not force and cached and now - cached[0] < ttl:
        return cached[1]

    ticker = await _rest(exchange, "fetch_ticker", symbol, priority=priority, conf=conf)
    RUNTIME.ticker_cache[symbol] = (time.monotonic(), ticker)
    return ticker


async def _fetch_ohlcv(exchange, symbol, timeframe, limit, conf, priority="LOW", force=False):
    key = (symbol, timeframe, limit)
    # 【核心优化】使用 30s 的 OHLCV 高缓存，彻底杜绝 1h K线引起的 429 限流
    ttl = float(conf.get("ohlcv_cache_ttl_sec", 30.0))
    now = time.monotonic()
    cached = RUNTIME.ohlcv_cache.get(key)
    if not force and cached and now - cached[0] < ttl:
        return cached[1]

    rows = await _rest(exchange, "fetch_ohlcv", symbol, timeframe, None, limit, priority=priority, conf=conf)
    RUNTIME.ohlcv_cache[key] = (time.monotonic(), rows)
    return rows


async def _closed_atr(exchange, symbol, timeframe, period, conf, force=False):
    rows = await _fetch_ohlcv(exchange, symbol, timeframe, max(period + 30, 60), conf, force=force)
    return _atr_from_rows(rows, period)


async def _market_snapshot(exchange, symbol, conf, priority="NORMAL", force=False):
    ticker = await _fetch_ticker(exchange, symbol, conf, priority=priority, force=force)
    mark = _f(ticker.get("mark"))
    last = _f(ticker.get("last") or ticker.get("close"))
    price = mark or last
    if not price or price <= 0:
        raise RuntimeError(f"[{symbol}] 无有效 ticker/mark price")
    return {"price": price, "mark": mark or price, "last": last or price, "timestamp": time.time()}


async def _position_fresh(exchange, symbol, side, conf, priority="HIGH"):
    positions = await _fetch_positions(exchange, conf, symbols=[symbol], priority=priority, force=True)
    for p in positions:
        if _position_size(p) > 0 and _position_side(p) == side:
            return p
    return None


async def _two_source_price_ok(exchange, symbol, ws_price, side, conf):
    snap = await _market_snapshot(exchange, symbol, conf, priority="HIGH", force=True)
    rest_price = snap["mark"] or snap["price"]
    tolerance = max(0.003, float(conf.get("price_source_tolerance_pct", 0.01)))
    diff = abs(rest_price - ws_price) / max(rest_price, 1e-12)
    if diff > tolerance:
        logger.warning(f"[{symbol}] 行情双源不一致 WS={ws_price} REST={rest_price} diff={diff:.3%}")
        return False, snap
    return True, snap


async def _emergency_signal(exchange, symbol, side, conf, live_rows=None):
    tf = str(conf.get("emergency_timeframe", "15m"))
    enabled = conf.get("emergency_enabled", True)
    if not enabled:
        return False, None
    period = int(conf.get("emergency_atr_period", 14))
    mult = float(conf.get("emergency_atr_multiplier", 3.0))
    volmult = float(conf.get("emergency_vol_multiplier", 1.0))
    lookback = int(conf.get("emergency_structure_lookback", 4))
    limit = max(period + lookback + 25, 60)

    rows = live_rows or await _fetch_ohlcv(exchange, symbol, tf, limit, conf, priority="LOW", force=False)
    if not rows or len(rows) < period + lookback + 2:
        return False, None

    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    closed = df.iloc[:-1].copy()
    atr = _atr_from_df(closed, period)
    if not atr:
        return False, None

    vol_ma = closed["volume"].rolling(20).mean().iloc[-1]

    live = df.iloc[-1]
    ws_price = float(live["close"])
    live_vol = float(live["volume"])
    threshold = atr * mult

    is_volume_spike = bool(vol_ma and vol_ma > 0 and live_vol > vol_ma * volmult)

    if side == "long":
        move = float(live["open"] - ws_price) if ws_price < live["open"] else 0.0
        structure = ws_price < float(closed["low"].iloc[-lookback:].min())
        volume_crash = is_volume_spike and move >= (atr * mult)
    else:
        move = float(ws_price - live["open"]) if ws_price > live["open"] else 0.0
        structure = ws_price > float(closed["high"].iloc[-lookback:].max())
        volume_crash = is_volume_spike and move >= (atr * mult)

    is_emergency = bool((move >= threshold and structure) or volume_crash)
    reason = "放量加速暴跌/拉升" if volume_crash else "结构性黑天鹅"

    return is_emergency, {
        "ws_price": ws_price, "move": move, "threshold": threshold,
        "structure": structure, "volume_crash": volume_crash, "reason": reason
    }
