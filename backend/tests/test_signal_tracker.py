"""结果跟踪测试：前视收益 + 纸面持仓（离线，用假行情，不触网）。

覆盖：
- outcomes.simulate_exit：止损 / 止盈 / 超时 / 窗口未走完不判超时 / 跳空按开盘价成交；
- outcomes.forward_return：入场取信号次根开盘，方向取反正确；
- OutcomeTracker：纸面开关、过滤链复用、开仓 -> 结算 -> 统计、前视结果落库幂等。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pandas as pd
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import database  # noqa: E402
from app.signals import outcomes, tracker as tracker_module  # noqa: E402
from app.signals.signal_store import SignalStore  # noqa: E402
from app.signals.tracker import OutcomeTracker  # noqa: E402

HOUR_MS = 3_600_000


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()


def make_bars(rows):
    """rows: [(open, high, low, close)] -> ccxt 风格 K 线（时间戳从 0 起每根 1h）。"""
    return [[i * HOUR_MS, o, h, l, c, 1000.0] for i, (o, h, l, c) in enumerate(rows)]


def flat_rows(count=20, price=100.0, spread=0.5):
    return [(price, price + spread, price - spread, price) for _ in range(count)]


# ------------------------------------------------------------------ 纯函数
def test_simulate_exit_hits_stop():
    rows = flat_rows(20)
    rows[16] = (100.0, 100.5, 98.5, 99.0)
    df = outcomes.to_frame(make_bars(rows))
    result = outcomes.simulate_exit(df, 15, "long", 100.0, 99.0, 102.0, max_bars=3)
    assert result["reason"] == "stop"
    assert result["exit_price"] == pytest.approx(99.0)
    assert result["bars_held"] == 1


def test_simulate_exit_hits_target():
    rows = flat_rows(20)
    rows[17] = (100.0, 102.5, 99.5, 102.0)
    df = outcomes.to_frame(make_bars(rows))
    result = outcomes.simulate_exit(df, 15, "long", 100.0, 99.0, 102.0, max_bars=3)
    assert result["reason"] == "target"
    assert result["exit_price"] == pytest.approx(102.0)
    assert result["bars_held"] == 2


def test_simulate_exit_gap_uses_open_price():
    """跳空越过止损时按开盘价成交，不能假装在理论价出场。"""
    rows = flat_rows(20)
    rows[16] = (97.0, 97.5, 96.5, 97.0)
    df = outcomes.to_frame(make_bars(rows))
    result = outcomes.simulate_exit(df, 15, "long", 100.0, 99.0, 102.0, max_bars=2)
    assert result["exit_price"] == pytest.approx(97.0)
    assert result["reason"] == "stop"


def test_simulate_exit_waits_for_full_window():
    """窗口没走完又没触发止损止盈时返回 None，避免半路误判超时。"""
    df = outcomes.to_frame(make_bars(flat_rows(17)))
    assert outcomes.simulate_exit(df, 15, "long", 100.0, 99.0, 102.0, max_bars=3) is None


def test_forward_return_direction_and_entry():
    rows = flat_rows(20)
    rows[16] = (100.0, 101.0, 99.5, 101.0)
    rows[17] = (101.0, 102.0, 100.5, 102.0)
    df = outcomes.to_frame(make_bars(rows))
    assert outcomes.forward_return(df, 15, 1, "long") == pytest.approx(0.01)   # open[16]=100 -> close[16]=101
    assert outcomes.forward_return(df, 15, 2, "long") == pytest.approx(0.02)   # -> close[17]=102
    assert outcomes.forward_return(df, 15, 2, "short") == pytest.approx(-0.02)
    assert outcomes.forward_return(df, 15, 99, "long") is None                 # 数据不够


# ------------------------------------------------------------------ 跟踪器
class FakeMarket:
    def __init__(self, bars):
        self._bars = bars
        self.calls = 0

    async def get_ohlcv(self, symbol, timeframe, limit=300):
        self.calls += 1
        return self._bars


def paper_settings(**overrides):
    settings = {
        'signal_paper_enabled': True,
        'signal_paper_sl_atr': 1.0,
        'signal_paper_tp_r': 2.0,
        'signal_paper_max_bars': 3,
        'signal_forward_bars': [1, 2],
        'signal_auto_trade_value_usd': 100.0,
        'signal_auto_trade_directions': ['long', 'short'],
        'signal_auto_trade_strategies': ['ma_breakout'],
        'signal_auto_trade_timeframes': ['1h'],
        'signal_auto_trade_confirmations': 1,
        'signal_auto_trade_confirmation_window_seconds': 300,
        'signal_auto_trade_cooldown_seconds': 0,
        'signal_auto_trade_max_positions': 3,
    }
    settings.update(overrides)
    return settings


def make_signal(bar_index=15, direction='long', price=100.0, signal_id='sig1'):
    return {
        'id': signal_id, 'created_at': '2026-11-12T00:00:00+00:00',
        'symbol': 'BTC', 'full_symbol': 'BTC/USDT:USDT', 'timeframe': '1h',
        'strategy': 'ma_breakout', 'direction': direction, 'price': price,
        'volume_ratio': 1.0, 'ts': bar_index * HOUR_MS,
    }


def build_tracker(settings, bars):
    store = SignalStore()
    market = FakeMarket(bars)
    return OutcomeTracker(lambda: settings, market, store), store, market


def test_paper_disabled_records_nothing():
    rows = flat_rows(20)
    tracker, store, _ = build_tracker(paper_settings(signal_paper_enabled=False), make_bars(rows))
    signal = make_signal()
    store.add(signal)
    asyncio.run(tracker.on_signal(signal))
    assert tracker.snapshot()['open_positions'] == []
    asyncio.run(tracker.tick())
    assert tracker.snapshot()['paper_stats']['total'] == 0


def test_paper_open_then_stop_out():
    rows = flat_rows(20)
    rows[16] = (100.0, 100.5, 98.5, 99.0)
    tracker, store, market = build_tracker(paper_settings(), make_bars(rows))
    signal = make_signal()
    store.add(signal)

    asyncio.run(tracker.on_signal(signal))
    asyncio.run(tracker.tick())          # 建仓
    snapshot = tracker.snapshot()
    assert len(snapshot['open_positions']) == 1
    position = snapshot['open_positions'][0]
    assert position['stop_loss'] == pytest.approx(99.0, rel=1e-6)
    assert position['take_profit'] == pytest.approx(102.0, rel=1e-6)

    asyncio.run(tracker.tick())          # 结算
    stats = tracker.snapshot()['paper_stats']
    assert stats['total'] == 1
    assert stats['by_reason'] == {'stop': 1}
    assert stats['avg_pnl_pct'] == pytest.approx(-1.0, abs=0.05)


def test_forward_results_recorded_once():
    rows = flat_rows(20)
    rows[16] = (100.0, 101.0, 99.5, 101.0)
    rows[17] = (101.0, 102.0, 100.5, 102.0)
    tracker, store, market = build_tracker(paper_settings(signal_paper_enabled=False), make_bars(rows))
    signal = make_signal()
    store.add(signal)

    asyncio.run(tracker.tick())
    decorated = tracker.decorate([dict(signal)])
    assert decorated[0]['fwd'] == {'1': 1.0, '2': 2.0}

    calls = market.calls
    asyncio.run(tracker.tick())          # 已有结果，不再拉 K 线
    assert market.calls == calls


def test_forward_stats_group_by_strategy():
    rows = flat_rows(20)
    rows[16] = (100.0, 101.0, 99.5, 101.0)
    rows[17] = (101.0, 102.0, 100.5, 102.0)
    tracker, store, _ = build_tracker(paper_settings(signal_paper_enabled=False), make_bars(rows))
    store.add(make_signal(signal_id='a'))
    store.add(make_signal(signal_id='b', direction='short'))
    asyncio.run(tracker.tick())

    rows_out = tracker.snapshot()['forward_stats']
    assert len(rows_out) == 1
    assert rows_out[0]['samples'] == 2
    assert rows_out[0]['h1_samples'] == 2
    assert rows_out[0]['h1'] == pytest.approx(0.0)      # 多空相抵
    assert rows_out[0]['h1_win'] == pytest.approx(50.0)


def test_state_persisted_and_reloaded(tmp_path):
    rows = flat_rows(20)
    tracker, store, _ = build_tracker(paper_settings(), make_bars(rows))
    signal = make_signal()
    store.add(signal)
    asyncio.run(tracker.on_signal(signal))
    asyncio.run(tracker.tick())

    reloaded = OutcomeTracker(lambda: paper_settings(), FakeMarket(make_bars(rows)), SignalStore())
    assert len(reloaded.snapshot()['open_positions']) == 1


def test_no_duplicate_paper_position_per_symbol():
    """同币种已有纸面持仓时不再叠加（复用自动开仓的持仓约束）。"""
    rows = flat_rows(20)
    # 持有上限放大到窗口之外，避免测试中途超时平仓干扰断言
    tracker, store, _ = build_tracker(paper_settings(signal_paper_max_bars=50), make_bars(rows))
    first = make_signal(signal_id='a')
    store.add(first)
    asyncio.run(tracker.on_signal(first))
    asyncio.run(tracker.tick())
    assert len(tracker.snapshot()['open_positions']) == 1

    second = make_signal(signal_id='b', direction='short')
    store.add(second)
    asyncio.run(tracker.on_signal(second))
    asyncio.run(tracker.tick())
    assert len(tracker.snapshot()['open_positions']) == 1
