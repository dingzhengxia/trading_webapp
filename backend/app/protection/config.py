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
 'tier_ratios': [0.15, 0.20, 0.25, 0.40],
 'tier_confirm_sec': [30, 45, 60, 0],
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
 'tier1_ratio': 0.2,
 'tier2_ratio': 0.3,
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
    return {"position_protection": deep_merge(
        DEFAULT_CONFIG["position_protection"], stored)}
