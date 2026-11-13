"""黑天鹅判定：零成交 K 线不得把 ATR / 均量拉低，阈值也不得脱离标的自身的价格尺度。

回归两起误杀：
· 2026-11-13 TQQQ：股票代币在美股休市时段产出 O=H=L=C、volume=0 的 15m K 线，
  把 ATR 与 20 根均量同时拉到极低（实测 ATR 0.096，真实应为 0.6），开盘后一次 1.7% 的正常回落即被全平。
· 2026-11-13 AAPL：ATR 口径已修好，但 ATR(14) 只覆盖 3.5 小时，急涨后的窄幅整理把 ATR 压到
  0.756（占价 0.21%），3×ATR 仅 0.63%，一根 0.67% 的放量回落就成了「黑天鹅」。

约定：只留有成交 K 线做基准；有成交 K 线不足时不判定；位移门槛再与「价格 × 1%」取大，
放量分支（无结构确认）另用更高倍数。
"""
from __future__ import annotations

import asyncio

import pytest

from app.protection.market_data import _emergency_signal

COLS = ["timestamp", "open", "high", "low", "close", "volume"]

CONF = {
    'emergency_enabled': True,
    'emergency_timeframe': '15m',
    'emergency_atr_period': 14,
    'emergency_atr_multiplier': 3.0,
    'emergency_vol_multiplier': 3.0,
    'emergency_vol_atr_multiplier': 4.0,
    'emergency_min_move_pct': 0.01,
    'emergency_structure_lookback': 4,
}

# 三类 K 线：(open, high, low, close), volume
IDLE = ((59.5, 59.5, 59.5, 59.5), 0.0)        # 休市：零成交、价格不动
PRE = ((60.0, 60.05, 59.95, 60.0), 5.0)       # 盘前：微成交、几乎不动
DAY = ((60.0, 60.4, 59.8, 60.1), 100.0)       # 盘中：正常成交与波动
# AAPL 真实尺度（2026-11-13 23:14 那根）：ATR≈0.8（占价 0.22%）
AAPL_DAY = ((357.9, 358.2, 357.4, 357.8), 100.0)


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


def test_aapl_low_atr_trap_does_not_trigger():
    """AAPL 那根：ATR 0.8(0.22%)、3×ATR 仅 2.4，但位移 2.41(0.67%) 不到价格的 1%。

    这是 ATR 的固有陷阱——窗口只覆盖 3.5 小时，窄幅整理后一根中等阴线就是「3 倍」。
    价格百分比下限（357.74 × 1% = 3.58）必须挡住它，否则每次急涨后回落都会全平。
    """
    rows = _rows([AAPL_DAY] * 59, (360.15, 360.2, 357.7, 357.74, 400.0))
    triggered, details = _fire(rows)
    assert details['volume_crash'] is False, f'放量回落被误判为黑天鹅: {details}'
    assert triggered is False, f'正常回落被误判全平: {details}'
    assert details['threshold'] == pytest.approx(357.74 * 0.01, rel=1e-6)


def test_aapl_real_flash_crash_still_triggers():
    """同一标的真闪崩（15m 跌 3.4%）必须仍然触发，下限不能把熔断关掉。"""
    rows = _rows([AAPL_DAY] * 59, (360.15, 360.2, 347.9, 348.0, 400.0))
    triggered, details = _fire(rows)
    assert triggered is True, '真闪崩被漏判'
    assert details['volume_crash'] is True


def test_volume_branch_stricter_than_structure_branch():
    """放量分支没有结构确认，位移门槛必须高于结构分支（4×ATR vs 3×ATR）。

    价格 10、ATR≈0.2：move 0.7 只到 3.5×ATR——够结构分支，不够放量分支。
    """
    rows = _rows([((10.0, 10.1, 9.9, 10.0), 100.0)] * 59, (10.0, 10.05, 9.28, 9.3, 400.0))
    triggered, details = _fire(rows)
    assert details['volume_crash'] is False
    assert details['volume_threshold'] > details['structure_threshold']
