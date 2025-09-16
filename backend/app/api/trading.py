# backend/app/api/trading.py (最终完整版)
from fastapi import APIRouter, BackgroundTasks, Depends

from ..core.security import verify_api_key
from ..core.trading_service import trading_service
from ..models.schemas import TradePlanRequest, SyncSltpRequest

router = APIRouter(prefix="/api/trading", tags=["Trading"],dependencies=[Depends(verify_api_key)])

@router.post("/start")
def start_trading_task(plan: TradePlanRequest, background_tasks: BackgroundTasks):
    print("--- 📢 API HIT: /api/trading/start ---")
    return trading_service.start_trading(plan, background_tasks)

@router.post("/stop")
async def stop_trading_task():
    print("--- 📢 API HIT: /api/trading/stop ---")
    return await trading_service.stop_trading()

@router.post("/sync-sltp")
def sync_sltp_task(settings: SyncSltpRequest, background_tasks: BackgroundTasks):
    print("--- 📢 API HIT: /api/trading/sync-sltp ---")
    return trading_service.sync_all_sltp(settings, background_tasks)