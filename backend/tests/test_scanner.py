"""SignalScanner 离线集成测试：
- 每轮每个 (symbol, timeframe) 只请求一次 K 线；
- 顶部行情每轮只请求一次 fetch_tickers；
- 策略产出结构化信号并入队；
- 静态币种解析 USDC 优先。
"""
from __future__ import annotations

import asyncio
import queue
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import database  # noqa: E402
from app.core.rest_guardian import RestGuardian  # noqa: E402
from app.signals.market_data import MarketDataService  # noqa: E402
from app.signals.scanner import SignalScanner, build_scan_config  # noqa: E402
from app.signals.signal_store import SignalStore  # noqa: E402


class FakeScanExchange:
    """扫描用的假交易所（只实现扫描会用到的只读接口）。"""

    def __init__(self):
        self.markets = {
            "BTC/USDC:USDC": {"symbol": "BTC/USDC:USDC"},
            "ETH/USDC:USDC": {"symbol": "ETH/USDC:USDC"},
            "BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT"},
        }
        self.tickers = {
            "BTC/USDC:USDC": {"quoteVolume": 9_000_000},
            "BTC/USDT:USDT": {"quoteVolume": 50_000_000},
            "ETH/USDC:USDC": {"quoteVolume": 8_000_000},
        }
        self.fetch_tickers_calls = 0
        self.fetch_ohlcv_calls = []

    async def fetch_tickers(self):
        self.fetch_tickers_calls += 1
        await asyncio.sleep(0.01)  # 模拟网络延迟，保证锁内挂起点可被并发测试捕捉
        return self.tickers

    async def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        self.fetch_ohlcv_calls.append((symbol, timeframe))
        # 前平后突破的形态 + 最后一根放量，触发 SMA 突破看涨信号
        # （signal_config.json 中 ma_breakout 开启了 volume_confirm；
        #   ma_periods 含 99，需要 >99 根 K 线，否则 dropna 后为空）
        closes = [100.0] * 128 + [99.0, 200.0]
        volumes = [1000.0] * 129 + [5000.0]
        return [[1_700_000_000_000 + i * 3_600_000, c, c, c, c, v]
                for i, (c, v) in enumerate(zip(closes, volumes))]


def _settings(**overrides):
    settings = {
        'signal_scan_enabled': True,
        'signal_scan_interval_seconds': 300,
        'signal_scan_static_symbols': ['BTC'],
        'signal_scan_top_n': 10,
        'signal_scan_timeframes': ['1h'],
        'signal_ticker_cache_seconds': 30,
        'signal_ohlcv_cache_seconds': 30,
        'signal_auto_trade_enabled': False,
        'signal_auto_trade_directions': ['long', 'short'],
        'signal_auto_trade_strategies': ['ma_breakout'],
        'signal_auto_trade_timeframes': ['1h'],
        'signal_auto_trade_confirmation_window_seconds': 300,
        'signal_auto_trade_confirmations': 1,
        'signal_auto_trade_cooldown_seconds': 900,
        'signal_auto_trade_max_positions': 5,
        'signal_auto_trade_value_usd': 100.0,
    }
    settings.update(overrides)
    return settings


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "USER_SETTINGS_FILE", tmp_path / "u.json")
    monkeypatch.setattr(database, "COIN_LISTS_FILE", tmp_path / "c.json")
    database.init_db()
    from app.signals import runtime
    runtime.alerted_states.clear()
    while True:
        try:
            runtime.signal_queue.get_nowait()
        except queue.Empty:
            break
    yield
    runtime.cached_top_symbols.clear()


def _make_scanner(exchange, settings):
    store = SignalStore()

    market_data = MarketDataService(
        _provider(exchange),
        guardian=RestGuardian({"api_min_interval_sec": 0, "api_max_retries": 1}),
    )

    async def exchange_provider():
        return exchange

    return SignalScanner(lambda: settings, store, market_data, exchange_provider)


def _provider(exchange):
    async def _get():
        return exchange
    return _get


def _drain_queue() -> list:
    from app.signals import runtime
    records = []
    while True:
        try:
            records.append(runtime.signal_queue.get_nowait())
        except queue.Empty:
            return records


def test_scan_once_requests_ohlcv_once_per_key_and_emits_signals():
    exchange = FakeScanExchange()
    scanner = _make_scanner(exchange, _settings())

    result = asyncio.run(scanner.scan_once())

    # BTC（静态，解析为 USDC 优先）+ ETH（TopN）共 2 个交易对，1h 一个周期
    assert result['scanned_symbols'] == 2
    assert sorted(exchange.fetch_ohlcv_calls) == [
        ("BTC/USDC:USDC", "1h"), ("ETH/USDC:USDC", "1h")]
    assert exchange.fetch_tickers_calls == 1  # 每轮只拉一次顶部行情

    records = _drain_queue()
    # signal_config.json 还启用了其他策略，可能产生额外信号；ma_breakout 必须两个币种都触发
    ma_records = {(r['full_symbol'], r['strategy']): r for r in records
                  if r['strategy'] == 'ma_breakout'}
    assert {("BTC/USDC:USDC", "ma_breakout"), ("ETH/USDC:USDC", "ma_breakout")} <= set(ma_records)
    for record in ma_records.values():
        assert record['direction'] == 'long'
        assert record['price'] == pytest.approx(200.0)

    # 扫描状态已更新
    status = scanner.status()
    assert status['last_scan_at'] is not None
    assert status['scanned_symbols'] == 2
    assert status['running'] is False


def test_scan_once_dedupes_static_and_topn_base():
    """静态 BTC 与 TopN BTC（USDC 代表）同 base 去重。"""
    exchange = FakeScanExchange()
    scanner = _make_scanner(exchange, _settings(signal_scan_static_symbols=['BTC']))

    result = asyncio.run(scanner.scan_once())
    # TopN 也包含 BTC（USDC 代表），去重后仍只有 BTC+ETH 两个
    assert result['scanned_symbols'] == 2
    symbols = {s for s, _ in exchange.fetch_ohlcv_calls}
    assert symbols == {"BTC/USDC:USDC", "ETH/USDC:USDC"}


def test_scan_once_concurrent_protection():
    exchange = FakeScanExchange()
    scanner = _make_scanner(exchange, _settings())

    async def run():
        first = asyncio.create_task(scanner.scan_once())
        await asyncio.sleep(0)
        second = await scanner.scan_once()
        await first
        return second

    second = asyncio.run(run())
    assert second.get('skipped') is True


def test_build_scan_config_merges_user_settings():
    config = build_scan_config(_settings(signal_scan_static_symbols=['SOL']))
    assert config['market_settings']['static_symbols'] == ['SOL']
    assert 'strategy_params' in config
    assert config['user_settings']['signal_scan_top_n'] == 10
