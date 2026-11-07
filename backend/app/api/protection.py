# backend/app/api/protection.py
"""仓位保护（Phase 3）API：状态查询与参数热更新。"""
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException
from loguru import logger

from ..config import config as app_config
from ..core.security import verify_api_key
from ..protection.service import get_protection_status, restart_protection
from .validators import validate_numbers

router = APIRouter(prefix="/api/protection", tags=["Protection"],
                   dependencies=[Depends(verify_api_key)])

# 允许的时间框架（用于 T1/T2/T3 结构判定）
ALLOWED_TIMEFRAMES = ('15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d')

# 数值范围（下限, 上限, 是否整数）——这些直接进入风控计算，必须服务端校验
NUMERIC_RANGES: Dict[str, tuple] = {
    'tp1_r_multiple': (0.1, 100, False),
    'tp2_r_multiple': (0.1, 100, False),
    'tp3_r_multiple': (0.1, 100, False),
    'tp1_ratio': (0.01, 1, False),
    'tp2_ratio': (0.01, 1, False),
    'tier1_ratio': (0.01, 1, False),
    'tier2_ratio': (0.01, 1, False),
    'profit_protection_trigger_r': (0.1, 100, False),
    'structure_lookback': (2, 500, True),
    't1_structure_lookback': (2, 500, True),
    't2_structure_lookback': (2, 500, True),
    't3_structure_lookback': (2, 500, True),
    'entry_classification_lookback_bars': (10, 2000, True),
    'ema_fast_period': (2, 500, True),
    'ema_slow_period': (2, 1000, True),
    'ma_atr_period': (2, 200, True),
    'structure_buffer_atr': (0, 10, False),
    't1_atr_confirmation': (0, 10, False),
    't2_atr_confirmation': (0, 10, False),
    't3_atr_confirmation': (0, 10, False),
    'emergency_atr_multiplier': (0.5, 20, False),
    'emergency_structure_lookback': (1, 500, True),
    'hard_stop_atr_multiplier': (0.5, 50, False),
    'hard_stop_min_distance_pct': (0, 1, False),
    'dynamic_stop_max_distance_pct': (0, 1, False),
    'stop_maintenance_interval_sec': (1, 300, False),
    'stop_min_update_pct': (0, 1, False),
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _validate(conf: Dict[str, Any]) -> None:
    """校验仓位保护参数，非法值直接 400，避免写入会导致风控失灵的配置。"""
    if 'enabled' in conf and not isinstance(conf['enabled'], bool):
        raise HTTPException(status_code=400, detail="enabled 必须是布尔值。")

    timeframe = conf.get('timeframe')
    if timeframe is not None and timeframe not in ALLOWED_TIMEFRAMES:
        raise HTTPException(
            status_code=400,
            detail=f"timeframe 必须是 {', '.join(ALLOWED_TIMEFRAMES)} 之一。")

    validate_numbers(conf, NUMERIC_RANGES)


@router.get("")
def protection_status() -> Dict[str, Any]:
    """仓位保护运行状态：开关、引擎是否在跑、守卫中的仓位与风险周期状态。"""
    return get_protection_status()


@router.post("/config")
async def update_protection_config(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """增量更新仓位保护参数（深合并），保存后立即重启引擎使其生效。"""
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="配置内容必须是对象。")

    settings = app_config.load_settings()
    current = settings.get('position_protection')
    if not isinstance(current, dict):
        current = {}

    merged = _deep_merge(current, payload)
    _validate(merged)

    settings['position_protection'] = merged
    if not app_config.save_settings(settings):
        raise HTTPException(status_code=500, detail="保存仓位保护配置失败，请查看服务器日志。")

    await restart_protection()
    logger.info(f"🛡️ 仓位保护配置已更新（enabled={merged.get('enabled')}）")
    return {"message": "仓位保护配置已保存", "position_protection": merged}
