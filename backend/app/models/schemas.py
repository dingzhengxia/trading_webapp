from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


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

    class Config:
        from_attributes = True


class TradePlanRequest(BaseModel):
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


class RebalanceCriteria(BaseModel):
    method: str = "multi_factor_weakest"
    top_n: int = 50
    min_volume_usd: float = 20000000.0
    abs_momentum_days: int = 30
    rel_strength_days: int = 60
    foam_days: int = 1


class RebalancePlanResponse(BaseModel):
    target_ratio_perc: float
    positions_to_close: List[Dict[str, Any]]
    positions_to_open: List[Dict[str, Any]]
    error: Optional[str] = None


class ClosePositionRequest(BaseModel):
    full_symbol: str
    ratio: float = Field(..., gt=0, le=1.0)


class CloseBySideRequest(BaseModel):
    side: str
    ratio: float = Field(..., gt=0, le=1.0)


class CloseMultipleRequest(BaseModel):
    full_symbols: List[str]
    ratio: float = Field(..., gt=0, le=1.0)