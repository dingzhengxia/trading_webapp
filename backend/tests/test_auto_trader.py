"""SignalAutoTrader 全过滤链离线测试（MERGE_PLAN §8.6）：
开关/方向(neutral 永不开仓)/策略白名单/时间框架/确认数/冷却/最大持仓/已有持仓。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import database  # noqa: E402
from app.signals.auto_trader import SignalAutoTrader  # noqa: E402


def base_settings(**overrides):
    settings = {
        'signal_auto_trade_enabled': True,
        'signal_auto_trade_directions': ['long', 'short'],
        'signal_auto_trade_strategies': [
            'ema_cross', 'ma_breakout', 'kdj_cross', 'level_breakout',
            'rsi_divergence', 'trend_channel_breakout', 'ob_luxalgo', 'ob_fluxcharts'],
        'signal_auto_trade_timeframes': ['1h', '4h'],
        'signal_auto_trade_confirmation_window_seconds': 300,
        'signal_auto_trade_confirmations': 1,
        'signal_auto_trade_cooldown_seconds': 900,
        'signal_auto_trade_max_positions': 5,
        'signal_auto_trade_value_usd': 100.0,
    }
    settings.update(overrides)
    return settings


class FakePosition:
    def __init__(self, symbol, side="long"):
        self.symbol = symbol
        self.side = side
        self.full_symbol = f"{symbol}/USDC:USDC"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "USER_SETTINGS_FILE", tmp_path / "u.json")
    monkeypatch.setattr(database, "COIN_LISTS_FILE", tmp_path / "c.json")
    database.init_db()


def _signal(symbol="BTC", direction="long", strategy="ema_cross", timeframe="1h"):
    return {"symbol": symbol, "full_symbol": f"{symbol}/USDC:USDC", "timeframe": timeframe,
            "strategy": strategy, "strategy_index": 0, "direction": direction,
            "price": 12345.6, "title": "t", "message": "m", "dedupe_key": "k"}


def _make_trader(settings, positions=None, opened=None):
    opened = opened if opened is not None else []

    async def open_callback(signal):
        opened.append(signal)
        return True

    async def position_provider():
        return list(positions or [])

    trader = SignalAutoTrader(lambda: settings, position_provider, open_callback)
    return trader, opened


def test_disabled_skips():
    trader, opened = _make_trader(base_settings(signal_auto_trade_enabled=False))
    result = asyncio.run(trader.on_signal(_signal()))
    assert result == {'action': 'skip', 'reason': '自动开仓未启用'}
    assert opened == []


def test_never_open_neutral():
    trader, opened = _make_trader(base_settings())
    result = asyncio.run(trader.on_signal(_signal(direction="neutral")))
    assert result['action'] == 'skip'
    assert 'neutral' in result['reason']
    assert opened == []


def test_direction_whitelist():
    trader, opened = _make_trader(base_settings(signal_auto_trade_directions=['long']))
    result = asyncio.run(trader.on_signal(_signal(direction="short")))
    assert result['action'] == 'skip'
    assert opened == []


def test_strategy_whitelist():
    trader, opened = _make_trader(base_settings())
    result = asyncio.run(trader.on_signal(_signal(strategy="volatility_breakout")))
    assert result['action'] == 'skip'
    assert result['action'] == 'skip' and opened == []
    # neutral 类策略（consecutive_candles）默认不在白名单
    result2 = asyncio.run(trader.on_signal(_signal(strategy="consecutive_candles")))
    assert result2['action'] == 'skip'


def test_timeframe_whitelist():
    trader, opened = _make_trader(base_settings(signal_auto_trade_timeframes=['4h']))
    result = asyncio.run(trader.on_signal(_signal(timeframe="1h")))
    assert result['action'] == 'skip'
    assert opened == []


def test_confirmations_require_distinct_families():
    """确认数按「信号族」计：同族的多个策略只算 1 票。"""
    trader, opened = _make_trader(base_settings(signal_auto_trade_confirmations=2))
    # 同族（trend）：ema_cross / ma_breakout / trend_channel_breakout 都只算 1 票
    r1 = asyncio.run(trader.on_signal(_signal(strategy="ema_cross")))
    assert r1['action'] == 'skip'
    r2 = asyncio.run(trader.on_signal(_signal(strategy="ma_breakout")))
    assert r2['action'] == 'skip' and '确认族数不足' in r2['reason']
    r3 = asyncio.run(trader.on_signal(_signal(strategy="trend_channel_breakout")))
    assert r3['action'] == 'skip'
    # 不同族（level）-> 2 族共振 -> 开仓
    r4 = asyncio.run(trader.on_signal(_signal(strategy="level_breakout")))
    assert r4['action'] == 'open'
    assert len(opened) == 1


def test_confirmation_counts_only_whitelisted_signals():
    """不在策略白名单的信号不参与确认计票。"""
    settings = base_settings(signal_auto_trade_confirmations=2,
                             signal_auto_trade_strategies=['ema_cross', 'level_breakout'])
    trader, opened = _make_trader(settings)
    # volatility_breakout 不在白名单，即使属于独立族也不计票
    assert asyncio.run(trader.on_signal(
        _signal(strategy="volatility_breakout")))['action'] == 'skip'
    assert asyncio.run(trader.on_signal(_signal(strategy="ema_cross")))['action'] == 'skip'
    assert asyncio.run(trader.on_signal(
        _signal(strategy="level_breakout")))['action'] == 'open'
    assert len(opened) == 1


def test_cooldown_blocks_same_symbol():
    trader, opened = _make_trader(base_settings())
    assert asyncio.run(trader.on_signal(_signal()))['action'] == 'open'
    r2 = asyncio.run(trader.on_signal(_signal(strategy="ma_breakout", direction="long")))
    assert r2['action'] == 'skip'
    assert '冷却' in r2['reason']
    assert len(opened) == 1


def test_cooldown_is_per_symbol():
    trader, opened = _make_trader(base_settings())
    assert asyncio.run(trader.on_signal(_signal(symbol="BTC")))['action'] == 'open'
    r2 = asyncio.run(trader.on_signal(_signal(symbol="ETH", strategy="ma_breakout")))
    assert r2['action'] == 'open'
    assert len(opened) == 2


def test_max_positions():
    positions = [FakePosition(f"C{i}") for i in range(5)]
    trader, opened = _make_trader(base_settings(), positions=positions)
    result = asyncio.run(trader.on_signal(_signal()))
    assert result['action'] == 'skip'
    assert '上限' in result['reason']
    assert opened == []


def test_existing_position_skips():
    positions = [FakePosition("SOL", side="short")]
    trader, opened = _make_trader(base_settings(), positions=positions)
    result = asyncio.run(trader.on_signal(_signal(symbol="SOL")))
    assert result['action'] == 'skip'
    assert '已有持仓' in result['reason']
    assert opened == []


def test_open_callback_error_returns_error_action():
    async def fail_callback(signal):
        raise Exception("exchange down")

    async def position_provider():
        return []

    trader = SignalAutoTrader(lambda: base_settings(), position_provider, fail_callback)
    result = asyncio.run(trader.on_signal(_signal()))
    assert result['action'] == 'error'
    assert 'exchange down' in result['reason']


def test_full_chain_pass_opens():
    trader, opened = _make_trader(base_settings(), positions=[FakePosition("DOGE")])
    result = asyncio.run(trader.on_signal(_signal(symbol="BTC", direction="long",
                                                  strategy="ema_cross", timeframe="1h")))
    assert result['action'] == 'open'
    assert len(opened) == 1
    assert opened[0]['symbol'] == 'BTC'
