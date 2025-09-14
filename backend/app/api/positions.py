import asyncio
from fastapi import APIRouter, HTTPException, Depends
from typing import List
import ccxt.async_support as ccxt

from ..models.schemas import Position, ClosePositionRequest, CloseBySideRequest, CloseMultipleRequest
from ..core.exchange_manager import get_exchange_dependency
from ..logic.exchange_logic_async import fetch_positions_with_pnl_async
from ..config.config import load_settings
from ..core.trading_service import trading_service

router = APIRouter(prefix="/api/positions", tags=["Positions"])


@router.get("", response_model=List[Position])
async def get_all_positions(exchange: ccxt.binanceusdm = Depends(get_exchange_dependency)):
    """获取所有非零持仓的实时数据"""
    try:
        settings = load_settings()
        positions = await fetch_positions_with_pnl_async(exchange, settings.get('leverage', 1))
        return positions
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch positions: {e}")


@router.post("/close")
async def close_single_position(request: ClosePositionRequest):
    """
    提交一个平掉单个仓位的任务。
    """
    config = load_settings()
    # 将任务数据打包成一个列表，以便统一处理
    tasks = [(request.full_symbol, request.ratio)]
    return await trading_service.dispatch_tasks("平仓", tasks, 'CLOSE_ORDER', config)


@router.post("/close-by-side")
async def close_positions_by_side(
        request: CloseBySideRequest,
        exchange: ccxt.binanceusdm = Depends(get_exchange_dependency)
):
    """
    提交按方向批量平仓的任务。
    """
    config = load_settings()
    try:
        # 需要在这里获取一次持仓，以确定要平仓的具体交易对
        all_positions = await fetch_positions_with_pnl_async(exchange, config.get('leverage', 1))

        symbols_to_close = []
        if request.side == 'all':
            symbols_to_close = [p.full_symbol for p in all_positions]
        else:
            symbols_to_close = [p.full_symbol for p in all_positions if p.side == request.side]

        tasks = [(full_symbol, request.ratio) for full_symbol in symbols_to_close]
        return await trading_service.dispatch_tasks(f"批量平仓-{request.side}", tasks, 'CLOSE_ORDER', config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/close-multiple")
async def close_multiple_positions(request: CloseMultipleRequest):
    """
    提交平掉多个选中仓位的任务。
    """
    config = load_settings()
    tasks = [(full_symbol, request.ratio) for full_symbol in request.full_symbols]
    return await trading_service.dispatch_tasks("平掉选中", tasks, 'CLOSE_ORDER', config)