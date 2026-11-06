# backend/app/api/settings.py
from typing import Any, Dict, List

import ccxt.async_support as ccxt
from fastapi import APIRouter, Body, Depends, HTTPException, status

from ..config import config as app_config
from ..core.dependencies import get_settings_dependency
from ..core.exchange_manager import get_exchange_dependency
from ..core.security import verify_api_key
from ..logic.utils import resolve_full_symbol
from ..models.schemas import AddCoinRequest, CoinPoolsUpdate, SettingsResponse

router = APIRouter(prefix="/api/settings", tags=["Settings"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=SettingsResponse)
def get_settings(settings: Dict[str, Any] = Depends(get_settings_dependency)):
    """获取所有用户配置和可选币种列表。"""
    return {
        "user_settings": settings,
        "available_coins": app_config.AVAILABLE_COINS,
        "available_long_coins": app_config.AVAILABLE_LONG_COINS,
        "available_short_coins": app_config.AVAILABLE_SHORT_COINS,
    }


@router.post("")
def update_settings(
        updated_settings: Dict[str, Any] = Body(...),
        current_settings: Dict[str, Any] = Depends(get_settings_dependency)
):
    """保存用户配置到 user_settings.json 文件。"""
    current_settings.update(updated_settings)
    if app_config.save_settings(current_settings):
        return {"message": "Settings saved successfully"}
    return {"error": "Failed to save settings"}


@router.post("/update-coin-pools", status_code=204)
def update_coin_pools(pools: CoinPoolsUpdate):
    """更新 coin_lists.json 文件中的做多/做空币种池。

    统一走 config.save_coin_pools()：加锁写文件 + 同步刷新内存全局变量，
    避免绕过锁直接写文件导致内存与文件不一致。
    """
    app_config.save_coin_pools(pools.long_coins_pool, pools.short_coins_pool)


@router.post("/add-coin", response_model=List[str])
async def add_new_coin_to_pool(
        request: AddCoinRequest,
        exchange: ccxt.binanceusdm = Depends(get_exchange_dependency)
):
    """添加一个新币种到总币池 (coins_pool)，并先校验其在交易所的有效性。"""
    coin_upper = request.coin.strip().upper()
    if not coin_upper:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="币种代码不能为空。")

    if not resolve_full_symbol(exchange, coin_upper):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"在币安交易所中未找到币种 '{coin_upper}' 的有效交易对。"
        )

    try:
        return app_config.add_coin_to_pool(request.coin)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"添加币种失败: {e}")
