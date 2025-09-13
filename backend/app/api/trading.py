from fastapi import APIRouter
from ..core.trading_service import trading_service
from ..models.schemas import TradePlanRequest

router = APIRouter(prefix="/api/trading", tags=["Trading"])

@router.post("/start")
async def start(plan: TradePlanRequest):
    return await trading_service.start_trading(plan)

@router.post("/stop")
async def stop():
    return await trading_service.stop_trading()

@router.post("/sync-sltp")
async def sync_sltp_endpoint(settings: dict):
    """触发所有持仓的SL/TP校准任务"""
    return await trading_service.sync_all_sltp(settings)