"""实盘出场层测试：ATR 口径上实盘挂单 + 超时平仓执行器。

覆盖：
- `exit_rules.timeframe_ms / bars_held`：根数换算；
- `MarketDataService.atr_at`：正常取值、数据不足返回 None；
- 实盘挂单在 `signal_exit_mode=atr` 时用 ATR 算止损止盈（不再固定 percent）；
- **ATR 拿不到时必须回退 percent**（否则等于裸奔不挂止损）；
- `LiveExitExecutor`：未到期不动、到期平仓并清登记、仓位已消失则清登记、
  开关关闭时只对账不平仓。
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
from app.logic import sl_tp_logic_async  # noqa: E402
from app.signals import exit_executor as ee  # noqa: E402
from app.signals.market_data import MarketDataService  # noqa: E402

BASE = {
    'leverage': 20,
    'enable_long_sl_tp': True,
    'long_stop_loss_percentage': 50.0,
    'long_take_profit_percentage': 100.0,
    'enable_long_trailing_stop': False,
    'enable_short_sl_tp': True,
    'short_stop_loss_percentage': 80.0,
    'short_take_profit_percentage': 150.0,
    'enable_short_trailing_stop': False,
    'signal_exit_mode': 'percent',
    'signal_paper_sl_atr': 2.0,
    'signal_paper_tp_r': 2.0,
    'signal_live_exit_timeframe': '4h',
}


def _run(coro):
    return asyncio.run(coro)


def _stops(calls):
    return [float(c['params']['stopPrice']) for c in calls if str(c.get('type', '')).upper() == 'STOP_MARKET']


# ---------------------------------------------------------------- timeframe 工具
def test_timeframe_ms_and_bars_held():
    assert exit_rules.timeframe_ms('4h') == 14_400_000
    assert exit_rules.timeframe_ms('bogus') is None
    assert exit_rules.bars_held(None, '4h') is None
    # 手 0 根：刚开仓
    assert exit_rules.bars_held(1_000_000, '4h', now_ms=1_000_000) == 0
    # 满 6 根 4h = 24 小时
    assert exit_rules.bars_held(0, '4h', now_ms=6 * 14_400_000) == 6


# ---------------------------------------------------------------- ATR 取数
def test_atr_at_returns_value_and_none():
    service = MarketDataService(lambda: None)
    rows = [[i * 3_600_000, 100 + i, 101 + i, 99 + i, 100 + i, 1.0] for i in range(40)]

    async def fake_ohlcv(symbol, timeframe, limit=400):
        return rows

    service.get_ohlcv = fake_ohlcv  # type: ignore[assignment]
    atr = _run(service.atr_at('BTC/USDT:USDT', '1h'))
    assert atr and atr > 0

    async def too_short(symbol, timeframe, limit=400):
        return rows[:5]

    service.get_ohlcv = too_short  # type: ignore[assignment]
    assert _run(service.atr_at('BTC/USDT:USDT', '1h')) is None


# ---------------------------------------------------------------- 实盘挂单口径
def test_resolve_atr_follows_signal_timeframe(monkeypatch, async_logger):
    """ATR 周期跟随信号自身周期；缺失或非法时才退回全局 signal_live_exit_timeframe。"""
    used = []

    class FakeMarket:
        async def atr_at(self, symbol, timeframe):
            used.append(timeframe)
            return 1.0

    import app.signals.market_data as market_data
    monkeypatch.setattr(market_data, 'shared_market_data', lambda: FakeMarket())

    async def run():
        await sl_tp_logic_async._resolve_atr(
            'BTC/USDT:USDT',
            {'_signal_timeframe': '1h', 'signal_live_exit_timeframe': '4h'}, async_logger)
        await sl_tp_logic_async._resolve_atr(
            'BTC/USDT:USDT', {'signal_live_exit_timeframe': '4h'}, async_logger)
        await sl_tp_logic_async._resolve_atr(
            'BTC/USDT:USDT',
            {'_signal_timeframe': 'bogus', 'signal_live_exit_timeframe': '4h'}, async_logger)

    _run(run())
    assert used == ['1h', '4h', '4h']


def test_live_stop_uses_atr_when_mode_atr(
    fake_exchange, async_logger, stop_event, position_factory, fast_sleep, monkeypatch,
):
    async def fake_atr(full_symbol, config, logger):
        return 2.0

    monkeypatch.setattr(sl_tp_logic_async, '_resolve_atr', fake_atr)
    position = position_factory('BTC', 'BTC/USDC:USDC', 'long', contracts=1.0, entry_price=100.0)
    config = dict(BASE, signal_exit_mode='atr')

    _run(sl_tp_logic_async.set_tp_sl_for_position_async(
        fake_exchange, position, config, async_logger, stop_event))

    # 止损 = entry - 2.0(ATR) * 2.0(sl_atr) = 96；止盈 = entry + 2R = 108
    assert _stops(fake_exchange.create_order_calls) == [pytest.approx(96.0)]


def test_live_stop_falls_back_to_percent_without_atr(
    fake_exchange, async_logger, stop_event, position_factory, fast_sleep, monkeypatch,
):
    async def no_atr(full_symbol, config, logger):
        return None

    monkeypatch.setattr(sl_tp_logic_async, '_resolve_atr', no_atr)
    position = position_factory('BTC', 'BTC/USDC:USDC', 'long', contracts=1.0, entry_price=100.0)
    config = dict(BASE, signal_exit_mode='atr')

    _run(sl_tp_logic_async.set_tp_sl_for_position_async(
        fake_exchange, position, config, async_logger, stop_event))

    # 回退 percent：50%/20 倍杠杆 = 2.5% -> 97.5
    assert _stops(fake_exchange.create_order_calls) == [pytest.approx(97.5)]
    assert any('回退百分比' in msg for _, msg in async_logger.calls)


def test_live_stop_percent_mode_unchanged(
    fake_exchange, async_logger, stop_event, position_factory, fast_sleep,
):
    position = position_factory('BTC', 'BTC/USDC:USDC', 'long', contracts=1.0, entry_price=100.0)
    _run(sl_tp_logic_async.set_tp_sl_for_position_async(
        fake_exchange, position, dict(BASE), async_logger, stop_event))
    assert _stops(fake_exchange.create_order_calls) == [pytest.approx(97.5)]


# ---------------------------------------------------------------- 超时平仓执行器
@pytest.fixture
def executor_env(monkeypatch):
    """隔离的登记表 + 可控时钟 + 假的平仓回调。"""
    state = {'positions': {}}
    monkeypatch.setattr(ee.database, 'get_value', lambda table, key, default=None: state.get(key, default))
    monkeypatch.setattr(ee.database, 'set_value', lambda table, key, value: state.__setitem__(key, value))

    now = {'ms': 0}
    monkeypatch.setattr(ee, '_timestamp_ms', lambda: now['ms'])

    positions = {'list': []}
    closed = []
    settings = {'signal_live_exit_timeout_enabled': True, 'signal_paper_max_bars': 6}

    async def provider():
        return positions['list']

    async def close(full_symbol):
        closed.append(full_symbol)
        return True

    ex = ee.LiveExitExecutor(lambda: settings, provider, close)
    return ex, positions, closed, settings, now


def test_registers_and_keeps_before_deadline(executor_env):
    ex, positions, closed, settings, now = executor_env
    ex.register({'symbol': 'BTC', 'full_symbol': 'BTC/USDT:USDT', 'direction': 'long', 'timeframe': '4h'})
    positions['list'] = [type('P', (), {'symbol': 'BTC', 'full_symbol': 'BTC/USDT:USDT'})()]
    now['ms'] = 5 * 14_400_000  # 持有 5 根，未满 6

    stats = _run(ex.tick())
    assert stats == {'closed': 0, 'dropped': 0, 'kept': 1}
    assert closed == []


def test_closes_and_unregisters_at_deadline(executor_env):
    ex, positions, closed, settings, now = executor_env
    ex.register({'symbol': 'BTC', 'full_symbol': 'BTC/USDT:USDT', 'direction': 'long', 'timeframe': '4h'})
    positions['list'] = [type('P', (), {'symbol': 'BTC', 'full_symbol': 'BTC/USDT:USDT'})()]
    now['ms'] = 6 * 14_400_000

    stats = _run(ex.tick())
    assert stats['closed'] == 1
    assert closed == ['BTC/USDT:USDT']
    assert ex.snapshot()['positions'] == []


def test_drops_register_when_position_gone(executor_env):
    ex, positions, closed, settings, now = executor_env
    ex.register({'symbol': 'BTC', 'full_symbol': 'BTC/USDT:USDT', 'direction': 'long', 'timeframe': '4h'})
    positions['list'] = []
    now['ms'] = 99 * 14_400_000

    stats = _run(ex.tick())
    assert stats == {'closed': 0, 'dropped': 1, 'kept': 0}
    assert closed == []


def test_disabled_only_reconciles(executor_env):
    ex, positions, closed, settings, now = executor_env
    settings['signal_live_exit_timeout_enabled'] = False
    ex.register({'symbol': 'BTC', 'full_symbol': 'BTC/USDT:USDT', 'direction': 'long', 'timeframe': '4h'})
    positions['list'] = [type('P', (), {'symbol': 'BTC', 'full_symbol': 'BTC/USDT:USDT'})()]
    now['ms'] = 99 * 14_400_000

    stats = _run(ex.tick())
    assert stats == {'closed': 0, 'dropped': 0, 'kept': 1}
    assert closed == []


def test_close_failure_keeps_register(monkeypatch, executor_env):
    ex, positions, closed, settings, now = executor_env
    monkeypatch.setattr(ex, '_close_callback', lambda full: asyncio.sleep(0, result=False))
    ex.register({'symbol': 'BTC', 'full_symbol': 'BTC/USDT:USDT', 'direction': 'long', 'timeframe': '4h'})
    positions['list'] = [type('P', (), {'symbol': 'BTC', 'full_symbol': 'BTC/USDT:USDT'})()]
    now['ms'] = 6 * 14_400_000

    stats = _run(ex.tick())
    assert stats['closed'] == 0 and stats['kept'] == 1
    assert len(ex.snapshot()['positions']) == 1
