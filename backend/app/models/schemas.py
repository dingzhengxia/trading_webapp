# backend/app/models/schemas.py (最终修正版)
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
    rebalance_method: str
    rebalance_top_n: int
    rebalance_min_volume_usd: float
    rebalance_abs_momentum_days: int
    rebalance_rel_strength_days: int
    rebalance_foam_days: int
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


class CloseBySideRequest(BaseTaskRequest):
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


# --- 核心修正：将所有新参数添加到 RebalanceCriteria 模型 ---
class RebalanceCriteria(BaseModel):
    method: str = "multi_factor_weakest"
    top_n: int = 50
    min_volume_usd: float = 20000000.0
    abs_momentum_days: int = 30
    rel_strength_days: int = 60
    foam_days: int = 1
    rebalance_volume_ma_days: int = 20
    rebalance_volume_spike_ratio: float = 3.0
    rebalance_benchmark_coin: List[str] = ['BTC']

    enable_rebalance_filters: bool = True
    rebalance_rsi_period: int = 14
    rebalance_rsi_threshold: float = 25.0
    rebalance_short_term_momentum_days: int = 3
    rebalance_short_term_momentum_threshold: float = 15.0
    rebalance_bollinger_period: int = 20
    rebalance_bollinger_std_dev: int = 2
    rebalance_bollinger_width_spike_ratio: float = 2.0

    # 新增字段：允许前端传入手动设置的目标比例
    manual_target_ratio_perc: Optional[float] = Field(None, ge=0, le=200)

class RebalancePlanResponse(BaseModel):
    target_ratio_perc: float
    positions_to_close: List[Dict[str, Any]]
    positions_to_open: List[Dict[str, Any]]
    target_coin_list: List[str]  # <--- 新增此字段
    error: Optional[str] = None