# backend/app/signals/outcomes.py
"""信号结果计算的纯函数层（无 I/O，便于单测与离线回测复用）。

三个能力，供纸面跟踪与「信号前视收益」共用：
1. `to_frame` / `bar_index`：把 ccxt K 线转 DataFrame 并按时间戳定位；
2. `simulate_exit`：从入场 bar 起逐根检查 ATR 止损 / R 倍数止盈 / 超时，返回出场信息；
3. `forward_return`：信号后第 N 根 K 线的收益（入场取信号次根开盘，与回测口径一致）。
"""
import math
from typing import Any, Dict, List, Optional

import pandas as pd

OHLCV_COLUMNS = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
ATR_PERIOD = 14


def to_frame(raw: List[list]) -> pd.DataFrame:
    """ccxt/交易所原始 K 线 -> DataFrame，并附带 ATR 列（简单移动平均 TR）。"""
    df = pd.DataFrame(raw, columns=OHLCV_COLUMNS)
    prev_close = df['close'].shift(1)
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - prev_close).abs(),
        (df['low'] - prev_close).abs(),
    ], axis=1).max(axis=1)
    df['atr'] = tr.rolling(ATR_PERIOD).mean()
    return df


def bar_index(df: pd.DataFrame, timestamp_ms: int) -> Optional[int]:
    """按 K 线开盘时间戳定位下标；找不到返回 None。"""
    matches = df.index[df['timestamp'] == int(timestamp_ms)].tolist()
    return int(matches[0]) if matches else None


def atr_at(df: pd.DataFrame, index: int) -> Optional[float]:
    """取某个 bar 的 ATR；不足周期或为 NaN 时返回 None。"""
    if index < 0 or index >= len(df):
        return None
    value = float(df['atr'].iloc[index])
    return None if math.isnan(value) or value <= 0 else value


def forward_return(df: pd.DataFrame, index: int, bars: int, direction: str) -> Optional[float]:
    """信号后持有 bars 根 K 线的方向性收益（入场 = 信号次根开盘，出场 = 第 bars 根收盘）。

    与离线回测口径一致：信号 bar 收盘入场不现实，统一用下一根开盘价；
    持有 1 根 = 入场那根的开盘到收盘。
    """
    entry_idx = index + 1
    exit_idx = entry_idx + int(bars) - 1
    if bars <= 0 or entry_idx >= len(df) or exit_idx >= len(df):
        return None
    entry = float(df['open'].iloc[entry_idx])
    if entry <= 0:
        return None
    ret = float(df['close'].iloc[exit_idx]) / entry - 1
    return ret if direction == 'long' else -ret if direction == 'short' else None


def simulate_exit(df: pd.DataFrame, index: int, direction: str, entry_price: float,
                  stop_loss: Optional[float], take_profit: Optional[float],
                  max_bars: int) -> Optional[Dict[str, Any]]:
    """逐根检查止损/止盈/超时，返回 {exit_price, exit_ts, bars_held, reason}。

    stop_loss / take_profit 允许为 None（该方向只启用了一边，或走纯时间止损）。

    - 从信号**次根**开始检查（信号 bar 已收线，不能假装在里面成交）；
    - 同一根内止损与止盈都触及时按**止损优先**（保守，避免回测偏乐观）；
    - 跳空开盘越过触发价时按开盘价成交（不按理论价，避免虚高）。
    """
    entry_idx = index + 1
    if entry_idx >= len(df) or max_bars <= 0 or entry_price <= 0:
        return None
    # 窗口未走完时只允许止损/止盈触发；超时平仓必须等最后一根到齐，否则会在半路误判
    window_end = entry_idx + int(max_bars)
    last_idx = min(window_end, len(df) - 1)
    window_complete = window_end <= len(df) - 1
    is_long = direction == 'long'

    for j in range(entry_idx, last_idx + 1):
        high = float(df['high'].iloc[j])
        low = float(df['low'].iloc[j])
        open_px = float(df['open'].iloc[j])
        hit_stop = stop_loss is not None and (low <= stop_loss if is_long else high >= stop_loss)
        hit_target = take_profit is not None and (high >= take_profit if is_long else low <= take_profit)
        if hit_stop:
            exit_px = min(stop_loss, open_px) if is_long else max(stop_loss, open_px)
            return _exit(exit_px, df, j, entry_idx, 'stop')
        if hit_target:
            exit_px = max(take_profit, open_px) if is_long else min(take_profit, open_px)
            return _exit(exit_px, df, j, entry_idx, 'target')

    if not window_complete:
        return None
    exit_px = float(df['close'].iloc[last_idx])
    return _exit(exit_px, df, last_idx, entry_idx, 'time')


def _exit(price: float, df: pd.DataFrame, index: int, entry_idx: int, reason: str) -> Dict[str, Any]:
    return {
        'exit_price': price,
        'exit_ts': int(df['timestamp'].iloc[index]),
        'bars_held': index - entry_idx + 1,
        'reason': reason,
    }
