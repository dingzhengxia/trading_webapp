# tests/test_trend_filter.py
"""日线趋势过滤：TrendFilter 判定 + auto_trader 过滤链 2.5 行为。

趋势判定复用 analysis/trend.get_current_trend（三线 EMA 严格排列，
trend_ema_long = 26/50/120），这里用持续单调涨/跌的合成 K 线驱动三线收敛。
"""
import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import database  # noqa: E402
from app.signals.auto_trader import SignalAutoTrader  # noqa: E402
from app.signals.trend_filter import TrendFilter, make_trend_provider  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """过滤链会写冷却状态（signal_state 表），必须隔离到临时 DB。"""
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "USER_SETTINGS_FILE", tmp_path / "u.json")
    monkeypatch.setattr(database, "COIN_LISTS_FILE", tmp_path / "c.json")
    database.init_db()


class _FakeMarketData:
    """get_ohlcv 打桩：可注入返回值 / 异常，并统计调用次数。"""

    def __init__(self, rows=None, error=None):
        self.rows = rows
        self.error = error
        self.calls = 0

    async def get_ohlcv(self, symbol, timeframe, limit=200):
        self.calls += 1
        if self.error:
            raise self.error
        return self.rows


def _closes(rising: bool, n=200):
    base = 100.0
    out = []
    for i in range(n):
        # 单调涨/跌 + 微小抖动，保证三线 EMA 严格同向排列
        step = 0.5 if rising else -0.5
        base += step + (0.01 if (i % 2) else -0.01)
        out.append(base)
    return out


def _ohlcv(closes):
    return [[i * 86400000, c, c, c, c, 1000.0] for i, c in enumerate(closes)]


# 生产的 trend_ema_long 组（signal_config.json）：三线 26/50/120
_TREND_PARAMS = {'fast': 26, 'medium': 50, 'long': 120}


def _settings(**over):
    settings = {
        'signal_auto_trade_enabled': True,
        'signal_auto_trade_directions': ['long', 'short'],
        'signal_auto_trade_strategies': ['ema_cross'],
        'signal_auto_trade_timeframes': ['4h'],
        'signal_auto_trade_confirmations': 1,
        'signal_auto_trade_trend_filter_enabled': True,
    }
    settings.update(over)
    return settings


async def _positions():
    return []


# ---------------------------------------------------------------- TrendFilter
def test_rising_market_is_long():
    md = _FakeMarketData(rows=_ohlcv(_closes(rising=True)))
    tf = TrendFilter(md, strategy_config=lambda: {'strategy_params': {'trend_ema_long': _TREND_PARAMS}})
    assert asyncio.run(tf.trend_of('BTC/USDC:USDC')) == 'long'


def test_falling_market_is_short():
    md = _FakeMarketData(rows=_ohlcv(_closes(rising=False)))
    tf = TrendFilter(md, strategy_config=lambda: {'strategy_params': {'trend_ema_long': _TREND_PARAMS}})
    assert asyncio.run(tf.trend_of('BTC/USDC:USDC')) == 'short'


def test_insufficient_data_is_neutral():
    md = _FakeMarketData(rows=_ohlcv(_closes(rising=True, n=30)))
    tf = TrendFilter(md, strategy_config=lambda: {'strategy_params': {'trend_ema_long': _TREND_PARAMS}})
    assert asyncio.run(tf.trend_of('BTC/USDC:USDC')) == 'neutral'


def test_market_error_is_neutral():
    md = _FakeMarketData(error=RuntimeError('net down'))
    tf = TrendFilter(md, strategy_config=lambda: {'strategy_params': {'trend_ema_long': _TREND_PARAMS}})
    assert asyncio.run(tf.trend_of('BTC/USDC:USDC')) == 'neutral'


def test_result_is_cached():
    md = _FakeMarketData(rows=_ohlcv(_closes(rising=True)))
    tf = TrendFilter(md, strategy_config=lambda: {'strategy_params': {'trend_ema_long': _TREND_PARAMS}})
    first = asyncio.run(tf.trend_of('BTC/USDC:USDC'))
    second = asyncio.run(tf.trend_of('BTC/USDC:USDC'))
    assert first == second == 'long'
    assert md.calls == 1  # 第二次走缓存，不再发请求


def test_neutral_not_cached():
    md = _FakeMarketData(error=RuntimeError('flaky'))
    tf = TrendFilter(md, strategy_config=lambda: {'strategy_params': {'trend_ema_long': _TREND_PARAMS}})
    asyncio.run(tf.trend_of('BTC/USDC:USDC'))
    asyncio.run(tf.trend_of('BTC/USDC:USDC'))
    assert md.calls == 2  # neutral 不缓存，故障恢复后下轮重试


