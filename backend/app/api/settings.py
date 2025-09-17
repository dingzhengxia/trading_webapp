# backend/app/api/settings.py

from typing import Dict, Any, List

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
import json
import os

# 从 config.py 中导入所有全局变量
from ..config.config import load_settings, save_settings, COIN_LISTS_FILE, AVAILABLE_COINS, AVAILABLE_LONG_COINS, \
    AVAILABLE_SHORT_COINS
from ..core.security import verify_api_key

router = APIRouter(prefix="/api/settings", tags=["Settings"], dependencies=[Depends(verify_api_key)])


# 修改响应模型以包含新的总列表
class SettingsResponse(BaseModel):
    user_settings: Dict[str, Any]
    available_coins: List[str]  # 新增字段
    available_long_coins: List[str]
    available_short_coins: List[str]


# 更新的类，用于接收币种池的更新
class CoinPoolsUpdate(BaseModel):
    long_coins_pool: List[str]
    short_coins_pool: List[str]


@router.get("", response_model=SettingsResponse)
def get_settings():
    """获取所有用户配置和可选币种列表"""
    # 确保返回的是内存中的最新列表
    return {
        "user_settings": load_settings(),
        "available_coins": AVAILABLE_COINS,  # 现在这个变量被正确导入了
        "available_long_coins": AVAILABLE_LONG_COINS,
        "available_short_coins": AVAILABLE_SHORT_COINS,
    }


@router.post("")
def update_settings(settings: Dict[str, Any] = Body(...)):
    """保存用户配置到 user_settings.json 文件。"""
    try:
        current_settings = load_settings()
        current_settings.update(settings)
        save_settings(current_settings)
        return {"message": "Settings saved successfully"}
    except Exception as e:
        return {"error": f"Failed to save settings: {e}"}


# --- 新增 API 端点：用于更新 coin_lists.json ---
@router.post("/update-coin-pools", status_code=204)
def update_coin_pools(pools: CoinPoolsUpdate):
    """
    更新 coin_lists.json 文件中的做多/做空币种池。
    """
    try:
        with open(COIN_LISTS_FILE, 'w', encoding='utf-8') as f:
            data_to_save = {
                # 保持 coins_pool 不变
                "coins_pool": AVAILABLE_COINS,
                "long_coins_pool": sorted(pools.long_coins_pool),
                "short_coins_pool": sorted(pools.short_coins_pool)
            }
            json.dump(data_to_save, f, indent=4, ensure_ascii=False)

        # 刷新内存中的变量，只对需要修改的变量使用 global
        global AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS
        AVAILABLE_LONG_COINS = data_to_save["long_coins_pool"]
        AVAILABLE_SHORT_COINS = data_to_save["short_coins_pool"]

        print(
            f"--- [INFO] Coin pools saved successfully. Long: {len(AVAILABLE_LONG_COINS)}, Short: {len(AVAILABLE_SHORT_COINS)} ---")

    except Exception as e:
        print(f"--- [ERROR] Failed to save coin pools: {e} ---")
        raise HTTPException(status_code=500, detail=f"Failed to save coin pools: {e}")