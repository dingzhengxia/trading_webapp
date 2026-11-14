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


# ---------------------------------------------------------------------------
# 位移锚点：只归因「持仓期间」的行情（2026-11-14 ETH 开仓 16 秒被全平）
#
# 15m 的 22:00 那根从 1891.5 跌到 1867.6（整根位移 23.97 > 阈值 20.37），
# 但仓位是 22:05:54 在 1868.66 才建立的——入场后只浮亏 1.08（0.06%），
# 却被判成闪崩市价全平。位移必须按入场价起算。
# ---------------------------------------------------------------------------
BASE_MS = 1_790_000_000_000
TF_MS = 900_000  # 15m


def _ts_rows(spec, live):
    rows = [(BASE_MS + i * TF_MS, *ohlc, vol) for i, (ohlc, vol) in enumerate(spec)]
    rows.append((BASE_MS + len(spec) * TF_MS, *live))
    return rows


# 崩盘前的 15m K 线：价格 1885 附近，单根振幅 7 → ATR≈7，3×ATR≈21（价格 1% 下限 18.7）
ETH_CALM = ((1885.0, 1888.5, 1881.5, 1884.0), 150.0)
# 出事那根：开盘 1891.5，一路砸到 1867.58（跌破前 4 根低点 1878）
ETH_CRASH_LIVE = (1891.5, 1892.0, 1867.0, 1867.58, 150.0)
BAR_OPEN_TS = BASE_MS / 1000 + 59 * (TF_MS / 1000)  # 本根 K 线开盘时间（秒）


def _fire_anchor(rows, entry_price=0.0, entry_ts=0.0):
    return asyncio.run(_emergency_signal(
        None, 'ETH/USDC:USDC', 'long', CONF, live_rows=rows,
        entry_price=entry_price, entry_ts=entry_ts))


def test_crash_before_entry_does_not_close_new_position():
    """ETH 事故复现：入场前的跌幅不得算到新仓头上。"""
    rows = _ts_rows([ETH_CALM] * 59, ETH_CRASH_LIVE)
    triggered, details = _fire_anchor(rows, entry_price=1868.66,
                                      entry_ts=BAR_OPEN_TS + 354)  # 22:05:54，本根第 354 秒
    assert triggered is False, f'入场前的跌幅把新仓平掉了: {details}'
    assert details['anchored_at_entry'] is True
    assert details['move'] == pytest.approx(1.08, abs=0.01)
    # 同一根 K 线：不做锚点时（入场前就持有）仍然必须开枪，证明没有修过头
    triggered_legacy, legacy = _fire_anchor(rows)
    assert triggered_legacy is True, f'真跌势被漏判: {legacy}'
    assert legacy['move'] == pytest.approx(23.92, abs=0.01)


def test_position_held_before_bar_uses_bar_open():
    """仓位早于本根 K 线建立 → 整根 K 线的跌幅都发生在持仓期间，仍按开盘价起算。"""
    rows = _ts_rows([ETH_CALM] * 59, ETH_CRASH_LIVE)
    triggered, details = _fire_anchor(rows, entry_price=1900.0,
                                      entry_ts=BAR_OPEN_TS - 600)
    assert triggered is True
    assert details['anchored_at_entry'] is False
    assert details['anchor'] == pytest.approx(1891.5)


def test_crash_after_entry_still_triggers():
    """入场后继续暴跌（从 1868.66 跌到 1840）→ 必须平，保护不能被削弱。"""
    rows = _ts_rows([ETH_CALM] * 59, (1891.5, 1892.0, 1839.0, 1840.0, 150.0))
    triggered, details = _fire_anchor(rows, entry_price=1868.66,
                                      entry_ts=BAR_OPEN_TS + 354)
    assert triggered is True, f'入场后真闪崩被漏判: {details}'
    assert details['move'] == pytest.approx(28.66, abs=0.01)
    assert details['move'] >= details['threshold']
