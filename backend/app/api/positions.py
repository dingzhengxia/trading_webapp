# backend/app/api/positions.py
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
    # ... (此方法保持不变)
    pass


@router.post("/close")
async def close_single_position(request: ClosePositionRequest):
    config = load_settings()
    tasks = [(request.full_symbol, request.ratio)]
    return await trading_service.dispatch_tasks("平仓", tasks, 'CLOSE_ORDER', config)


@router.post("/close-by-side")
async def close_positions_by_side(
        request: CloseBySideRequest,
        exchange: ccxt.binanceusdm = Depends(get_exchange_dependency)
):
    config = load_settings()
    try:
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
    config = load_settings()
    tasks = [(full_symbol, request.ratio) for full_symbol in request.full_symbols]
    return await trading_service.dispatch_tasks("平掉选中", tasks, 'CLOSE_ORDER', config)