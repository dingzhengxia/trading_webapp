# backend/app/core/exchange_manager.py (完整代码)
import contextlib
import ccxt.async_support as ccxt
from ..config.config import load_settings
from ..logic.exchange_logic_async import initialize_exchange_async


async def get_exchange_dependency():
    """FastAPI 依赖项，为每个Web请求管理连接生命周期。"""
    settings = load_settings()
    exchange = await initialize_exchange_async(
        api_key=settings.get('api_key'),
        api_secret=settings.get('api_secret'),
        use_testnet=settings.get('use_testnet'),
        enable_proxy=settings.get('enable_proxy'),
        proxy_url=settings.get('proxy_url')
    )
    try:
        yield exchange
    finally:
        await exchange.close()


# --- 核心修复：为后台任务创建上下文管理器 ---
@contextlib.asynccontextmanager
async def get_exchange_for_task():
    """
    为后台任务提供一个安全的交易所实例上下文。
    用法: async with get_exchange_for_task() as exchange: ...
    """
    settings = load_settings()
    exchange = await initialize_exchange_async(
        api_key=settings.get('api_key'),
        api_secret=settings.get('api_secret'),
        use_testnet=settings.get('use_testnet'),
        enable_proxy=settings.get('enable_proxy'),
        proxy_url=settings.get('proxy_url')
    )
    try:
        yield exchange
    finally:
        await exchange.close()
# --- 修复结束 ---
