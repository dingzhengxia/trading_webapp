# backend/app/api/settings.py
from typing import Dict, Any, List

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

# --- 修改导入 ---
from ..config.config import load_settings, save_settings, ALL_AVAILABLE_COINS
# --- 移除 AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS 的直接导入，因为它们不再是后端逻辑的主要来源 ---
from ..config.config import ALL_AVAILABLE_COINS # 仅保留全局列表
# --- 修改结束 ---
from ..core.security import verify_api_key

router = APIRouter(prefix="/api/settings", tags=["Settings"], dependencies=[Depends(verify_api_key)])
class SettingsResponse(BaseModel):
    user_settings: Dict[str, Any]
    all_available_coins: List[str] # 返回合并后的所有可用币种

@router.get("", response_model=SettingsResponse)
def get_settings():
    """获取所有用户配置和可选币种列表"""
    settings = load_settings()
    return {
        "user_settings": settings,
        "all_available_coins": ALL_AVAILABLE_COINS, # 返回合并后的所有币种
    }

@router.post("/update-pools")
def update_coin_pools(
    selected_long_coins: List[str] = Body(..., alias='selected_long_coins'),
    selected_short_coins: List[str] = Body(..., alias='selected_short_coins')
):
    """更新并保存用户选择的做多/做空币种列表"""
    try:
        current_settings = load_settings()
        current_settings['user_selected_long_coins'] = selected_long_coins
        current_settings['user_selected_short_coins'] = selected_short_coins
        save_settings(current_settings)
        return {"message": "币种池选择已更新并保存。"}
    except Exception as e:
        return {"error": f"更新币种池选择失败: {e}"}