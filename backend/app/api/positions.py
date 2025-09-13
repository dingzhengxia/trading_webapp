import asyncio
from fastapi import APIRouter, HTTPException, Depends
from typing import List
import ccxt.async_support as ccxt

from ..models.schemas import Position, ClosePositionRequest, CloseBySideRequest
from ..core.exchange_manager import get_exchange_dependency
from ..logic.exchange_logic_async import fetch_positions_with_pnl_async, close_position_async
from ..core.websocket_manager import log_message, manager
from ..config.config import load_settings

router = APIRouter(prefix="/api/positions", tags=["Positions"])


@router.get("", response_model=List[Position])
async def get_all_positions(exchange: ccxt.binanceusdm = Depends(get_exchange_dependency)):
    try:
        settings = load_settings()
        positions = await fetch_positions_with_pnl_async(exchange, settings.get('leverage', 1))
        return positions
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch positions: {e}")


@router.post("/close")
async def close_single_position(
        request: ClosePositionRequest,
        exchange: ccxt.binanceusdm = Depends(get_exchange_dependency)
):
    try:
        await close_position_async(exchange, request.full_symbol, request.ratio, log_message)
        asyncio.create_task(manager.broadcast({"type": "refresh_positions"}))
        return {"message": f"Close order for {request.full_symbol} submitted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/close-by-side")
async def close_positions_by_side(
        request: CloseBySideRequest,
        exchange: ccxt.binanceusdm = Depends(get_exchange_dependency)
):
    try:
        settings = load_settings()
        all_positions = await fetch_positions_with_pnl_async(exchange, settings.get('leverage', 1))

        symbols_to_close = []
        if request.side == 'all':
            symbols_to_close = [p.full_symbol for p in all_positions]
        else:
            symbols_to_close = [p.full_symbol for p in all_positions if p.side == request.side]

        if not symbols_to_close:
            await log_message(f"未找到可平仓的 {request.side} 仓位", "info")
            return {"message": "No positions to close."}

        tasks = [close_position_async(exchange, full_symbol, request.ratio, log_message) for full_symbol in
                 symbols_to_close]
        await asyncio.gather(*tasks)

        asyncio.create_task(manager.broadcast({"type": "refresh_positions"}))

        return {"message": f"Submitted close orders for {len(symbols_to_close)} positions."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))