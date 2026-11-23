"""Binance USD-M Futures 仓位保护的 facade（Phase 3）。

v1 轮询主循环（每仓一个 watch_symbol_position 协程 + protect_positions_main）已下线：
protection/service.py 固定使用 v2 引擎（runner.protect_positions_main_v2），
配置键 engine_version 只接受 "v2"。

Phase 3 T08 把实现拆分为职责模块，本文件仅做 re-export facade，维持既有
``from .engine import x`` / ``engine.x`` 导入不变。模块归属：config=配置深合并；
state=状态持久化/Runtime/动作锁/reconcile；market_data=K线/ATR/EMA/黑天鹅行情；
stops=止损判定；take_profit=TP 阶梯；exits=应急减仓/市价单（静态审计白名单）+ 交易所 STOP 管理。
"""
import time  # noqa: F401  既有调用方/测试通过 engine.time 使用

from loguru import logger  # noqa: F401  既有调用方/测试通过 engine.logger 使用

from .config import DEFAULT_CONFIG, _f, load_protection_config  # noqa: F401
from .exits import (  # noqa: F401  facade re-export
    CLIENT_ALGO_PREFIX, LAST_STOP_MAINTAIN_TIME, LAST_STOP_ORDER_TIME,
    _algo_methods, _algo_status, _algo_trigger, _cancel_algo,
    _cancel_bot_reduce_orders, _cancel_program_stops_for_flat, _cancel_stop_orders,
    _create_full_close_stop, _create_lot_stop, _ensure_disaster_stop, _find_stop_orders,
    _full_exit_with_revalidation, _get_open_algo_orders, _is_program_stop,
    _limit_reduce_with_maker_retry, _make_client_algo_id, _market_reduce_and_confirm,
    _take_over_external_stops,
)
from .market_data import (  # noqa: F401  facade re-export
    _atr_from_df, _atr_from_rows, _closed_atr, _closed_df, _ema_structure_from_rows,
    _ema_value, _emergency_signal, _fetch_ohlcv, _fetch_positions, _fetch_ticker,
    _market_snapshot, _position_fresh, _two_source_price_ok,
)
from .state import (  # noqa: F401  facade re-export
    LAST_RISK_ACTION_TS, RUNTIME, Runtime, _ACTION_EXECUTION_LOCK, _STATUS_LOG_LAST,
    _load_state, _mark_risk_action_done, _position_open_time_ms, _position_side,
    _position_size, _raw_position_side, _reconcile_position_state, _rest,
    _risk_action_lock_key, _risk_action_on_cooldown, _save_state, _state_key,
    _status_log, _try_lock_risk_action,
)
from .stops import (  # noqa: F401  facade re-export
    _calculate_disaster_stop, _calculate_dynamic_protection_stop,
    _strategy_levels_from_rows,
)
from .take_profit import (  # noqa: F401  facade re-export
    _initialize_take_profit_levels, _take_profit_hit, _take_profit_protection_stop,
    _tp3_action_text, _tp3_remaining_ratio,
)
