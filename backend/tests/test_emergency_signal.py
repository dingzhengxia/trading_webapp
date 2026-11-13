"""黑天鹅判定：零成交 K 线不得把 ATR / 均量拉低，导致盘中正常回落被判全平。

回归 2026-11-13 TQQQ 事件：股票代币在美股休市时段产出 O=H=L=C、volume=0 的 15m K 线，
把 ATR 与 20 根均量同时拉到极低（实测 ATR 0.096，真实应为 0.6），
结果开盘后一次 1.7% 的正常回落就满足「放量 + 3×ATR」，被市价全平。

约定：只保留有成交的 K 线做基准；有成交 K 线不足时不判定（宁可不动手）。
"""
from __future__ import annotations

import asyncio

from app.protection.market_data import _emergency_signal

COLS = ["timestamp", "open", "high", "low", "close", "volume"]

CONF = {
    'emergency_enabled': True,
    'emergency_timeframe': '15m',
    'emergency_atr_period': 14,
    'emergency_atr_multiplier': 3.0,
    'emergency_vol_multiplier': 3.0,
    'emergency_structure_lookback': 4,
}

# 三类 K 线：(open, high, low, close), volume
IDLE = ((59.5, 59.5, 59.5, 59.5), 0.0)        # 休市：零成交、价格不动
PRE = ((60.0, 60.05, 59.95, 60.0), 5.0)       # 盘前：微成交、几乎不动
DAY = ((60.0, 60.4, 59.8, 60.1), 100.0)       # 盘中：正常成交与波动


def _rows(spec, live):
    rows = [(i, *ohlc, vol) for i, (ohlc, vol) in enumerate(spec)]
    rows.append((len(spec), *live))
    return rows


def _fire(rows):
    return asyncio.run(
        _emergency_signal(None, 'X/USDT:USDT', 'long', CONF, live_rows=rows)
    )


def test_idle_candles_do_not_fake_a_crash():
    """美股开盘后 14 分钟：窗口内几乎全是休市/盘前 K 线，不能判定黑天鹅。"""
    rows = _rows([IDLE] * 50 + [PRE] * 9, (60.0, 60.4, 58.95, 59.0, 500.0))
    triggered, details = _fire(rows)
    assert triggered is False, f'零成交 K 线污染仍触发全平: {details}'


def test_normal_move_during_session_does_not_trigger():
    """盘中正常成交（ATR 真实），1.0 的回落远不到 3×ATR，不应触发。"""
    rows = _rows([IDLE] * 34 + [DAY] * 25, (60.0, 60.1, 58.95, 59.0, 500.0))
    triggered, details = _fire(rows)
    assert triggered is False, f'正常回落被误判: {details}'


def test_crypto_calm_market_does_not_trigger():
    """24h 连续交易的加密标的：过滤前后基准一致，行为不得变化。"""
    rows = _rows([DAY] * 59, (60.0, 60.1, 58.95, 59.0, 500.0))
    triggered, details = _fire(rows)
    assert triggered is False, f'加密正常行情被误判: {details}'


def test_real_crash_still_triggers():
    """真实闪崩（位移 2.8 远超 3×ATR=1.8）必须仍然触发，不能修过头。"""
    rows = _rows([DAY] * 59, (60.0, 60.1, 57.0, 57.2, 900.0))
    triggered, details = _fire(rows)
    assert triggered is True, '真闪崩被漏判'
    assert details['move'] > details['threshold']


def test_volume_spike_requires_multiplier():
    """放量门槛是均量的 3 倍：2 倍量不足以单独构成「放量加速」。"""
    rows = _rows([DAY] * 59, (60.0, 60.1, 59.35, 59.4, 200.0))
    triggered, details = _fire(rows)
    assert details['volume_crash'] is False
