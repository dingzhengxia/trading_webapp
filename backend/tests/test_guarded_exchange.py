"""GuardedExchange 代理层离线测试（R-P1-1）。

验收要点（ARCH_REFACTOR_PHASE3 §7 T04）：
- 优先级映射（HIGH/NORMAL/LOW）按方法名生效；
- 未登记属性/方法原样透传；setattr 委托到 underlying；
- HIGH 绕熔断但仍受并发/最小间隔约束；
- get_shared_exchange 返回代理实例且 create_order 经共享 guardian 计数。
"""
from __future__ import annotations

import asyncio

import pytest

from app.core.guarded_exchange import GuardedExchange, REST_PRIORITY, raw_rest_method
from app.core.rest_guardian import (
    CircuitBreakerException,
    RestGuardian,
    reset_shared_guardian,
    shared_guardian,
)


class CountingGuardian(RestGuardian):
    def __init__(self, conf=None):
        super().__init__(conf)
        self.calls: list[tuple] = []

    async def call(self, func, *args, priority="NORMAL", conf=None, **kwargs):
        self.calls.append((getattr(func, "__name__", str(func)), priority))
        return await super().call(func, *args, priority=priority, conf=conf, **kwargs)


class MiniExchange:
    def __init__(self):
        self.custom_field = "raw"
        self.create_order_calls = 0

    async def create_order(self, *args, **kwargs):
        self.create_order_calls += 1
        return {"id": "x"}

    async def fetch_ohlcv(self, *args, **kwargs):
        return []

    async def fetch_order_book(self, *args, **kwargs):
        return {"bids": [[1, 1]], "asks": [[1, 1]]}

    def amount_to_precision(self, symbol, amount):
        return str(amount)

    async def close(self):
        self.closed = True


def test_priority_mapping():
    assert REST_PRIORITY['create_order'] == 'HIGH'
    assert REST_PRIORITY['cancel_order'] == 'HIGH'
    assert REST_PRIORITY['fetch_positions'] == 'HIGH'
    assert REST_PRIORITY['fetch_balance'] == 'HIGH'
    assert REST_PRIORITY['fetch_tickers'] == 'NORMAL'
    assert REST_PRIORITY['fetch_order_book'] == 'NORMAL'
    assert REST_PRIORITY['fetch_ohlcv'] == 'LOW'


def test_getattr_wraps_rest_methods_and_passes_through_others():
    exchange = MiniExchange()
    guardian = CountingGuardian({"api_min_interval_sec": 0, "api_max_retries": 1})
    proxy = GuardedExchange(exchange, guardian)

    # REST 方法：经 guardian 包装，priority 按方法名映射
    asyncio.run(proxy.create_order("BTC/USDC:USDC", "limit", "buy", 1, 100))
    assert exchange.create_order_calls == 1
    assert ("create_order", "HIGH") in guardian.calls

    asyncio.run(proxy.fetch_ohlcv("BTC/USDC:USDC", "1h"))
    assert ("fetch_ohlcv", "LOW") in guardian.calls

    # 非登记属性/方法：原样透传（不经过 guardian）
    assert proxy.custom_field == "raw"
    assert proxy.amount_to_precision("BTC/USDC:USDC", 1.5) == "1.5"
    assert [name for name, _p in guardian.calls] == ["create_order", "fetch_ohlcv"]


def test_setattr_delegates_to_underlying():
    exchange = MiniExchange()
    proxy = GuardedExchange(exchange, RestGuardian())
    proxy._twa_hedge_mode = True  # 缓存必须落在真实实例上（R-P0-3）
    assert exchange._twa_hedge_mode is True
    proxy.custom_field = "mutated"
    assert exchange.custom_field == "mutated"


def test_high_bypasses_circuit_but_still_throttled():
    """HIGH 绕过熔断（Q6），但仍受并发 + 最小间隔约束（真实计时，不用 fast_sleep）。"""
    guardian = RestGuardian({
        "api_min_interval_sec": 0.05, "api_max_concurrency": 1, "api_max_retries": 1,
    })
    exchange = MiniExchange()
    proxy = GuardedExchange(exchange, guardian)

    # 强制熔断开启
    guardian.circuit_open_until = float("inf")

    async def run():
        # NORMAL 调用被熔断拦截
        with pytest.raises(CircuitBreakerException):
            normal_exchange = MiniExchange()
            await GuardedExchange(normal_exchange, guardian).fetch_order_book("X")
        # HIGH 调用绕过熔断，可以继续下单
        await asyncio.gather(*(proxy.create_order("X", "limit", "buy", 1, 1) for _ in range(4)))

    asyncio.run(run())
    assert exchange.create_order_calls == 4

    # 间隔约束：HIGH 请求的开始时刻彼此间隔 >= min_interval（串行节流共享同一把锁）
    starts: list[float] = []

    class TimedExchange(MiniExchange):
        async def create_order(self, *args, **kwargs):
            import time as _time
            starts.append(_time.monotonic())
            return {"id": "x"}

    guardian2 = RestGuardian({"api_min_interval_sec": 0.02, "api_max_retries": 1})
    guardian2.circuit_open_until = float("inf")
    timed_proxy = GuardedExchange(TimedExchange(), guardian2)

    async def _fire_timed():
        await asyncio.gather(*(timed_proxy.create_order("X", "limit", "buy", 1, 1)
                               for _ in range(3)))

    asyncio.run(_fire_timed())
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert all(gap >= 0.01 for gap in gaps), f"HIGH 仍必须受最小间隔约束: {gaps}"


def test_raw_rest_method_unwraps_proxy():
    exchange = MiniExchange()
    proxy = GuardedExchange(exchange, RestGuardian())
    assert raw_rest_method(proxy, 'create_order').__name__ == 'create_order'
    assert getattr(raw_rest_method(proxy, 'create_order'), "__self__", None) is exchange
    assert raw_rest_method(exchange, 'create_order') == exchange.create_order


def test_shared_guardian_singleton_and_shared_counting():
    reset_shared_guardian()
    guardian = shared_guardian()
    assert shared_guardian() is guardian
    before = guardian.request_count
    exchange = MiniExchange()
    proxy = GuardedExchange(exchange, shared_guardian())
    asyncio.run(proxy.create_order("X", "limit", "buy", 1, 1))
    assert shared_guardian().request_count == before + 1, (
        "get_shared_exchange 返回的代理实例必须把调用计入共享 guardian（HIGH 生效断言）"
    )
    reset_shared_guardian()
