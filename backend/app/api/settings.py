# backend/app/api/settings.py

from typing import Dict, Any, List

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

# --- 核心修改：确保导入了正确的配置加载和保存函数 ---
from ..config.config import load_settings, save_settings, ALL_AVAILABLE_COINS
# --- 修改结束 ---
from ..core.security import verify_api_key

# --- Pydantic 模型定义 ---
class SettingsResponse(BaseModel):
    user_settings: Dict[str, Any]
    all_available_coins: List[str] # 返回合并后的所有可用币种

# --- 路由定义 ---
router = APIRouter(prefix="/api/settings", tags=["Settings"], dependencies=[Depends(verify_api_key)])

@router.get("", response_model=SettingsResponse)
def get_settings():
    """
    获取所有用户配置和可选币种列表。
    - **user_settings**: 当前用户的配置。
    - **all_available_coins**: 从 coin_lists.json 加载的全局币种列表。
    """
    settings = load_settings()
    return {
        "user_settings": settings,
        "all_available_coins": ALL_AVAILABLE_COINS, # 提供全局币种列表
    }

# --- 新增 POST /api/settings 接口，用于保存所有用户设置 ---
@router.post("")
def update_settings(
    settings_update: Dict[str, Any] = Body(...) # 接收完整的设置对象进行更新
):
    """
    更新并保存用户配置。
    接收一个包含所有可配置字段的字典，并将其保存到 user_settings.json。
    """
    try:
        current_settings = load_settings()
        # --- 关键：合并更新，确保不会丢失用户未在 payload 中提供的字段 ---
        # 这里假设 payload 包含了所有需要更新的字段，并且是覆盖式的更新
        # 如果需要更细粒度的更新，可能需要更复杂的逻辑
        updated_settings = {**current_settings, **settings_update}

        # --- 确保关键列表字段的类型正确 ---
        # 确保 user_selected_* 字段是列表，即使 payload 中是 null 或其他类型
        updated_settings['user_selected_long_coins'] = updated_settings.get('user_selected_long_coins', [])
        updated_settings['user_selected_short_coins'] = updated_settings.get('user_selected_short_coins', [])
        # --- 结束 ---

        save_settings(updated_settings) # 调用保存函数
        return {"message": "Settings saved successfully"}
    except Exception as e:
        # 返回一个清晰的错误信息
        return {"error": f"Failed to save settings: {e}"}
# --- POST /api/settings 接口结束 ---


# --- 新增 POST /api/settings/update-pools 接口，用于更新币种选择 ---
@router.post("/update-pools")
def update_coin_pools(
    selected_long_coins: List[str] = Body(..., alias='selected_long_coins'),
    selected_short_coins: List[str] = Body(..., alias='selected_short_coins')
):
    """
    更新并保存用户选择的做多/做空币种列表。
    这个接口主要用于前端直接修改币种池时调用。
    """
    try:
        current_settings = load_settings()
        current_settings['user_selected_long_coins'] = selected_long_coins
        current_settings['user_selected_short_coins'] = selected_short_coins
        save_settings(current_settings)
        return {"message": "币种池选择已更新并保存。"}
    except Exception as e:
        return {"error": f"更新币种池选择失败: {e}"}
# --- POST /api/settings/update-pools 接口结束 ---