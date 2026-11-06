"""RestGuardian 离线测试（MERGE_PLAN §8.4）：
并发上限、最小间隔、429 指数退避、熔断、HIGH 绕过熔断。
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.rest_guardian import CircuitBreakerException, RestGuardian  # noqa: E402


@pytest.fixture
def fast_sleep(monkeypatch):
    """把 asyncio.sleep 变成立即返回（退避/冷却路径不真实等待）。"""

    async def _fast_sleep(_delay, *args, **kwargs):
        return None

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)


def test_concurrency_limit():
    """并发上限：6 个调用、并发=2 时峰值并发不超过 2。"""
    guardian = RestGuardian({"api_min_interval_sec": 0, "api_max_concurrency": 2, "api_max_retries": 1})
    peak = {"value": 0}
    current = {"value": 0}
    lock = asyncio.Lock()

    async def slow_call():
        async with lock:
            current["value"] += 1
            peak["value"] = max(peak["value"], current["value"])
        await asyncio.sleep(0.05)
        async with lock:
            current["value"] -= 1
        return True

    async def run():
        return await asyncio.gather(*[
            guardian.call(slow_call, priority="NORMAL") for _ in range(6)])

    results = asyncio.run(run())
    assert all(results)
    assert peak["value"] <= 2


def test_min_interval_throttle():
    """最小间隔：串行节流，相邻请求开始时间间隔 >= min_interval。"""
    min_interval = 0.05
    guardian = RestGuardian({"api_min_interval_sec": min_interval, "api_max_retries": 1})
    starts: list[float] = []

    def quick():
        starts.append(time.monotonic())
        return True

    async def run():
        return await asyncio.gather(*[guardian.call(quick) for _ in range(3)])

    asyncio.run(run())
    assert len(starts) == 3
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    # 并发 gather 下三个请求，节流保证任意相邻两个开始时间相差 >= min_interval（留少量时钟误差）
    assert all(g >= min_interval - 0.01 for g in gaps), gaps


def test_429_backoff_then_recover(fast_sleep):
    """429 指数退避：第一次 429、第二次成功；冷却被设置、请求计数正确。"""
    guardian = RestGuardian({"api_min_interval_sec": 0, "api_max_retries": 3,
                             "api_429_base_backoff_sec": 2})
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise Exception('binance HTTP 429 too many requests')
        return "ok"

    result = asyncio.run(guardian.call(flaky))
    assert result == "ok"
    assert attempts["n"] == 2
    assert guardian.cooldown_until > time.monotonic()  # 429 设置了冷却


def test_429_exhausts_retries(fast_sleep):
    """连续 429：重试 api_max_retries 次后抛出原始异常。"""
    guardian = RestGuardian({"api_min_interval_sec": 0, "api_max_retries": 3})

    def always_429():
        raise Exception("HTTP 429 rate limit exceeded")

    with pytest.raises(Exception, match="rate limit"):
        asyncio.run(guardian.call(always_429))
    assert guardian.error_count == 3


def test_circuit_breaker_opens_and_high_bypasses(fast_sleep):
    """熔断：连续失败达到阈值后 NORMAL 抛 CircuitBreakerException，HIGH 可绕过。"""
    guardian = RestGuardian({"api_min_interval_sec": 0, "api_max_retries": 1,
                             "api_failure_threshold": 2,
                             "api_circuit_breaker_cooldown_sec": 30})

    def failing():
        raise Exception("network unreachable")

    for _ in range(2):
        with pytest.raises(Exception):
            asyncio.run(guardian.call(failing))

    # NORMAL 被熔断拦截
    with pytest.raises(CircuitBreakerException):
        asyncio.run(guardian.call(failing))

    # HIGH 优先级绕过熔断（关键止损/平仓场景）
    def critical_ok():
        return "closed"

    assert asyncio.run(guardian.call(critical_ok, priority="HIGH")) == "closed"

    # 熔断恢复（模拟冷却结束）
    guardian.circuit_open_until = time.monotonic() - 1
    assert asyncio.run(guardian.call(lambda: "ok")) == "ok"


def test_418_long_cooldown(fast_sleep):
    """418 IP 封禁警告：设置更长的冷却时间。"""
    guardian = RestGuardian({"api_min_interval_sec": 0, "api_max_retries": 1,
                             "api_418_cooldown_sec": 60})

    def banned():
        raise Exception("binance HTTP 418 ip auto banned")

    with pytest.raises(Exception):
        asyncio.run(guardian.call(banned))
    # 418 冷却 60s > 普通 429 退避
    assert guardian.cooldown_until - time.monotonic() > 50
