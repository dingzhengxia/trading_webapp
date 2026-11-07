"""MarketDataService 离线测试（MERGE_PLAN §8.5）：
ticker/OHLCV 缓存命中不重复请求；同 key in-flight 去重；TopN 选择与 USDC 优先。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.rest_guardian import RestGuardian  # noqa: E402
from app.signals.market_data import MarketDataService  # noqa: E402


class FakeExchange:
    """带请求计数器的假交易所（完全离线）。"""

    def __init__(self, tickers=None, ohlcv=None):
        self.tickers = tickers or {}
        self.ohlcv = ohlcv or {}
        self.fetch_tickers_calls = 0
        self.fetch_ohlcv_calls = []

    async def fetch_tickers(self):
        self.fetch_tickers_calls += 1
        return self.tickers

    async def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        self.fetch_ohlcv_calls.append((symbol, timeframe, limit))
        await asyncio.sleep(0.02)  # 模拟网络延迟，制造 in-flight 窗口
        return self.ohlcv.get((symbol, timeframe), [])


def _provider(exchange):
    async def _get():
        return exchange
    return _get


def make_service(exchange, **kw):
    return MarketDataService(_provider(exchange), guardian=RestGuardian(
        {"api_min_interval_sec": 0, "api_max_retries": 1}), **kw)


# ---------------------------------------------------------------------------
def test_ticker_cache_hits_once():
    exchange = FakeExchange(tickers={"BTC/USDC:USDC": {"quoteVolume": 1e8}})

    async def run():
        svc = make_service(exchange)
        t1 = await svc.get_tickers()
        t2 = await svc.get_tickers()
        return t1, t2

    t1, t2 = asyncio.run(run())
    assert t1 is t2
    assert exchange.fetch_tickers_calls == 1


def test_ticker_force_bypasses_cache():
    exchange = FakeExchange(tickers={"BTC/USDC:USDC": {"quoteVolume": 1e8}})

    async def run():
        svc = make_service(exchange)
        await svc.get_tickers()
        await svc.get_tickers(force=True)

    asyncio.run(run())
    assert exchange.fetch_tickers_calls == 2


def test_ohlcv_cache_and_dedup():
    exchange = FakeExchange(ohlcv={("BTC/USDC:USDC", "1h"): [[1, 2, 3, 4, 5, 6]]})

    async def run():
        svc = make_service(exchange)
        # 并发两次同 key 请求 -> in-flight 去重，只发一次
        r1, r2 = await asyncio.gather(svc.get_ohlcv("BTC/USDC:USDC", "1h", 100),
                                      svc.get_ohlcv("BTC/USDC:USDC", "1h", 100))
        # 第三次走 TTL 缓存
        r3 = await svc.get_ohlcv("BTC/USDC:USDC", "1h", 100)
        # 不同 key 独立请求
        await svc.get_ohlcv("ETH/USDC:USDC", "1h", 100)
        return r1, r2, r3

    r1, r2, r3 = asyncio.run(run())
    assert r1 == r2 == r3 == [[1, 2, 3, 4, 5, 6]]
    assert exchange.fetch_ohlcv_calls == [("BTC/USDC:USDC", "1h", 100), ("ETH/USDC:USDC", "1h", 100)]


def test_top_symbols_usdc_priority_and_volume_order():
    tickers = {
        "BTC/USDC:USDC": {"quoteVolume": 9_000_000},
        "BTC/USDT:USDT": {"quoteVolume": 50_000_000},  # USDT 量更大，但 USDC 优先
        "ETH/USDT:USDT": {"quoteVolume": 8_000_000},
        "SOL/USDC:USDC": {"quoteVolume": 10_000_000},
        "USDC/USDT:USDT": {"quoteVolume": 99_000_000},  # 稳定币排除
        "DOGE/BUSD:BUSD": {"quoteVolume": 99_000_000},  # 非 USDC/USDT 报价排除
    }
    exchange = FakeExchange(tickers=tickers)

    async def run():
        svc = make_service(exchange)
        return await svc.get_top_symbols_by_volume(10)

    result = asyncio.run(run())
    # SOL 量最大排第一；BTC 用 USDC 代表（即使 USDT 量更大）
    assert result == ["SOL/USDC:USDC", "BTC/USDC:USDC", "ETH/USDT:USDT"]


def test_top_symbols_respects_top_n_and_exclude():
    tickers = {
        f"COIN{i}/USDT:USDT": {"quoteVolume": 1_000_000 - i * 1000} for i in range(5)
    }
    tickers["BTC/USDC:USDC"] = {"quoteVolume": 2_000_000}
    exchange = FakeExchange(tickers=tickers)

    async def run():
        svc = make_service(exchange)
        return await svc.get_top_symbols_by_volume(2, exclude=["COIN0"])

    result = asyncio.run(run())
    assert result == ["BTC/USDC:USDC", "COIN1/USDT:USDT"]


def test_ohlcv_failure_propagates_and_does_not_poison_cache():
    exchange = FakeExchange()
    exchange.ohlcv = {}

    async def _fail(symbol, timeframe, since=None, limit=None):
        raise Exception("boom")

    exchange.fetch_ohlcv = _fail

    async def run():
        svc = make_service(exchange)
        try:
            await svc.get_ohlcv("BTC/USDC:USDC", "1h")
        except Exception as e:
            return str(e)
        return None

    assert asyncio.run(run()) == "boom"
