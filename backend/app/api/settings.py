# backend/app/api/settings.py (修改版，新增 /update-coin-pools)

from typing import Dict, Any, List

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
import json  # 导入 json 模块
import os  # 导入 os 模块

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
    # 新增字段，如果需要前端更新总列表
    coins_pool: List[str] = None


@router.get("", response_model=SettingsResponse)
def get_settings():
    """获取所有用户配置和可选币种列表"""
    # 确保返回的是内存中的最新列表
    return {
        "user_settings": load_settings(),
        "available_coins": AVAILABLE_COINS,  # 返回新的总列表
        "available_long_coins": AVAILABLE_LONG_COINS,
        "available_short_coins": AVAILABLE_SHORT_COINS,
    }


@router.post("")
def update_settings(settings: Dict[str, Any] = Body(...)):
    """更新并保存用户配置"""
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
                "coins_pool": sorted(list(set(pools.long_coins_pool + pools.short_coins_pool))),  # 新增：合并做多做空池来生成总列表
                "long_coins_pool": sorted(pools.long_coins_pool),
                "short_coins_pool": sorted(pools.short_coins_pool)
            }
            json.dump(data_to_save, f, indent=4, ensure_ascii=False)

        # 刷新内存中的变量
        global AVAILABLE_COINS, AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS
        AVAILABLE_COINS = data_to_save["coins_pool"]
        AVAILABLE_LONG_COINS = data_to_save["long_coins_pool"]
        AVAILABLE_SHORT_COINS = data_to_save["short_coins_pool"]

        print(
            f"--- [INFO] Coin pools updated successfully. New long pool: {AVAILABLE_LONG_COINS[:5]}..., New short pool: {AVAILABLE_SHORT_COINS[:5]}... ---")
        return {"message": "Coin pools updated successfully"}
    except Exception as e:
        print(f"--- [ERROR] Failed to update coin pools: {e} ---")
        raise HTTPException(status_code=500, detail=f"Failed to update coin pools: {e}")