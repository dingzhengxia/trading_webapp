# backend/app/core/guarded_exchange.py
"""GuardedExchange：ccxt 异步 exchange 的限流代理（R-P1-1，交易链路全量接入 RestGuardian）。

设计契约（ARCH_REFACTOR_PHASE3 §1.2）：
- 业务代码调用形态完全不变（``await exchange.create_order(...)``），代理按
  **方法名**从静态映射表取优先级，零运行时开销、业务代码不感知优先级；
- HIGH = 交易决策与下单撤单类（绕过熔断，仍受并发/最小间隔约束）；
  NORMAL = 行情/元数据读；LOW = 大批量扫描读；
- 不在表内的一切属性/方法（``markets``、``amount_to_precision``、``close``、
  ``set_sandbox_mode`` 等）**原样透传**，不包装；
- ``__setattr__`` 同步委托到 underlying：``exchange._twa_hedge_mode`` 等缓存
  必须落在真实实例上，随底层实例生命周期存续；
- 全项目只有一个地方接触裸 ccxt（``initialize_exchange_async`` 构造 + 本模块）；
  ``raw_rest_method`` 供已有自建 guardian 的子系统（protection / 行情层测试路径）
  解包原始方法，避免双重限流——它是唯一允许访问 ``.underlying`` 的辅助入口。
"""
from typing import Any, Callable

REST_PRIORITY: dict[str, str] = {
    # HIGH：交易关键，绕过熔断（仍受并发/最小间隔约束）
    'create_order': 'HIGH', 'cancel_order': 'HIGH', 'cancel_all_orders': 'HIGH',
    'edit_order': 'HIGH', 'fetch_order': 'HIGH', 'fetch_open_orders': 'HIGH',
    'fetch_positions': 'HIGH', 'fetch_position_mode': 'HIGH',
    'fetch_balance': 'HIGH', 'set_leverage': 'HIGH',
    # NORMAL：行情/元数据读
    'fetch_tickers': 'NORMAL', 'fetch_ticker': 'NORMAL',
    'fetch_order_book': 'NORMAL', 'load_markets': 'NORMAL',
    'fetch_funding_rate': 'NORMAL', 'fetch_leverage': 'NORMAL',
    # LOW：大批量扫描读
    'fetch_ohlcv': 'LOW',
}


def raw_rest_method(exchange: Any, name: str) -> Any:
    """返回 exchange 上未包装的原始 REST 方法。

    exchange 为 GuardedExchange 代理时解包 underlying（避免与调用方自建的
    guardian 双重限流/双重计数）；普通实例（fake/裸 ccxt）原样返回属性。
    """
    target = exchange.underlying if hasattr(exchange, 'underlying') else exchange
    return getattr(target, name)


class GuardedExchange:
    """ccxt 异步 exchange 的限流代理；非 REST 属性/方法原样透传。"""

    def __init__(self, exchange: Any, guardian: Any) -> None:
        # __setattr__ 会委托到 underlying，因此内部字段必须绕过委托直接写实例字典
        object.__setattr__(self, '_exchange', exchange)
        object.__setattr__(self, '_guardian', guardian)

    @property
    def underlying(self) -> Any:
        """被包装的真实 ccxt 实例（仅本模块与测试可访问）。"""
        return self._exchange

    def __getattr__(self, name: str) -> Any:
        """仅当常规属性查找失败时进入（_exchange/_guardian 已在实例字典中）。

        name 命中 REST_PRIORITY 且可调用 → 返回经 guardian.call(priority=...)
        包装的协程函数；否则原样透传。
        """
        exchange = object.__getattribute__(self, '_exchange')
        guardian = object.__getattribute__(self, '_guardian')
        attribute = getattr(exchange, name)
        priority = REST_PRIORITY.get(name)
        if priority is None or not callable(attribute):
            return attribute

        async def guarded_call(*args: Any, **kwargs: Any) -> Any:
            return await guardian.call(attribute, *args, priority=priority, **kwargs)

        guarded_call.__name__ = name
        guarded_call.__qualname__ = f"GuardedExchange.{name}"
        return guarded_call

    def __setattr__(self, name: str, value: Any) -> None:
        """属性写委托到 underlying（_twa_hedge_mode 等缓存落在真实实例上）。"""
        setattr(self._exchange, name, value)


def wrap_exchange(exchange: Any, guardian: Any) -> Any:
    """统一包装入口：future 扩展（如多层代理）只改这里。"""
    return GuardedExchange(exchange, guardian)
