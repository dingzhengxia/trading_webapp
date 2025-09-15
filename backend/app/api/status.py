# backend/app/api/status.py
from fastapi import APIRouter
from ..core.trading_service import trading_service

router = APIRouter(prefix="/api", tags=["Status"])

@router.get("/status")
async def get_service_status():
    """获取后端交易服务的当前运行状态"""
    return trading_service.get_current_status()