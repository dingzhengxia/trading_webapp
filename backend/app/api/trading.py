# backend/app/api/trading.py (最终修复版)
from fastapi import APIRouter, BackgroundTasks
from ..core.trading_service import trading_service
from ..models.schemas import TradePlanRequest

router = APIRouter(prefix="/api/trading", tags=["Trading"])

@router.post("/start")
async def start_trading_task(plan: TradePlanRequest, background_tasks: BackgroundTasks):
    print("--- 📢 API HIT: /api/trading/start ---")
    return await trading_service.start_trading(plan, background_tasks)

@router.post("/stop")
async def stop_trading_task():
    print("--- 📢 API HIT: /api/trading/stop ---")
    return await trading_service.stop_trading()

@router.post("/sync-sltp")
async def sync_sltp_task(settings: dict, background_tasks: BackgroundTasks):
    print("--- 📢 API HIT: /api/trading/sync-sltp ---")
    return await trading_service.sync_all_sltp(settings, background_tasks)