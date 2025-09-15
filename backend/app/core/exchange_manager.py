# backend/app/core/exchange_manager.py (最终健壮版)
import contextlib
import asyncio
import ccxt.async_support as ccxt
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
        print(f"--- ❌ FATAL: 获取交易所连接在 {timeout} 秒内超时！请检查API Key/Secret、网络或代理设置。---")
        raise ConnectionAbortedError(f"获取交易所连接超时 ({timeout}s)")
    except Exception as e:
        print(f"--- ❌ FATAL: 初始化交易所时发生未知错误: {e} ---")
        raise

async def get_exchange_dependency():
    """FastAPI 依赖项"""
    exchange = await get_exchange_with_timeout()
    try:
        yield exchange
    finally:
        await exchange.close()

@contextlib.asynccontextmanager
async def get_exchange_for_task():
    """为后台任务提供一个安全的交易所实例上下文。"""
    exchange = await get_exchange_with_timeout()
    try:
        yield exchange
    finally:
        await exchange.close()