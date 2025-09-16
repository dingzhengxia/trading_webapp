# backend/app/api/settings.py (修改版，新增 /update-coin-pools)

from typing import Dict, Any, List

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
import json # 导入 json 模块
import os # 导入 os 模块

from ..config.config import load_settings, save_settings, COIN_LISTS_FILE, AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS
from ..core.security import verify_api_key

router = APIRouter(prefix="/api/settings", tags=["Settings"], dependencies=[Depends(verify_api_key)])

class SettingsResponse(BaseModel):
    user_settings: Dict[str, Any]
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

# --- 新增 API 端点：用于更新 coin_lists.json ---
@router.post("/update-coin-pools", status_code=204) # No Content response for success
def update_coin_pools(pools: CoinPoolsUpdate):
    """
    更新 coin_lists.json 文件中的做多/做空币种池。
    """
    try:
        # 确保写入时是 UTF-8 编码，并且使用缩进以保持可读性
        with open(COIN_LISTS_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "long_coins_pool": sorted(pools.long_coins_pool), # 排序以保持一致性
                "short_coins_pool": sorted(pools.short_coins_pool)
            }, f, indent=4, ensure_ascii=False)

        # 刷新内存中的 AVAILABLE_LONG_COINS 和 AVAILABLE_SHORT_COINS 变量
        # 这使得后续的 get_settings() 调用能返回最新的列表
        # 使用 global 关键字来修改全局变量
        global AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS
        AVAILABLE_LONG_COINS = sorted(pools.long_coins_pool)
        AVAILABLE_SHORT_COINS = sorted(pools.short_coins_pool)

        print(f"--- [INFO] Coin pools updated successfully. New long pool: {AVAILABLE_LONG_COINS[:5]}..., New short pool: {AVAILABLE_SHORT_COINS[:5]}... ---")
        return {"message": "Coin pools updated successfully"}
    except Exception as e:
        print(f"--- [ERROR] Failed to update coin pools: {e} ---")
        raise HTTPException(status_code=500, detail=f"Failed to update coin pools: {e}")