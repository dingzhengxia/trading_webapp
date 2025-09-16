# backend/app/api/settings.py
from typing import Dict, Any, List

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

# --- 修改导入 ---
from ..config.config import load_settings, save_settings, ALL_AVAILABLE_COINS
# --- 移除了 user_selected_* 相关的导入 ---
from ..core.security import verify_api_key
router = APIRouter(prefix="/api/settings", tags=["Settings"], dependencies=[Depends(verify_api_key)])
class SettingsResponse(BaseModel):
    user_settings: Dict[str, Any]
    all_available_coins: List[str]

@router.get("", response_model=SettingsResponse)
def get_settings():
    """获取所有用户配置和可选币种列表"""
    settings = load_settings()
    return {
        "user_settings": settings,
        "all_available_coins": ALL_AVAILABLE_COINS,
    }

# --- POST /api/settings 接口，用于更新所有设置 ---
@router.post("")
def update_settings(
    settings_update: Dict[str, Any] = Body(...)
):
    """更新并保存用户配置，包括 long_coin_list 和 short_coin_list"""
    try:
        current_settings = load_settings()
        updated_settings = {**current_settings, **settings_update}

        # --- 确保列表字段是列表类型 ---
        updated_settings['long_coin_list'] = updated_settings.get('long_coin_list', [])
        updated_settings['short_coin_list'] = updated_settings.get('short_coin_list', [])
        # --- 结束 ---

        save_settings(updated_settings)
        return {"message": "Settings saved successfully"}
    except Exception as e:
        return {"error": f"Failed to save settings: {e}"}
# --- POST /api/settings 接口结束 ---

# --- 移除了 update-pools 接口，因为现在所有更新都通过 /api/settings POST ---
# --- 如果需要单独更新 pool，可以保留，但目前 POST /api/settings 已经可以处理 ---
# @router.post("/update-pools")
# def update_coin_pools(...)
# --- 移除非必须接口 ---