def test_neutral_cached_when_configured():
    """展示链路（10s 轮询）给 neutral 配了短 TTL：震荡币不该每轮重拉日线。"""
    md = _FakeMarketData(rows=_ohlcv(_closes(rising=True, n=30)))  # 数据不足 -> neutral
    tf = TrendFilter(md, strategy_config=lambda: {'strategy_params': {'trend_ema_long': _TREND_PARAMS}},
                     neutral_cache_seconds=60)
    assert asyncio.run(tf.trend_of('BTC/USDC:USDC')) == 'neutral'
    assert asyncio.run(tf.trend_of('BTC/USDC:USDC')) == 'neutral'
    assert md.calls == 1


# ------------------------------------------------------------ 过滤链 2.5
def _make_trader(trend_value, settings_over=None):
    async def provider(signal):
        return trend_value

    return SignalAutoTrader(
        settings_loader=lambda: _settings(**(settings_over or {})),
        position_provider=_positions,
        open_callback=lambda signal: asyncio.sleep(0, result=True),
        trend_provider=provider,
    )


def _signal(direction, symbol='ETH'):
    return {'symbol': symbol, 'full_symbol': f'{symbol}/USDC:USDC', 'direction': direction,
            'strategy': 'ema_cross', 'timeframe': '4h'}


def test_long_signal_blocked_in_downtrend():
    trader = _make_trader('short')
    result = asyncio.run(trader.on_signal(_signal('long')))
    assert result['action'] == 'skip'
    assert '日线趋势' in result['reason']


def test_short_signal_passes_in_downtrend():
    trader = _make_trader('short')
    result = asyncio.run(trader.on_signal(_signal('short')))
    assert result['action'] == 'open'


def test_neutral_trend_passes_both():
    # 不同 symbol：过滤链对同 symbol 有冷却，连续开仓会被拦截
    trader = _make_trader('neutral')
    assert asyncio.run(trader.on_signal(_signal('long')))['action'] == 'open'
    trader = _make_trader('neutral')
    assert asyncio.run(trader.on_signal(_signal('short', 'SOL')))['action'] == 'open'


def test_provider_exception_passes():
    """趋势查询异常绝不阻塞开仓链（降级放行）。"""
    async def broken(signal):
        raise RuntimeError('boom')

    trader = SignalAutoTrader(
        settings_loader=lambda: _settings(),
        position_provider=_positions,
        open_callback=lambda signal: asyncio.sleep(0, result=True),
        trend_provider=broken,
    )
    result = asyncio.run(trader.on_signal(_signal('long')))
    assert result['action'] == 'open', result


def test_filter_disabled_passes():
    """开关关闭时 make_trend_provider 恒返回 neutral（放行），趋势判定短路。"""
    class _MD(_FakeMarketData):
        async def get_ohlcv(self, symbol, timeframe, limit=200):
            return _ohlcv(_closes(rising=False))  # 市场是空头趋势

    tf = TrendFilter(_MD(), strategy_config=lambda: {'strategy_params': {'trend_ema_long': _TREND_PARAMS}})
    provider = make_trend_provider(
        get_filter=lambda: tf,
        settings_loader=lambda: _settings(signal_auto_trade_trend_filter_enabled=False),
        symbol_of=lambda s: s.get('full_symbol'),
    )
    trader = SignalAutoTrader(
        settings_loader=lambda: _settings(),
        position_provider=_positions,
        open_callback=lambda signal: asyncio.sleep(0, result=True),
        trend_provider=provider,
    )
    result = asyncio.run(trader.on_signal(_signal('long')))
    assert result['action'] == 'open', result


def test_no_provider_passes():
    """未装配 trend_provider（旧调用方）行为不变。"""
    trader = SignalAutoTrader(
        settings_loader=lambda: _settings(),
        position_provider=_positions,
        open_callback=lambda signal: asyncio.sleep(0, result=True),
    )
    result = asyncio.run(trader.on_signal(_signal('long')))
    assert result['action'] == 'open'


# ---------------------------------------------------------------- provider 装配
def test_make_trend_provider_symbol_and_switch():
    calls = []

    class _MD(_FakeMarketData):
        async def get_ohlcv(self, symbol, timeframe, limit=200):
            calls.append(symbol)
            return _ohlcv(_closes(rising=True))

    tf = TrendFilter(_MD(), strategy_config=lambda: {'strategy_params': {'trend_ema_long': _TREND_PARAMS}})
    provider = make_trend_provider(
        get_filter=lambda: tf,
        settings_loader=lambda: {'signal_auto_trade_trend_filter_enabled': True},
        symbol_of=lambda s: str(s.get('full_symbol') or s.get('symbol') or ''),
    )
    # full_symbol 优先于 base symbol
    trend = asyncio.run(provider({'symbol': 'ETH', 'full_symbol': 'ETH/USDC:USDC'}))
    assert trend == 'long' and calls == ['ETH/USDC:USDC']
    # 开关关闭 → neutral 放行
    provider_off = make_trend_provider(
        get_filter=lambda: tf,
        settings_loader=lambda: {'signal_auto_trade_trend_filter_enabled': False},
        symbol_of=lambda s: s.get('full_symbol'),
    )
    assert asyncio.run(provider_off({'full_symbol': 'ETH/USDC:USDC'})) == 'neutral'
