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
    'trailing_trigger_r': (0.1, 100, False),
    'trailing_atr_multiple': (0.5, 20, False),
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
    'status_log_interval_sec': (0, 86400, False),
    'stop_min_update_pct': (0, 1, False),
    # ---- v2 引擎参数 ----
    'v2_poll_interval_sec': (1, 60, False),
    'v2_decision_concurrency': (1, 16, True),
    'tier_atr_buffer': (0, 10, False),
    'tier_min_gap_atr': (0.1, 10, False),
    'risk_min_pct': (0.001, 0.5, False),
    'risk_max_pct': (0.001, 0.5, False),
    'disaster_atr_buffer': (0, 20, False),
    'breakeven_trigger_r': (0.1, 100, False),
    'breakeven_buffer_pct': (0, 0.1, False),
    'profit_lock_buffer_pct': (0, 0.1, False),
    'trailing_start_r': (0, 100, False),
    'trailing_atr_mult': (0.5, 20, False),
    'action_retry_cooldown_sec': (0, 3600, False),
    'tier_maker_retries': (1, 10, True),
    'tier_maker_only_until': (0, 4, True),
    'tp_keep_ratio': (0, 0.9, False),
    'emergency_check_interval_sec': (5, 300, False),
    'flat_confirm_sec': (0, 600, False),
}

ENGINE_VERSIONS = ('v1', 'v2')


def _validate_ratio_list(conf: Dict[str, Any], key: str, length: int,
                         allow_zero: bool = True) -> None:
    """校验比例数组：长度固定、全为数值、非负、合计 > 0。"""
    if key not in conf:
        return
    raw = conf[key]
    if not isinstance(raw, (list, tuple)) or len(raw) != length:
        raise HTTPException(status_code=400, detail=f"配置项 {key} 必须是长度 {length} 的数组。")
    values = []
    for item in raw:
        try:
            value = float(item)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"配置项 {key} 存在非数值元素。")
        if value < 0 or (not allow_zero and value == 0):
            raise HTTPException(status_code=400, detail=f"配置项 {key} 的元素不能为负。")
        if value > 1:
            raise HTTPException(status_code=400, detail=f"配置项 {key} 的元素必须在 0~1 之间。")
        values.append(value)
    if sum(values) <= 0:
        raise HTTPException(status_code=400, detail=f"配置项 {key} 合计必须大于 0。")
    conf[key] = values


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
    if 'dry_run' in conf and not isinstance(conf['dry_run'], bool):
        raise HTTPException(status_code=400, detail="dry_run 必须是布尔值。")
    if 'take_over_external_stops' in conf and not isinstance(conf['take_over_external_stops'], bool):
        raise HTTPException(status_code=400, detail="take_over_external_stops 必须是布尔值。")

    mode = conf.get('trailing_stop_mode')
    if mode is not None and str(mode).lower() not in ('step', 'continuous'):
        raise HTTPException(status_code=400, detail="trailing_stop_mode 必须是 step 或 continuous。")

    version = conf.get('engine_version')
    if version is not None and str(version).lower() not in ENGINE_VERSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"engine_version 必须是 {', '.join(ENGINE_VERSIONS)} 之一。")

    timeframe = conf.get('timeframe')
    if timeframe is not None and timeframe not in ALLOWED_TIMEFRAMES:
        raise HTTPException(
            status_code=400,
            detail=f"timeframe 必须是 {', '.join(ALLOWED_TIMEFRAMES)} 之一。")
    v2_timeframe = conf.get('v2_timeframe')
    if v2_timeframe is not None and v2_timeframe not in ALLOWED_TIMEFRAMES:
        raise HTTPException(
            status_code=400,
            detail=f"v2_timeframe 必须是 {', '.join(ALLOWED_TIMEFRAMES)} 之一。")

    validate_numbers(conf, NUMERIC_RANGES)

    # v2 四档与止盈的数组参数：长度固定，否则决策层会静默退回默认值
    _validate_ratio_list(conf, 'tier_ratios', 4)
    _validate_ratio_list(conf, 'tp_ratios', 3)

    confirm = conf.get('tier_confirm_sec')
    if confirm is not None:
        if not isinstance(confirm, (list, tuple)) or len(confirm) != 4:
            raise HTTPException(status_code=400, detail="tier_confirm_sec 必须是长度 4 的数组。")
        try:
            conf['tier_confirm_sec'] = [max(0.0, float(x)) for x in confirm]
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="tier_confirm_sec 存在非数值元素。")

    mults = conf.get('tp_r_multiples')
    if mults is not None:
        if not isinstance(mults, (list, tuple)) or len(mults) != 3:
            raise HTTPException(status_code=400, detail="tp_r_multiples 必须是长度 3 的数组。")
        try:
            values = [float(x) for x in mults]
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="tp_r_multiples 存在非数值元素。")
        if not (0 < values[0] < values[1] < values[2]):
            raise HTTPException(status_code=400, detail="tp_r_multiples 必须严格递增且大于 0。")
        conf['tp_r_multiples'] = values

    if 'risk_min_pct' in conf and 'risk_max_pct' in conf:
        if float(conf['risk_min_pct']) >= float(conf['risk_max_pct']):
            raise HTTPException(status_code=400, detail="risk_min_pct 必须小于 risk_max_pct。")


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
