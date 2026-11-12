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
from .validators import validate_numbers

router = APIRouter(prefix="/api/settings", tags=["Settings"], dependencies=[Depends(verify_api_key)])

# 不回传明文的敏感字段
SECRET_FIELDS = ("api_key", "api_secret")
MASK_MARK = "****"

# 交易相关数值项的安全范围（下限, 上限, 是否整数）
# 这些字段直接进入下单/风控计算，接口可能被绕过前端直接调用，必须在服务端校验。
NUMERIC_RANGES: Dict[str, tuple] = {
    'leverage': (1, 125, True),
    'total_long_position_value': (0, 1e9, False),
    'total_short_position_value': (0, 1e9, False),
    'long_stop_loss_percentage': (0, 1000, False),
    'long_take_profit_percentage': (0, 1000, False),
    'short_stop_loss_percentage': (0, 1000, False),
    'short_take_profit_percentage': (0, 1000, False),
    'long_trailing_stop_callback_rate': (0.1, 20, False),
    'short_trailing_stop_callback_rate': (0.1, 20, False),
    # 重试次数的上限按“用户可能已存过更大值”放宽到 50：
    # 上限卡太死会让整包保存直接 400，连改币种这种无关改动都存不进去。
    'open_maker_retries': (0, 50, True),
    'close_maker_retries': (0, 50, True),
    'open_order_fill_timeout_seconds': (1, 600, True),
    'close_order_fill_timeout_seconds': (1, 600, True),
    'signal_auto_trade_value_usd': (1, 1e7, False),
    'signal_auto_trade_confirmations': (1, 10, True),
    'signal_auto_trade_max_positions': (1, 100, True),
    'signal_auto_trade_cooldown_seconds': (0, 86400, True),
    'signal_scan_interval_seconds': (30, 86400, True),
    # R-P0-2 / R-P1-5 / R-P1-2 新配置范围（越界 400）
    'close_price_chase_ticks': (0, 10, True),
    # --- api_* 限流参数（RestGuardian 热更新）---
    'api_max_concurrency': (1, 20, True),
    'api_min_interval_sec': (0, 5, False),
    'api_max_retries': (1, 10, True),
    'api_failure_threshold': (1, 50, True),
    'api_circuit_breaker_cooldown_sec': (1, 3600, True),
    'api_418_cooldown_sec': (1, 3600, True),
    'api_429_base_backoff_sec': (0.2, 60, False),
    'api_429_max_backoff_sec': (0.2, 600, False),
}

# 枚举型配置的合法取值（非法值 400）
CHOICE_SETTINGS: Dict[str, tuple] = {
    'unprotected_position_action': ('auto_close', 'keep_alert'),
}


def _validate_numeric_settings(updated: Dict[str, Any]) -> None:
    """校验交易安全相关数值；非法值返回 400，避免 "" / 0 杠杆等写入数据库。"""
    validate_numbers(updated, NUMERIC_RANGES)
    for field, allowed in CHOICE_SETTINGS.items():
        if field in updated and str(updated[field]) not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field} 必须是 {allowed} 之一。",
            )


def _mask_secret(value: Any) -> str:
    """掩码展示密钥：保留首尾各 4 位，便于用户确认是哪一把 Key。"""
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 8:
        return MASK_MARK
    return f"{text[:4]}{MASK_MARK}{text[-4:]}"


def _masked_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    masked = dict(settings)
    for field in SECRET_FIELDS:
        if masked.get(field):
            masked[field] = _mask_secret(masked[field])
    return masked


@router.get("", response_model=SettingsResponse)
def get_settings(settings: Dict[str, Any] = Depends(get_settings_dependency)):
    """获取所有用户配置和可选币种列表（交易所密钥以掩码返回，不回传明文）。"""
    return {
        "user_settings": _masked_settings(settings),
        "available_coins": app_config.AVAILABLE_COINS,
        "available_long_coins": app_config.AVAILABLE_LONG_COINS,
        "available_short_coins": app_config.AVAILABLE_SHORT_COINS,
    }


@router.post("")
def update_settings(
        updated_settings: Dict[str, Any] = Body(...),
        current_settings: Dict[str, Any] = Depends(get_settings_dependency)
):
    """保存用户配置到 SQLite。

    掩码值（含 ****）视为“未修改”，保持原密钥不变，避免前端回写掩码覆盖真实 Key。
    """
    for field in SECRET_FIELDS:
        value = updated_settings.get(field)
        if isinstance(value, str) and MASK_MARK in value:
            updated_settings.pop(field, None)

    # 非法值直接 400：避免 "" / 0 杠杆等直接进入下单与风控计算
    _validate_numeric_settings(updated_settings)

    current_settings.update(updated_settings)
    if app_config.save_settings(current_settings):
        # R-P1-2 配置热更新：api_* 限流参数保存后立即生效，无需重启
        try:
            from ..core.rest_guardian import DEFAULT_API_LIMIT, shared_guardian

            api_conf = {k: current_settings[k] for k in DEFAULT_API_LIMIT
                        if k in current_settings}
            shared_guardian().configure(api_conf)
        except Exception:  # noqa: BLE001 - 热更新失败不影响保存结果（下次重启生效）
            pass
        return {"message": "Settings saved successfully"}
    raise HTTPException(status_code=500, detail="保存配置失败，请查看服务器日志。")


@router.post("/update-coin-pools", status_code=204)
def update_coin_pools(pools: CoinPoolsUpdate):
    """更新做多/做空币种池（SQLite coin_pools 表）。

    统一走 config.save_coin_pools()：加锁写入 + 同步刷新内存全局变量，
    避免绕过锁直接写存储导致内存与存储不一致。
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
