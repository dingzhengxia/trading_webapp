# backend/app/api/settings.py
from typing import Dict, Any, List

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

# --- 修改导入 ---
from ..config.config import load_settings, save_settings, ALL_AVAILABLE_COINS, AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS
# --- 修改结束 ---
from ..core.security import verify_api_key

router = APIRouter(prefix="/api/settings", tags=["Settings"], dependencies=[Depends(verify_api_key)])
class SettingsResponse(BaseModel):
    user_settings: Dict[str, Any]
    # --- 修改：返回合并后的所有可用币种 ---
    all_available_coins: List[str]
    # --- 修改结束 ---

@router.get("", response_model=SettingsResponse)
def get_settings():
    """获取所有用户配置和可选币种列表"""
    settings = load_settings()
    return {
        "user_settings": settings,
        # --- 修改：返回合并后的列表 ---
        "all_available_coins": ALL_AVAILABLE_COINS,
        # --- 修改结束 ---
    }

# --- 新增 API: 更新币种池选择 ---
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
        # 触发配置更新通知（可选，取决于前端如何处理）
        return {"message": "币种池选择已更新并保存。"}
    except Exception as e:
        return {"error": f"更新币种池选择失败: {e}"}
# --- 新增 API 结束 ---