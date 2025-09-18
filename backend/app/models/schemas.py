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
    # 这个模型包含了所有可能的设置字段
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
    # 新增的成交量字段也应包含
    rebalance_volume_ma_days: int
    rebalance_volume_spike_ratio: float


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

# --- 核心修复在这里 ---
class RebalanceCriteria(BaseModel):
    method: str = "multi_factor_weakest"
    top_n: int = 50
    min_volume_usd: float = 20000000.0
    abs_momentum_days: int = 30
    rel_strength_days: int = 60
    foam_days: int = 1
    # 新增的字段必须在这里定义，FastAPI才能正确解析它们
    rebalance_volume_ma_days: int = 20
    rebalance_volume_spike_ratio: float = 3.0

class RebalancePlanResponse(BaseModel):
    target_ratio_perc: float
    positions_to_close: List[Dict[str, Any]]
    positions_to_open: List[Dict[str, Any]]
    error: Optional[str] = None