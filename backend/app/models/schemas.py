# backend/app/models/schemas.py (最终完整正确版)
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field


class SettingsResponse(BaseModel):
    user_settings: Dict[str, Any]
    available_coins: List[str]
    available_long_coins: List[str]
    available_short_coins: List[str]


class CoinPoolsUpdate(BaseModel):
    long_coins_pool: List[str]
    short_coins_pool: List[str]


class AddCoinRequest(BaseModel):
    coin: str


class Position(BaseModel):
    symbol: str
    full_symbol: str
    side: str
    contracts: float
    notional: float
    pnl: float
    pnl_percentage: float
    entry_price: float
    mark_price: float


class BaseTaskRequest(BaseModel):
    request_id: Optional[str] = None


class TradePlanRequest(BaseTaskRequest):
    leverage: int
    total_long_position_value: float
    total_short_position_value: float
    long_coin_list: List[str]
    short_coin_list: List[str]
    long_custom_weights: Dict[str, float]
    open_maker_retries: int
    open_order_fill_timeout_seconds: int
    close_maker_retries: int
    close_order_fill_timeout_seconds: int
    enable_long_trades: bool
    enable_short_trades: bool
    enable_long_sl_tp: bool
    long_stop_loss_percentage: float
    long_take_profit_percentage: float
    enable_short_sl_tp: bool
    short_stop_loss_percentage: float
    short_take_profit_percentage: float


class SyncSltpRequest(BaseTaskRequest):
    enable_long_sl_tp: bool
    long_stop_loss_percentage: float
    long_take_profit_percentage: float
    enable_short_sl_tp: bool
    short_stop_loss_percentage: float
    short_take_profit_percentage: float
    leverage: int


class ClosePositionRequest(BaseTaskRequest):
    full_symbol: str
    ratio: float = Field(..., gt=0, le=1.0)


class CloseBySideRequest(BaseModel):
    side: str
    ratio: float = Field(..., gt=0, le=1.0)


class CloseMultipleRequest(BaseTaskRequest):
    full_symbols: List[str]
    ratio: float = Field(..., gt=0, le=1.0)


class ExecutionOrderItem(BaseModel):
    symbol: str
    action: str
    side: str
    value_to_trade: Optional[float] = None
    close_ratio: Optional[float] = None


class ExecutionPlanRequest(BaseTaskRequest):
    orders: List[ExecutionOrderItem]


# --- 核心修正：恢复并包含了所有字段，并加上默认值 ---
class RebalanceCriteria(BaseModel):
    method: str
    top_n: int
    # --- ！！！确保这个字段存在 ！！！ ---
    min_volume_usd: float
    # --- ！！！ ---
    abs_momentum_days: int
    rel_strength_days: int
    foam_days: int
    rebalance_volume_ma_days: int
    rebalance_volume_spike_ratio: float
    rebalance_benchmark_coin: List[str]

    enable_rebalance_filters: bool
    rebalance_rsi_period: int
    rebalance_rsi_threshold: float
    rebalance_short_term_momentum_days: int
    rebalance_short_term_momentum_threshold: float
    rebalance_bollinger_period: int
    rebalance_bollinger_std_dev: int
    rebalance_bollinger_width_spike_ratio: float


class RebalancePlanRequest(BaseModel):
    criteria: RebalanceCriteria
    custom_target_short_value: Optional[float] = None


class RebalancePlanResponse(BaseModel):
    target_ratio_perc: float
    positions_to_close: List[Dict[str, Any]]
    positions_to_open: List[Dict[str, Any]]
    error: Optional[str] = None