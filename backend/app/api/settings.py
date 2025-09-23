# backend/app/api/settings.py (已添加交易所校验)
from typing import Dict, Any, List

import ccxt.async_support as ccxt
from fastapi import APIRouter, Body, Depends, HTTPException, status
import json

from ..config.config import save_settings, COIN_LISTS_FILE, AVAILABLE_COINS, AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS, add_coin_to_pool
from ..core.dependencies import get_settings_dependency
from ..core.exchange_manager import get_exchange_dependency # 新增：导入交易所依赖
from ..core.security import verify_api_key
from ..logic.utils import resolve_full_symbol # 新增：导入符号解析工具
from ..models.schemas import SettingsResponse, CoinPoolsUpdate, AddCoinRequest

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
    current_settings.update(updated_settings)
    if save_settings(current_settings):
        return {"message": "Settings saved successfully"}
    return {"error": "Failed to save settings"}


@router.post("/update-coin-pools", status_code=204)
def update_coin_pools(pools: CoinPoolsUpdate):
    """更新 coin_lists.json 文件中的做多/做空币种池。"""
    global AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS

    with open(COIN_LISTS_FILE, 'w', encoding='utf-8') as f:
        data_to_save = {
            "coins_pool": AVAILABLE_COINS,
            "long_coins_pool": sorted(list(set(pools.long_coins_pool))),
            "short_coins_pool": sorted(list(set(pools.short_coins_pool)))
        }
        json.dump(data_to_save, f, indent=4, ensure_ascii=False)

    AVAILABLE_LONG_COINS = data_to_save["long_coins_pool"]
    AVAILABLE_SHORT_COINS = data_to_save["short_coins_pool"]

    print(
        f"--- [INFO] Coin pools saved successfully. Long: {len(AVAILABLE_LONG_COINS)}, Short: {len(AVAILABLE_SHORT_COINS)} ---")


# --- 核心修改：为添加币种API增加交易所校验 ---
@router.post("/add-coin", response_model=List[str])
async def add_new_coin_to_pool(
    request: AddCoinRequest,
    exchange: ccxt.binanceusdm = Depends(get_exchange_dependency) # 注入交易所实例
):
    """
    添加一个新币种到总币池 (coins_pool) 中，并先校验其在交易所的有效性。
    """
    coin_upper = request.coin.strip().upper()
    if not coin_upper:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="币种代码不能为空。")

    # 步骤1：校验币种是否存在于交易所
    if not resolve_full_symbol(exchange, coin_upper):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"在币安交易所中未找到币种 '{coin_upper}' 的有效交易对。"
        )

    # 步骤2：如果校验通过，再执行添加逻辑
    try:
        updated_pool = add_coin_to_pool(request.coin)
        return updated_pool
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"添加币种失败: {e}")
# --- 修改结束 ---