# backend/app/api/positions.py (最终完整版)
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
import ccxt.async_support as ccxt
from typing import List

from ..core.security import verify_api_key
from ..models.schemas import Position, ClosePositionRequest, CloseBySideRequest, CloseMultipleRequest
from ..core.exchange_manager import get_exchange_dependency
from ..logic.exchange_logic_async import fetch_positions_with_pnl_async
from ..config.config import load_settings
from ..core.trading_service import trading_service

router = APIRouter(prefix="/api/positions", tags=["Positions"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=List[Position])
async def get_all_positions(exchange: ccxt.binanceusdm = Depends(get_exchange_dependency)):
    try:
        settings = load_settings()
        positions = await fetch_positions_with_pnl_async(exchange, settings.get('leverage', 1))
        return positions
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch positions: {e}")


@router.post("/close")
def close_single_position(request: ClosePositionRequest, background_tasks: BackgroundTasks):
    print("--- 📢 API HIT: /api/positions/close ---")
    config = load_settings()
    tasks_data = [(request.full_symbol, request.ratio)]
    return trading_service.dispatch_tasks("平仓", tasks_data, 'CLOSE_ORDER', config, background_tasks)


@router.post("/close-by-side")
async def close_positions_by_side(
        request: CloseBySideRequest,
        background_tasks: BackgroundTasks,
        exchange: ccxt.binanceusdm = Depends(get_exchange_dependency)
):
    print(f"--- 📢 API HIT: /api/positions/close-by-side (side: {request.side}) ---")
    config = load_settings()
    try:
        all_positions = await fetch_positions_with_pnl_async(exchange, config.get('leverage', 1))
        symbols_to_close = []
        if request.side == 'all':
            symbols_to_close = [p.full_symbol for p in all_positions]
        else:
            symbols_to_close = [p.full_symbol for p in all_positions if p.side == request.side]

        tasks_data = [(full_symbol, request.ratio) for full_symbol in symbols_to_close]
        return trading_service.dispatch_tasks(f"批量平仓-{request.side}", tasks_data, 'CLOSE_ORDER', config,
                                              background_tasks)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/close-multiple")
def close_multiple_positions(request: CloseMultipleRequest, background_tasks: BackgroundTasks):
    print("--- 📢 API HIT: /api/positions/close-multiple ---")
    config = load_settings()
    tasks_data = [(full_symbol, request.ratio) for full_symbol in request.full_symbols]
    return trading_service.dispatch_tasks("平掉选中", tasks_data, 'CLOSE_ORDER', config, background_tasks)
