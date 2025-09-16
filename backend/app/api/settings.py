# backend/app/api/settings.py
from typing import Dict, Any, List

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

from ..config.config import load_settings, save_settings, AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS
from ..core.security import verify_api_key

router = APIRouter(prefix="/api/settings", tags=["Settings"], dependencies=[Depends(verify_api_key)])

class SettingsResponse(BaseModel):
    user_settings: Dict[str, Any]
    available_long_coins: List[str]
    available_short_coins: List[str]

@router.get("", response_model=SettingsResponse)
def get_settings():
    """获取所有用户配置和可选币种列表"""
    return {
        "user_settings": load_settings(),
        "available_long_coins": AVAILABLE_LONG_COINS,
        "available_short_coins": AVAILABLE_SHORT_COINS,
    }

@router.post("")
def update_settings(settings: Dict[str, Any] = Body(...)):
    """更新并保存用户配置"""
    try:
        # 在保存前，先加载一次旧配置，确保不会丢失任何字段
        current_settings = load_settings()
        current_settings.update(settings)
        save_settings(current_settings)
        return {"message": "Settings saved successfully"}
    except Exception as e:
        return {"error": f"Failed to save settings: {e}"}