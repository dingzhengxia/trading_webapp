# backend/app/core/rest_guardian.py
"""异步 REST 限流保护器（从 monitor 的 RestGuardian 提取改造）。

统一包装 ccxt 的 REST 调用，提供：
- 并发上限（asyncio.Semaphore）
- 全局最小请求间隔（跨协程串行节流）
- HTTP 429 指数退避 + 随机抖动
- HTTP 418 长冷却
- 连续失败熔断（CircuitBreakerException）
- priority="HIGH" 可绕过熔断（仅限关键止损/平仓，信号扫描只用 NORMAL/LOW）

所有配置通过 `call(..., conf=...)` 在调用时传入，默认值见 DEFAULT_API_LIMIT；
user_settings 中的 api_* 字段由调用方合并后传入。
"""
import asyncio
import inspect
import random
import time
from typing import Any, Awaitable, Callable, Dict, Optional

from loguru import logger

DEFAULT_API_LIMIT: Dict[str, Any] = {
    "api_max_concurrency": 3,
    "api_min_interval_sec": 0.08,
    "api_max_retries": 3,
    "api_failure_threshold": 5,
    "api_circuit_breaker_cooldown_sec": 30,
    "api_418_cooldown_sec": 60,
    "api_429_base_backoff_sec": 2,
    "api_429_max_backoff_sec": 30,
}


class CircuitBreakerException(Exception):
    """REST 断路器处于 OPEN 状态时抛出。"""


