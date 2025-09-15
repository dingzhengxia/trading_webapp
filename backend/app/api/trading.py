# backend/app/api/trading.py (添加日志)
from fastapi import APIRouter
from ..core.trading_service import trading_service
from ..models.schemas import TradePlanRequest

router = APIRouter(prefix="/api/trading", tags=["Trading"])

@router.post("/start")
async def start(plan: TradePlanRequest):
    print("--- 📢 API HIT: /api/trading/start ---") # <-- 新增：控制台日志
    return await trading_service.start_trading(plan)

@router.post("/stop")
async def stop():
    print("--- 📢 API HIT: /api/trading/stop ---") # <-- 新增：控制台日志
    return await trading_service.stop_trading()

@router.post("/sync-sltp")
async def sync_sltp_endpoint(settings: dict):
    print("--- 📢 API HIT: /api/trading/sync-sltp ---") # <-- 新增：控制台日志
    return await trading_service.sync_all_sltp(settings)