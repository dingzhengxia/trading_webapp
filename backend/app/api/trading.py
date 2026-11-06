# backend/app/api/trading.py
import ccxt.async_support as ccxt
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from ..core.exchange_manager import get_exchange_dependency
from ..core.security import verify_api_key
from ..core.trading_service import trading_service
from ..logic.utils import resolve_symbol_details
from ..models.schemas import (
    ManualTradeRequest,
    ResolveSymbolsResponse,
    ResolvedSymbol,
    SyncSltpRequest,
    TradePlanRequest,
)

router = APIRouter(prefix="/api/trading", tags=["Trading"], dependencies=[Depends(verify_api_key)])


@router.post("/start")
def start_trading_task(plan: TradePlanRequest, background_tasks: BackgroundTasks):
    return trading_service.start_trading(plan, background_tasks)


@router.post("/stop")
async def stop_trading_task():
    return await trading_service.stop_trading()


@router.post("/sync-sltp")
def sync_sltp_task(settings: SyncSltpRequest, background_tasks: BackgroundTasks):
    return trading_service.sync_all_sltp(settings, background_tasks)


@router.post("/manual")
def manual_trade_task(request: ManualTradeRequest, background_tasks: BackgroundTasks):
    """手动做多 / 做空 / 反手（限价 post-only；反手先全平再反向开仓）。"""
    return trading_service.manual_trade(request, background_tasks)


@router.get("/resolve-symbols", response_model=ResolveSymbolsResponse)
async def resolve_symbols(
        symbols: str = Query(..., description="逗号分隔的基础币种，例如 BTC,ETH,SOL"),
        exchange: ccxt.binanceusdm = Depends(get_exchange_dependency),
):
    """解析币种最终交易对（USDC 优先，其次 USDT）。"""
    names = []
    seen = set()
    for raw in str(symbols).split(','):
        symbol = raw.strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        names.append(symbol)

    if not names:
        raise HTTPException(status_code=400, detail="symbols 参数不能为空。")

    resolved_symbols = []
    for symbol in names:
        full_symbol, quote = resolve_symbol_details(exchange, symbol)
        resolved_symbols.append(ResolvedSymbol(
            symbol=symbol,
            full_symbol=full_symbol,
            quote=quote,
            available=full_symbol is not None,
        ))
    return ResolveSymbolsResponse(symbols=resolved_symbols)
