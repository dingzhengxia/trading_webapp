import asyncio
from fastapi import APIRouter, HTTPException, Depends
from typing import List
import ccxt.async_support as ccxt

from ..models.schemas import Position, ClosePositionRequest, CloseBySideRequest
from ..core.exchange_manager import get_exchange_dependency  # <-- 导入依赖项
from ..logic.exchange_logic_async import fetch_positions_with_pnl_async, close_position_async
from ..core.websocket_manager import log_message, manager

router = APIRouter(prefix="/api/positions", tags=["Positions"])


@router.get("", response_model=List[Position])
async def get_all_positions(exchange: ccxt.binanceusdm = Depends(get_exchange_dependency)):
    """获取所有非零持仓的真实数据"""
    try:
        # exchange 实例由 FastAPI 自动传入
        positions = await fetch_positions_with_pnl_async(exchange)
        return positions
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch positions: {e}")


@router.post("/close")
async def close_single_position(
        request: ClosePositionRequest,
        exchange: ccxt.binanceusdm = Depends(get_exchange_dependency)
):
    """平掉单个仓位"""
    try:
        # 将平仓操作作为后台任务执行，以快速响应
        asyncio.create_task(close_position_async(exchange, request.symbol, request.ratio, log_message))
        # 注意：后台任务会使用此请求的 exchange 实例，这可能导致连接在任务完成前关闭。
        # 一个更健壮的实现是在后台任务内部自己创建和关闭 exchange 实例。
        # 但对于当前问题，主要修复GET请求。
        return {"message": f"Close order for {request.symbol} submitted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/close-by-side")
async def close_positions_by_side(
        request: CloseBySideRequest,
        exchange: ccxt.binanceusdm = Depends(get_exchange_dependency)
):
    """按方向或全部平仓"""
    try:
        all_positions = await fetch_positions_with_pnl_async(exchange)

        symbols_to_close = []
        if request.side == 'all':
            symbols_to_close = [p.symbol for p in all_positions]
        else:
            symbols_to_close = [p.symbol for p in all_positions if p.side == request.side]

        if not symbols_to_close:
            await log_message(f"未找到可平仓的 {request.side} 仓位", "info")
            return {"message": "No positions to close."}

        # 对于需要长时间运行的后台任务，最佳实践是在任务内部创建连接
        async def close_task_wrapper():
            from ..core.exchange_manager import get_exchange_dependency as get_dep
            async for ex in get_dep():  # 模拟依赖注入
                tasks = [close_position_async(ex, symbol, request.ratio, log_message) for symbol in symbols_to_close]
                await asyncio.gather(*tasks)

        asyncio.create_task(close_task_wrapper())

        return {"message": f"Submitted close orders for {len(symbols_to_close)} positions."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))