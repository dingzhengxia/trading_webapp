"""仓位保护配置：DEFAULT_CONFIG + SQLite 覆盖深合并（Phase 3 T08 自 engine.py 拆出）。

配置统一走 signals/config_store.deep_merge 的递归合并模式：
DEFAULT_CONFIG 为 base，SQLite settings 的 position_protection 为 patch，
旧存量配置缺少的新字段自动使用默认值。
"""

from loguru import logger

from ..config.config import load_settings
from ..signals.config_store import deep_merge

DEFAULT_CONFIG = {
    # 并入 WebApp 后默认关闭：只有前端「仓位保护」页打开开关才会轮询交易所
    "position_protection": {'enabled': False,
 'engine_version': 'v2',
 'dry_run': False,
 'v2_timeframe': '2h',
 'v2_poll_interval_sec': 3.0,
     'tier_ratios': [0.15, 0.20, 0.25, 0.40],  # v2 实验引擎专用（risk_model/runner），当前主循环 engine.py 未引用
     'tier_confirm_sec': [30, 45, 60, 0],  # 同上，v2 四档确认秒，主循环未引用
 'timeframe': '2h',
 'ema_fast_period': 26,
 'ema_slow_period': 83,
 'structure_lookback': 12,
 'structure_buffer_atr': 0.5,
 't1_structure_lookback': 7,
 't1_atr_confirmation': 0.5,
 't2_structure_lookback': 26,
 't2_atr_confirmation': 0.5,
 't3_structure_lookback': 83,
 'entry_classification_lookback_bars': 500,
 'take_profit_enabled': True,
 'tp1_r_multiple': 1.0,
 'tp2_r_multiple': 2.0,
 'tp3_r_multiple': 3.0,
 'tp1_ratio': 0.2,
 'tp2_ratio': 0.3,
 'tp3_ratio': None,
 'tp_maker_only': True,
 'tp_limit_max_retries': 0,
 'tp_limit_timeout_sec': 10.0,
 'tp_limit_check_interval_sec': 1.0,
 'tp_breakeven_buffer_pct': 0.002,
 'tp_profit_lock_buffer_pct': 0.001,
 'profit_protection_enabled': True,
 'profit_protection_trigger_r': 0.5,
 # 双轨治理：True 时守护端接管（撤销）开仓端遗留的 SL/TP/TS 条件单，止损止盈由守护端独家管理。
 'take_over_external_stops': False,
 # 连续移动止损：'step'=阶梯跳（现状）| 'continuous'=浮盈达到 trailing_trigger_r 后按 ATR 平滑追踪。
 'trailing_stop_mode': 'step',
 'trailing_trigger_r': 1.0,
 'trailing_atr_multiple': 2.0,
     # T1/T2 分级减仓比例已收敛为沿用 tp1_ratio/tp2_ratio（见 load_protection_config），
     # 不再单独维护，避免两套减仓比例配置漂移。
 'ma_atr_period': 14,
 'emergency_enabled': True,
 'emergency_timeframe': '15m',
 'emergency_atr_period': 14,
 'emergency_atr_multiplier': 3.0,
 'emergency_structure_lookback': 4,
 'exchange_hard_stop_enabled': True,
 'hard_stop_timeframe': '1h',
 'hard_stop_atr_period': 14,
 'hard_stop_min_distance_pct': 0.05,
 'hard_stop_atr_multiplier': 6.0,
 'dynamic_stop_max_distance_pct': 0.12,
 'positions_cache_ttl_sec': 5.0,
 'ticker_cache_ttl_sec': 3.0,
 'orders_cache_ttl_sec': 10.0,
 'ohlcv_cache_ttl_sec': 30.0,
 'api_max_retries': 5,
 'api_failure_threshold': 5,
 'api_circuit_breaker_cooldown_sec': 30,
 'api_min_interval_sec': 0.08,
 'api_429_base_backoff_sec': 2.0,
 'api_418_cooldown_sec': 60.0,
 'stop_maintenance_interval_sec': 5.0,
 'stop_min_update_pct': 0.0005,
 'stop_min_update_atr_ratio': 0.05,
 'price_source_tolerance_pct': 0.01,
 'risk_action_min_interval_sec': 1800.0,
 'identity_grace_after_reduce_sec': 900.0,
 'flat_confirm_sec': 30.0,
 'status_log_interval_sec': 900.0}
}


def _f(value, default=None):
    """宽松转 float：None/非法值返回 default。"""
    try:
        return default if value is None else float(value)
    except (TypeError, ValueError):
        return default


def load_protection_config():
    """读取仓位保护配置：DEFAULT_CONFIG 与 SQLite 中的用户覆盖值深合并。"""
    try:
        stored = load_settings().get("position_protection")
    except Exception as exc:
        logger.warning(f"读取仓位保护配置失败，使用默认值: {exc}")
        stored = None
    merged = deep_merge(DEFAULT_CONFIG["position_protection"], stored)
    # 收敛：T1/T2 分级减仓比例默认沿用 tp1_ratio/tp2_ratio，不再单独维护。
    # 若用户显式设置 tier1_ratio/tier2_ratio（旧习惯），仍以它为准。
    for tier, tp in (("tier1_ratio", "tp1_ratio"), ("tier2_ratio", "tp2_ratio")):
        if merged.get(tier) is None:
            merged[tier] = merged.get(tp)
    return {"position_protection": merged}