class RestGuardian:
    """线程/协程安全的异步 REST 限流器（每个事件循环维护独立锁与信号量）。"""

    def __init__(self, conf: Optional[Dict[str, Any]] = None):
        self._base_conf: Dict[str, Any] = dict(DEFAULT_API_LIMIT)
        if conf:
            self.configure(conf)
        # 每个事件循环一份运行时状态，避免跨 asyncio.run 复用锁导致绑定错误
        self._loop_states: Dict[Any, Dict[str, Any]] = {}
        # 以下计数器跨循环共享，便于观测
        self.failures = 0
        self.circuit_open_until = 0.0
        self.cooldown_until = 0.0
        self.last_circuit_log_time = 0.0
        self.request_count = 0
        self.error_count = 0

    # ------------------------------------------------------------------ 配置
    def configure(self, conf: Optional[Dict[str, Any]]) -> None:
        if not conf:
            return
        for key, value in dict(conf).items():
            if key in DEFAULT_API_LIMIT:
                self._base_conf[key] = value

    def _merged_conf(self, conf: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        merged = dict(self._base_conf)
        for key, value in (conf or {}).items():
            if key in DEFAULT_API_LIMIT:
                merged[key] = value
        return merged

    # ------------------------------------------------------------------ 状态
    def _state(self) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        state = self._loop_states.get(loop)
        if state is None:
            state = {
                "start_lock": asyncio.Lock(),
                "semaphores": {},
                "next_start": 0.0,
            }
            self._loop_states[loop] = state
        return state

    def _semaphore(self, limit: int) -> asyncio.Semaphore:
        limit = max(1, int(limit))
        state = self._state()
        semaphore = state["semaphores"].get(limit)
        if semaphore is None:
            semaphore = asyncio.Semaphore(limit)
            state["semaphores"][limit] = semaphore
        return semaphore

    def reset(self) -> None:
        """重置熔断/冷却状态（测试或手动恢复用）。"""
        self.failures = 0
        self.circuit_open_until = 0.0
        self.cooldown_until = 0.0
        self.last_circuit_log_time = 0.0
        self._loop_states.clear()

    def is_circuit_open(self) -> bool:
        return time.monotonic() < self.circuit_open_until

    def stats(self) -> Dict[str, Any]:
        return {
            "request_count": self.request_count,
            "error_count": self.error_count,
            "failures": self.failures,
            "circuit_open": self.is_circuit_open(),
            "circuit_open_until": self.circuit_open_until,
            "cooldown_until": self.cooldown_until,
        }

    # ------------------------------------------------------------------ 节流
    async def _throttle(self, min_interval: float) -> None:
        if min_interval <= 0:
            return
        state = self._state()
        async with state["start_lock"]:
            now = time.monotonic()
            if now < state["next_start"]:
                await asyncio.sleep(state["next_start"] - now)
            state["next_start"] = time.monotonic() + min_interval

    # ------------------------------------------------------------------ 主入口
    async def call(self, func: Callable[..., Any], *args, priority: str = "NORMAL",
                   conf: Optional[Dict[str, Any]] = None, **kwargs) -> Any:
        """统一包装所有 ccxt REST 调用。

        :param func: 同步或异步 callable
        :param priority: HIGH / NORMAL / LOW；HIGH 可绕过熔断（关键止损/平仓）
        :param conf: api_* 配置覆盖（并发、间隔、重试、熔断等）
        """
        merged = self._merged_conf(conf)
        priority = str(priority or "NORMAL").upper()
        retries = max(1, int(merged["api_max_retries"]))
        min_interval = max(0.0, float(merged["api_min_interval_sec"]))
        max_concurrency = max(1, int(merged["api_max_concurrency"]))
        failure_threshold = max(1, int(merged["api_failure_threshold"]))
        circuit_cooldown = max(1.0, float(merged["api_circuit_breaker_cooldown_sec"]))
        backoff_base = max(0.2, float(merged["api_429_base_backoff_sec"]))
        backoff_max = max(backoff_base, float(merged["api_429_max_backoff_sec"]))

        # 熔断检查：HIGH 优先级可绕过
        if priority != "HIGH":
            now = time.monotonic()
            if now < self.circuit_open_until:
                remaining = round(self.circuit_open_until - now, 1)
                raise CircuitBreakerException(
                    f"REST 断路器处于 OPEN 保护状态，剩余冷却时间: {remaining} 秒")

        last_exc: Optional[Exception] = None
        for attempt in range(retries):
            # 429/418 冷却：在每次尝试开始前等待
            cooldown_remaining = self.cooldown_until - time.monotonic()
            if cooldown_remaining > 0:
                await asyncio.sleep(cooldown_remaining)

            await self._throttle(min_interval)

            try:
                async with self._semaphore(max_concurrency):
                    self.request_count += 1
                    result = func(*args, **kwargs)
                    if inspect.isawaitable(result):
                        result = await result
                self.failures = 0
                return result

            except Exception as exc:  # noqa: BLE001 - 需要分类 429/418
                last_exc = exc
                self.failures += 1
                self.error_count += 1
                text = str(exc).lower()
                is_429 = "429" in text or "too many requests" in text or "rate limit" in text
                is_418 = "418" in text or "ip banned" in text

                if is_418:
                    cool_sec = max(1.0, float(merged["api_418_cooldown_sec"]))
                    self.cooldown_until = max(self.cooldown_until, time.monotonic() + cool_sec)
                    logger.error(
                        f"🚨 [API 严重警告] 触发 HTTP 418 IP 封禁警告！强制休眠 {cool_sec:.0f} 秒！")
                elif is_429:
                    raw_backoff = min(backoff_max, backoff_base * (2 ** min(attempt, 4)))
                    backoff = raw_backoff * random.uniform(0.8, 1.2)
                    self.cooldown_until = max(self.cooldown_until, time.monotonic() + backoff)
                    logger.warning(
                        f"⚠️ [API 限流] 触发 HTTP 429 请求过快（尝试 {attempt + 1}/{retries}），"
                        f"退避 {backoff:.2f} 秒...")

                if self.failures >= failure_threshold:
                    self.circuit_open_until = time.monotonic() + circuit_cooldown
                    if time.monotonic() - self.last_circuit_log_time > 10:
                        logger.error(
                            f"🚨 [断路器熔断] REST 连续失败 {self.failures} 次，"
                            f"开启 {circuit_cooldown:.0f} 秒熔断保护！")
                        self.last_circuit_log_time = time.monotonic()

                if attempt + 1 >= retries:
                    break
                # 429/418 的退避在下一轮开头统一 sleep；其他错误立即重试

        assert last_exc is not None
        raise last_exc
