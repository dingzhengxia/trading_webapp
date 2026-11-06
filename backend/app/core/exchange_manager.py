# backend/app/core/exchange_manager.py (最终健壮版)
import asyncio
import contextlib

from ..config.config import load_settings
from ..logic.exchange_logic_async import initialize_exchange_async


# --- 核心修改在这里 ---
async def get_exchange_with_timeout(timeout=20):
    """获取交易所实例，并设置一个总的连接和加载市场的超时。"""
    settings = load_settings()
    try:
        # 将整个初始化过程包裹在 asyncio.wait_for 中
        exchange = await asyncio.wait_for(
            initialize_exchange_async(
                api_key=settings.get('api_key'),
                api_secret=settings.get('api_secret'),
                use_testnet=settings.get('use_testnet'),
                enable_proxy=settings.get('enable_proxy'),
                proxy_url=settings.get('proxy_url')
            ),
            timeout=timeout
        )
        return exchange
    except asyncio.TimeoutError:
        print(f"--- [FATAL] 获取交易所连接在 {timeout} 秒内超时！请检查API Key/Secret、网络或代理设置。---")
        raise ConnectionAbortedError(f"获取交易所连接超时 ({timeout}s)")
    except Exception as e:
        print(f"--- [FATAL] 初始化交易所时发生未知错误: {e} ---")
        raise


# --- 共享 exchange（MERGE_PLAN §2.2）---
# 读接口（/api/positions、/api/settings/add-coin、/api/trading/resolve-symbols、
# /api/rebalance/plan、信号扫描）复用同一个懒加载实例，只 load_markets 一次；
# lifespan shutdown 时通过 close_shared_exchange() 关闭。
# 与 RestGuardian 同样的思路：每个事件循环维护独立锁，避免跨 asyncio.run 复用锁。
_shared_exchange = None
_shared_loop_states: dict = {}


def _shared_state() -> dict:
    loop = asyncio.get_running_loop()
    state = _shared_loop_states.get(loop)
    if state is None:
        state = {"lock": asyncio.Lock()}
        _shared_loop_states[loop] = state
    return state


async def get_shared_exchange():
    """懒加载共享交易所实例（asyncio.Lock 保护，只 load_markets 一次）。"""
    global _shared_exchange
    state = _shared_state()
    async with state["lock"]:
        if _shared_exchange is None:
            _shared_exchange = await get_exchange_with_timeout()
        return _shared_exchange


async def close_shared_exchange() -> None:
    """关闭共享实例（FastAPI lifespan shutdown 调用；未创建时安全跳过）。"""
    global _shared_exchange
    if _shared_exchange is not None:
        try:
            await _shared_exchange.close()
        except Exception as e:
            print(f"--- [WARNING] 关闭共享交易所实例时出错: {e} ---")
        _shared_exchange = None
    _shared_loop_states.clear()


async def get_exchange_dependency():
    """FastAPI 依赖项：yield 共享实例且不 close（由 lifespan 统一关闭）。

    签名与行为不变，测试仍可通过 app.dependency_overrides 覆盖。
    """
    exchange = await get_shared_exchange()
    yield exchange


@contextlib.asynccontextmanager
async def get_exchange_for_task():
    """为后台任务提供一个安全的交易所实例上下文（独立实例、用完 close）。"""
    exchange = await get_exchange_with_timeout()
    try:
        yield exchange
    finally:
        await exchange.close()
