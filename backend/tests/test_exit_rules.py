"""出场规则测试：实盘挂单与纸面跟踪共用同一份计算（core.exit_rules）。

覆盖：
- percent 模式：按保证金百分比 ÷ 杠杆折算价格（与原有止盈止损口径一致），多空对称；
- atr 模式：止损 = N×ATR，止盈 = R×止损距离；
- 该方向未启用止盈止损、参数为 0、缺 ATR 时返回 None；
- 纸面跟踪在 percent 模式下开出的止损/止盈与 exit_rules 完全一致。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import database, exit_rules  # noqa: E402
from app.signals.signal_store import SignalStore  # noqa: E402
from app.signals.tracker import OutcomeTracker  # noqa: E402
from tests.test_signal_tracker import (  # noqa: E402
    FakeMarket, flat_rows, make_bars, make_signal, paper_settings,
)

BASE = {
    'enable_long_sl_tp': True,
    'enable_short_sl_tp': True,
    'long_stop_loss_percentage': 50.0,
    'long_take_profit_percentage': 100.0,
    'short_stop_loss_percentage': 80.0,
    'short_take_profit_percentage': 150.0,
    'leverage': 20,
    'signal_exit_mode': 'percent',
    'signal_paper_sl_atr': 1.5,
    'signal_paper_tp_r': 2.0,
}


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()


def test_percent_mode_long_uses_leverage():
    """20 倍杠杆：保证金止损 50% -> 价格 -2.5%；止盈 100% -> 价格 +5%。"""
    prices = exit_rules.exit_prices(100.0, "long", BASE)
    assert prices['mode'] == 'percent'
    assert prices['stop_loss'] == pytest.approx(97.5)
    assert prices['take_profit'] == pytest.approx(105.0)


def test_percent_mode_short_uses_leverage():
    """空头：止损 80%/20x -> +4%；止盈 150%/20x -> -7.5%。"""
    prices = exit_rules.exit_prices(100.0, "short", BASE)
    assert prices['stop_loss'] == pytest.approx(104.0)
    assert prices['take_profit'] == pytest.approx(92.5)


def test_percent_mode_respects_direction_switch():
    config = {**BASE, 'enable_long_sl_tp': False}
    assert exit_rules.exit_prices(100.0, "long", config) is None
    assert exit_rules.exit_prices(100.0, "short", config) is not None


def test_percent_mode_zero_percentages_returns_none():
    config = {**BASE, 'long_stop_loss_percentage': 0.0, 'long_take_profit_percentage': 0.0}
    assert exit_rules.exit_prices(100.0, "long", config) is None


def test_atr_mode_prices():
    prices = exit_rules.exit_prices(100.0, "long", {**BASE, 'signal_exit_mode': 'atr'}, atr=2.0)
    assert prices['mode'] == 'atr'
    assert prices['stop_loss'] == pytest.approx(97.0)    # 1.5 × 2
    assert prices['take_profit'] == pytest.approx(106.0)  # 2R


def test_forced_percent_mode_ignores_atr_setting():
    """实盘挂单强制 percent：即使全局切到 atr 模式也必须挂出百分比止损（否则等于裸奔）。"""
    config = {**BASE, 'signal_exit_mode': 'atr'}
    prices = exit_rules.exit_prices(100.0, 'long', config, mode=exit_rules.PERCENT_MODE)
    assert prices['mode'] == 'percent'
    assert prices['stop_loss'] == pytest.approx(97.5)


def test_atr_mode_without_atr_returns_none():
    assert exit_rules.exit_prices(100.0, "long", {**BASE, 'signal_exit_mode': 'atr'}, atr=None) is None


def test_tracker_uses_same_prices_in_percent_mode():
    """纸面开仓的止损/止盈必须等于 exit_rules 的结果（不允许出现两套算法）。"""
    settings = paper_settings(signal_exit_mode='percent', leverage=20)
    rows = flat_rows(20)
    tracker = OutcomeTracker(lambda: settings, FakeMarket(make_bars(rows)), SignalStore())
    signal = make_signal()
    tracker._store.add(signal)
    asyncio.run(tracker.on_signal(signal))
    asyncio.run(tracker.tick())

    position = tracker.snapshot()['open_positions'][0]
    expected = exit_rules.exit_prices(position['entry_price'], 'long', settings, atr=position['atr'])
    assert position['stop_loss'] == pytest.approx(expected['stop_loss'])
    assert position['take_profit'] == pytest.approx(expected['take_profit'])
    assert position['exit_mode'] == 'percent'
