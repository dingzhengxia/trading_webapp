# backend/app/models/schemas.py
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

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


# --- 交易任务请求（只保留交易执行实际使用的字段，再平衡参数走 RebalanceCriteria）---
class TradePlanRequest(BaseTaskRequest):
    leverage: int = 1
    total_long_position_value: float = 0.0
    total_short_position_value: float = 0.0
    long_coin_list: List[str] = Field(default_factory=list)
    short_coin_list: List[str] = Field(default_factory=list)
    long_custom_weights: Dict[str, float] = Field(default_factory=dict)

    open_maker_retries: int = 5
    open_order_fill_timeout_seconds: int = 60
    close_maker_retries: int = 3
    close_order_fill_timeout_seconds: int = 12

    enable_long_trades: bool = True
    enable_short_trades: bool = True
    enable_long_sl_tp: bool = True
    long_stop_loss_percentage: float = 0.0
    long_take_profit_percentage: float = 0.0
    enable_short_sl_tp: bool = True
    short_stop_loss_percentage: float = 0.0
    short_take_profit_percentage: float = 0.0

    enable_long_trailing_stop: bool = False
    long_trailing_stop_callback_rate: float = 1.0
    enable_short_trailing_stop: bool = False
    short_trailing_stop_callback_rate: float = 1.0


class SyncSltpRequest(BaseTaskRequest):
    enable_long_sl_tp: bool
    long_stop_loss_percentage: float
    long_take_profit_percentage: float
    enable_short_sl_tp: bool
    short_stop_loss_percentage: float
    short_take_profit_percentage: float

    enable_long_trailing_stop: bool = False
    long_trailing_stop_callback_rate: float = 1.0
    enable_short_trailing_stop: bool = False
    short_trailing_stop_callback_rate: float = 1.0

    leverage: int = 1


class ClosePositionRequest(BaseTaskRequest):
    full_symbol: str
    ratio: float = Field(..., gt=0, le=1.0)


class CloseBySideRequest(BaseTaskRequest):
    side: Literal['long', 'short', 'all']
    ratio: float = Field(..., gt=0, le=1.0)


class CloseMultipleRequest(BaseTaskRequest):
    full_symbols: List[str]
    ratio: float = Field(..., gt=0, le=1.0)


class ExecutionOrderItem(BaseModel):
    symbol: str
    action: Literal['CLOSE', 'OPEN']
    side: Optional[str] = None
    value_to_trade: Optional[float] = None
    close_ratio: Optional[float] = None


class ExecutionPlanRequest(BaseTaskRequest):
    orders: List[ExecutionOrderItem]


# --- 手动做多 / 做空 / 反手 ---
class ManualTradeAction(str, Enum):
    LONG = 'long'
    SHORT = 'short'
    REVERSE = 'reverse'


class ManualTradeItem(BaseModel):
    symbol: str
    action: ManualTradeAction
    value: Optional[float] = None


class ManualTradeRequest(BaseTaskRequest):
    items: List[ManualTradeItem]
    default_value: Optional[float] = None


class ResolvedSymbol(BaseModel):
    symbol: str
    full_symbol: Optional[str] = None
    quote: Optional[str] = None
    available: bool


class ResolveSymbolsResponse(BaseModel):
    symbols: List[ResolvedSymbol]


class RebalanceCriteria(BaseModel):
    method: str = "multi_factor_weakest"
    top_n: int = 50
    min_volume_usd: float = 20000000.0
    abs_momentum_days: int = 30
    rel_strength_days: int = 60
    rebalance_volume_ma_days: int = 20
    rebalance_volume_spike_ratio: float = 3.0
    rebalance_benchmark_coin: List[str] = Field(default_factory=lambda: ['BTC'])

    enable_rebalance_filters: bool = True
    rebalance_rsi_period: int = 14
    rebalance_rsi_threshold: float = 25.0
    rebalance_short_term_momentum_days: int = 3
    rebalance_short_term_momentum_threshold: float = 15.0
    rebalance_bollinger_period: int = 20
    rebalance_bollinger_std_dev: int = 2
    rebalance_bollinger_width_spike_ratio: float = 2.0

    manual_target_ratio_perc: Optional[float] = Field(None, ge=0, le=200)


class RebalancePlanResponse(BaseModel):
    target_ratio_perc: float
    positions_to_close: List[Dict[str, Any]]
    positions_to_open: List[Dict[str, Any]]
    target_coin_list: List[str]
    error: Optional[str] = None


# --- 信号扫描 / 自动开仓（Phase 2，MERGE_PLAN §6）---
SIGNAL_TIMEFRAMES = {'1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w'}
SIGNAL_STRATEGIES = {
    'ema_cross', 'ma_breakout', 'kdj_cross', 'volatility_breakout', 'level_breakout',
    'rsi_divergence', 'trend_channel_breakout', 'consecutive_candles',
    'ob_luxalgo', 'ob_fluxcharts',
}


class SignalConfigUpdate(BaseModel):
    """signal_* 配置项的部分更新模型（非法值由 API 层转 400）。"""
    signal_scan_enabled: Optional[bool] = None
    signal_scan_interval_seconds: Optional[int] = Field(None, ge=30, le=86400)
    signal_scan_static_symbols: Optional[List[str]] = Field(None, max_length=100)
    signal_scan_top_n: Optional[int] = Field(None, ge=1, le=500)
    signal_scan_timeframes: Optional[List[str]] = Field(None, min_length=1, max_length=10)
    signal_ticker_cache_seconds: Optional[int] = Field(None, ge=1, le=3600)
    signal_ohlcv_cache_seconds: Optional[int] = Field(None, ge=1, le=3600)
    signal_auto_trade_enabled: Optional[bool] = None
    signal_auto_trade_directions: Optional[List[Literal['long', 'short']]] = Field(None, max_length=2)
    signal_auto_trade_strategies: Optional[List[str]] = Field(None, min_length=1, max_length=10)
    signal_auto_trade_timeframes: Optional[List[str]] = Field(None, min_length=1, max_length=10)
    signal_auto_trade_confirmation_window_seconds: Optional[int] = Field(None, ge=1, le=86400)
    signal_auto_trade_confirmations: Optional[int] = Field(None, ge=1, le=10)
    signal_auto_trade_cooldown_seconds: Optional[int] = Field(None, ge=0, le=86400 * 7)
    signal_auto_trade_max_positions: Optional[int] = Field(None, ge=1, le=50)
    signal_auto_trade_value_usd: Optional[float] = Field(None, gt=0, le=1_000_000)
    signal_dingtalk_enabled: Optional[bool] = None
    signal_push_volume_multiplier: Optional[float] = Field(None, ge=0, le=100)
    signal_paper_enabled: Optional[bool] = None
    signal_exit_mode: Optional[Literal['percent', 'atr']] = None
    signal_paper_sl_atr: Optional[float] = Field(None, ge=0.2, le=10)
    signal_paper_tp_r: Optional[float] = Field(None, ge=0.5, le=10)
    signal_paper_max_bars: Optional[int] = Field(None, ge=1, le=100)
    signal_live_exit_timeframe: Optional[Literal['15m', '1h', '4h', '1d']] = None
    signal_live_exit_timeout_enabled: Optional[bool] = None
    signal_live_sltp_guard_enabled: Optional[bool] = None
    signal_forward_bars: Optional[List[int]] = Field(None, min_length=1, max_length=5)
