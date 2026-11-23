# backend/app/api/protection.py
"""仓位保护（Phase 3）API：状态查询与参数热更新。"""
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from loguru import logger

from ..config import config as app_config
from ..core.security import verify_api_key
from ..protection import ledger as protection_ledger
from ..protection.service import get_protection_status, restart_protection
from ..signals.config_store import deep_merge
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
    'stop_verify_interval_sec': (0, 300, False),
    'intervention_grace_sec': (0, 300, False),
    'stop_retry_cooldown_sec': (0, 3600, False),
    'min_qty_retry_cooldown_sec': (0, 86400, False),
    'status_log_interval_sec': (0, 86400, False),
    'stop_min_update_pct': (0, 1, False),
    # ---- v2 引擎参数 ----
    'v2_poll_interval_sec': (1, 60, False),
    'v2_decision_concurrency': (1, 16, True),
    'tier_atr_buffer': (0, 10, False),
    'risk_min_pct': (0.001, 0.5, False),
    'risk_max_pct': (0.001, 0.5, False),
    # T1 距离上限（结构位太远时把第一档收回来）
    't1_max_pct': (0.005, 0.5, False),
    # 人工干预识别容差
    'entry_change_tol_pct': (0.00001, 0.05, False),
    'qty_change_tol_pct': (0.0001, 0.2, False),
    'intervention_alert_pct': (0, 1, False),
    'breakeven_trigger_atr': (0.2, 20, False),
    'breakeven_buffer_pct': (0, 0.1, False),
    'breakeven_atr_ratio': (0, 5, False),
    'profit_lock_buffer_pct': (0, 0.1, False),
    'trailing_start_atr': (0.2, 20, False),
    'trailing_atr_mult': (0.5, 20, False),
    'stop_min_room_atr': (0, 5, False),
    'stop_min_room_pct': (0, 0.1, False),
    'action_retry_cooldown_sec': (0, 3600, False),
    'tier_maker_retries': (1, 10, True),
    'tier_maker_only_until': (0, 4, True),
    'tier_marketable_retries': (0, 10, True),
    'reduce_retry_fast_sec': (1, 600, False),
    'replan_interval_sec': (0, 604800, False),
    'replan_atr_up_ratio': (1.0, 10, False),
    'replan_atr_down_ratio': (0.01, 1.0, False),
    'replan_cooldown_sec': (0, 86400, False),
    'tp_keep_ratio': (0, 0.9, False),
    # 止盈「突破确认」缓冲：0 ~ 2%（0.001 = 0.1%）
    'tp_breakout_confirm_pct': (0, 0.02, False),
    'emergency_check_interval_sec': (5, 300, False),
    'flat_confirm_sec': (0, 600, False),
}

ENGINE_VERSIONS = ('v2',)


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


def _validate_float_array(conf: Dict[str, Any], key: str, length: int,
                          parse: Callable[[Any], float] = float,
                          check: Optional[Callable[[list], Optional[str]]] = None) -> None:
    """通用数组参数校验（Extract Method：合并 4 段近似复制粘贴的校验块）。

    长度固定 + 逐元素 float 转换（parse 可顺带清洗，如钳到 0）+ 整组约束
    （check 返回错误文案或 None）；任一失败直接 400，合法值写回 conf[key]。
    """
    raw = conf.get(key)
    if raw is None:
        return
    if not isinstance(raw, (list, tuple)) or len(raw) != length:
        raise HTTPException(status_code=400, detail=f"{key} 必须是长度 {length} 的数组。")
    try:
        values = [parse(item) for item in raw]
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{key} 存在非数值元素。")
    if check is not None:
        problem = check(values)
        if problem:
            raise HTTPException(status_code=400, detail=problem)
    conf[key] = values


