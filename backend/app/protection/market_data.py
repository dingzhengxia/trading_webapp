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
    volmult = float(conf.get("emergency_vol_multiplier", 3.0))
    vol_atr_mult = float(conf.get("emergency_vol_atr_multiplier", 4.0))
    lookback = int(conf.get("emergency_structure_lookback", 4))
    limit = max(period + lookback + 25, 60)

    rows = live_rows or await _fetch_ohlcv(exchange, symbol, tf, limit, conf, priority="LOW", force=False)
    if not rows or len(rows) < period + lookback + 2:
        return False, None

    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    closed = df.iloc[:-1].copy()
    # 股票代币等非 24h 合约在休市时段会产出 O=H=L=C、volume=0 的 K 线，
    # 把 ATR 与 20 根均量同时拉到极低，导致盘中一次正常回调就被判成「放量加速」
    # （2026-11-13 TQQQ 即在横盘中因 1.7% 回落被市价全平）。基准只用有成交的 K 线：
    # 加密 24h 连续交易几乎没有零成交 K 线，此过滤对加密标的不产生实质影响。
    traded = closed[closed["volume"] > 0]
    if len(traded) < period + 2:
        # 有成交 K 线不足（长休市/停牌/新上市）：此时任何 ATR 都是被零成交污染的，
        # 拿它判定等于随机开枪。宁可不动手——没有成交也就不存在需要躲的闪崩。
        return False, None
    atr = _atr_from_df(traded, period)
    if not atr:
        return False, None

    # 窗口自适应：过滤后可能不足 20 根，固定 20 会让 vol_ma 变 NaN、放量分支永不触发
    vol_ma = traded["volume"].rolling(min(20, len(traded))).mean().iloc[-1]

    live = df.iloc[-1]
    ws_price = float(live["close"])
    live_vol = float(live["volume"])
    # 阈值 = max(倍数 × ATR, 价格 × 绝对下限)，两个下限各有分工：
    # · ATR(14) 只覆盖最近 3.5 小时。急涨/急跌后的窄幅整理会把 ATR 压得很低，随后
    #   一根中等阴线就成「数倍 ATR」——2026-11-13 AAPL 即如此：ATR 0.756(占价 0.21%)，
    #   3×ATR 只有 0.63%，一根 0.67% 的回落（当日振幅的 38%）就被市价全平。
    # · 价格百分比下限按标的自身尺度兜底：对日波动 ~1.8% 的标的，15m 位移 1% 约 5σ，
    #   属月度级事件；而加密真闪崩（15m 2~3%）远高于该下限，不会因此漏判。
    # · 放量分支不需要结构确认，所以倍数单独提到 4（结构分支仍是 3，它本来就有破位确认）。
    floor = ws_price * max(0.0, _f(conf.get("emergency_min_move_pct"), 0.01))
    struct_threshold = max(atr * mult, floor)
    vol_threshold = max(atr * vol_atr_mult, floor)

    is_volume_spike = bool(vol_ma and vol_ma > 0 and live_vol > vol_ma * volmult)

    if side == "long":
        move = float(live["open"] - ws_price) if ws_price < live["open"] else 0.0
        structure = ws_price < float(closed["low"].iloc[-lookback:].min())
    else:
        move = float(ws_price - live["open"]) if ws_price > live["open"] else 0.0
        structure = ws_price > float(closed["high"].iloc[-lookback:].max())

    volume_crash = is_volume_spike and move >= vol_threshold
    is_emergency = bool((move >= struct_threshold and structure) or volume_crash)
    reason = "放量加速暴跌/拉升" if volume_crash else "结构性黑天鹅"

    return is_emergency, {
        "ws_price": ws_price, "move": move,
        "threshold": vol_threshold if volume_crash else struct_threshold,
        "structure_threshold": struct_threshold, "volume_threshold": vol_threshold,
        "structure": structure, "volume_crash": volume_crash, "reason": reason
    }
