# backend/app/api/positions.py
from typing import Any, Dict, List

import ccxt.async_support as ccxt
from fastapi import APIRouter, BackgroundTasks, Depends

from ..core.dependencies import get_settings_dependency
from ..core.exchange_manager import get_exchange_dependency
from ..core.security import verify_api_key
from ..core.trading_service import trading_service
from ..logic.exchange_logic_async import fetch_positions_with_pnl_async
from ..models.schemas import CloseBySideRequest, CloseMultipleRequest, ClosePositionRequest, Position

router = APIRouter(prefix="/api/positions", tags=["Positions"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=List[Position])
async def get_all_positions(
        exchange: ccxt.binanceusdm = Depends(get_exchange_dependency),
        settings: Dict[str, Any] = Depends(get_settings_dependency)
):
    # 交易所异常会向上抛，由全局异常处理器记录并返回 500，而不是伪装成"无持仓"
    positions = await fetch_positions_with_pnl_async(exchange, settings.get('leverage', 1))
    return positions


@router.post("/close")
def close_single_position(
        request: ClosePositionRequest,
        background_tasks: BackgroundTasks,
        settings: Dict[str, Any] = Depends(get_settings_dependency)
):
    tasks_data = [(request.full_symbol, request.ratio)]
    return trading_service.dispatch_tasks("平仓", tasks_data, 'CLOSE_ORDER', settings, background_tasks)


@router.post("/close-by-side")
async def close_positions_by_side(
        request: CloseBySideRequest,
        background_tasks: BackgroundTasks,
        exchange: ccxt.binanceusdm = Depends(get_exchange_dependency),
        settings: Dict[str, Any] = Depends(get_settings_dependency)
):
    all_positions = await fetch_positions_with_pnl_async(exchange, settings.get('leverage', 1))

    if request.side == 'all':
        symbols_to_close = [p.full_symbol for p in all_positions]
    else:
        symbols_to_close = [p.full_symbol for p in all_positions if p.side == request.side]

    tasks_data = [(full_symbol, request.ratio) for full_symbol in symbols_to_close]
    return trading_service.dispatch_tasks(f"批量平仓-{request.side}", tasks_data, 'CLOSE_ORDER', settings,
                                          background_tasks)


@router.post("/close-multiple")
def close_multiple_positions(
        request: CloseMultipleRequest,
        background_tasks: BackgroundTasks,
        settings: Dict[str, Any] = Depends(get_settings_dependency)
):
    tasks_data = [(full_symbol, request.ratio) for full_symbol in request.full_symbols]
    return trading_service.dispatch_tasks("平掉选中", tasks_data, 'CLOSE_ORDER', settings, background_tasks)