def _validate(conf: Dict[str, Any]) -> None:
    """校验仓位保护参数，非法值直接 400，避免写入会导致风控失灵的配置。"""
    # 布尔开关统一循环校验（替代五段复制粘贴的 isinstance 检查）
    for bool_key in ('enabled', 'dry_run', 'take_over_external_stops',
                     'replan_enabled', 'reduce_market_fallback'):
        if bool_key in conf and not isinstance(conf[bool_key], bool):
            raise HTTPException(status_code=400, detail=f"{bool_key} 必须是布尔值。")

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
    # 黑天鹅/灾难止损的判定周期同样会进 ATR 计算，写错会让阈值失衡（例如传 '60' 会被
    # ccxt 当非法周期直接抛错，引擎整轮跳过 → 等于关掉这层保护）。
    for tf_key in ('v2_timeframe', 'emergency_timeframe', 'hard_stop_timeframe'):
        value = conf.get(tf_key)
        if value is not None and value not in ALLOWED_TIMEFRAMES:
            raise HTTPException(
                status_code=400,
                detail=f"{tf_key} 必须是 {', '.join(ALLOWED_TIMEFRAMES)} 之一。")

    validate_numbers(conf, NUMERIC_RANGES)

    # v2 四档与止盈的数组参数：长度固定，否则决策层会静默退回默认值
    _validate_ratio_list(conf, 'tier_ratios', 4)
    _validate_ratio_list(conf, 'tp_ratios', 3)

    _validate_float_array(conf, 'tier_confirm_sec', 4,
                          parse=lambda x: max(0.0, float(x)))
    # A 破位深度分级：深度阈值数组（严格递增）与确认乘数数组（0~1 之间）
    _validate_float_array(
        conf, 'tier_fast_depth_atr', 3,
        check=lambda v: None if 0 < v[0] < v[1] < v[2]
        else "tier_fast_depth_atr 必须严格递增且大于 0。")
    _validate_float_array(
        conf, 'tier_fast_confirm_mult', 4,
        check=lambda v: None if all(0.0 <= x <= 1.0 for x in v)
        else "tier_fast_confirm_mult 每个乘数必须在 0~1 之间。")
    _validate_float_array(
        conf, 'tp_r_multiples', 3,
        check=lambda v: None if 0 < v[0] < v[1] < v[2]
        else "tp_r_multiples 必须严格递增且大于 0。")

    if 'risk_min_pct' in conf and 'risk_max_pct' in conf:
        if float(conf['risk_min_pct']) >= float(conf['risk_max_pct']):
            raise HTTPException(status_code=400, detail="risk_min_pct 必须小于 risk_max_pct。")
    # T1 距离上限必须落在「最小风险」与「单笔最大亏损」之间，否则四档会被挤成一条线
    if 't1_max_pct' in conf and 'risk_max_pct' in conf:
        min_pct = float(conf.get('risk_min_pct', 0.015))
        if not (min_pct < float(conf['t1_max_pct']) <= float(conf['risk_max_pct'])):
            raise HTTPException(status_code=400, detail="t1_max_pct 必须大于 risk_min_pct 且不超过 risk_max_pct。")
    if 'breakeven_trigger_atr' in conf and 'trailing_start_atr' in conf:
        if float(conf['trailing_start_atr']) < float(conf['breakeven_trigger_atr']):
            raise HTTPException(status_code=400,
                                detail="trailing_start_atr 不能小于 breakeven_trigger_atr。")


@router.get("")
def protection_status() -> Dict[str, Any]:
    """仓位保护运行状态：开关、引擎是否在跑、守卫中的仓位与风险周期状态。"""
    return get_protection_status()


@router.get("/events")
def protection_events(symbol: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    """最近保护事件（持久化台账，跨重启保留）。

    回答「这个仓位为什么没了」：cycle_new / reduce / stop（止损上移到哪）/
    exit（引擎主动全平）/ flat（仓位消失，含是否兜底单触发）/ replan / error。
    以前这些只写在 DB 里没有出口，出问题只能翻容器日志。
    """
    return {'events': protection_ledger.recent_events(limit=limit, symbol=symbol)}


@router.post("/config")
async def update_protection_config(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """增量更新仓位保护参数（深合并），保存后立即重启引擎使其生效。"""
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="配置内容必须是对象。")

    settings = app_config.load_settings()
    current = settings.get('position_protection')
    if not isinstance(current, dict):
        current = {}

    merged = deep_merge(current, payload)
    _validate(merged)

    settings['position_protection'] = merged
    if not app_config.save_settings(settings):
        raise HTTPException(status_code=500, detail="保存仓位保护配置失败，请查看服务器日志。")

    await restart_protection()
    logger.info(f"🛡️ 仓位保护配置已更新（enabled={merged.get('enabled')}）")
    return {"message": "仓位保护配置已保存", "position_protection": merged}
