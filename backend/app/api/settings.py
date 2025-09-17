# backend/app/api/settings.py (重构版)
from typing import Dict, Any, List

from fastapi import APIRouter, Body, Depends
import json

# REFACTOR: 从 load_settings 改为只导入 save_settings
from ..config.config import save_settings, COIN_LISTS_FILE, AVAILABLE_COINS, AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS
from ..core.dependencies import get_settings_dependency
from ..core.security import verify_api_key
# REFACTOR: 导入 Pydantic 模型
from ..models.schemas import SettingsResponse, CoinPoolsUpdate

router = APIRouter(prefix="/api/settings", tags=["Settings"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=SettingsResponse)
def get_settings(settings: Dict[str, Any] = Depends(get_settings_dependency)):
    """获取所有用户配置和可选币种列表"""
    return {
        "user_settings": settings,
        "available_coins": AVAILABLE_COINS,
        "available_long_coins": AVAILABLE_LONG_COINS,
        "available_short_coins": AVAILABLE_SHORT_COINS,
    }


@router.post("")
def update_settings(
        updated_settings: Dict[str, Any] = Body(...),
        current_settings: Dict[str, Any] = Depends(get_settings_dependency)
):
    """保存用户配置到 user_settings.json 文件。"""
    # REFACTOR: 移除了 try/except
    current_settings.update(updated_settings)
    if save_settings(current_settings):
        return {"message": "Settings saved successfully"}
    # 虽然全局异常会捕获，但这里可以给出一个更具体的失败响应
    return {"error": "Failed to save settings"}


@router.post("/update-coin-pools", status_code=204)
def update_coin_pools(pools: CoinPoolsUpdate):
    """更新 coin_lists.json 文件中的做多/做空币种池。"""
    # REFACTOR: 移除了 try/except
    global AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS

    with open(COIN_LISTS_FILE, 'w', encoding='utf-8') as f:
        data_to_save = {
            # 保持总池不变
            "coins_pool": AVAILABLE_COINS,
            "long_coins_pool": sorted(list(set(pools.long_coins_pool))),
            "short_coins_pool": sorted(list(set(pools.short_coins_pool)))
        }
        json.dump(data_to_save, f, indent=4, ensure_ascii=False)

    # 刷新内存中的变量
    AVAILABLE_LONG_COINS = data_to_save["long_coins_pool"]
    AVAILABLE_SHORT_COINS = data_to_save["short_coins_pool"]

    print(
        f"--- [INFO] Coin pools saved successfully. Long: {len(AVAILABLE_LONG_COINS)}, Short: {len(AVAILABLE_SHORT_COINS)} ---")