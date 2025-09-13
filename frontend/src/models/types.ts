export interface Position {
  symbol: string;
  full_symbol: string;
  side: 'long' | 'short';
  contracts: number;
  notional: number;
  pnl: number;
  pnl_percentage: number;
  entry_price: number;
  mark_price: number;
}

export interface LogEntry {
  message: string;
  level: 'normal' | 'info' | 'success' | 'warning' | 'error';
  timestamp: string;
}

export interface RebalancePlan {
  target_ratio_perc: number;
  positions_to_close: { symbol: string; close_value: number; close_ratio_perc: number }[];
  positions_to_open: { symbol: string; open_value: number; percentage: number }[];
  error?: string;
}

export interface UserSettings {
  leverage: number;
  total_long_position_value: number;
  total_short_position_value: number;
  long_coin_list: string[];
  short_coin_list: string[];
  long_custom_weights?: { [key: string]: number };

  rebalance_method: 'multi_factor_weakest' | 'foam';
  rebalance_top_n: number;
  rebalance_min_volume_usd: number;
  rebalance_abs_momentum_days: number;
  rebalance_rel_strength_days: number;
  rebalance_foam_days: number;

  open_maker_retries: number;
  open_order_fill_timeout_seconds: number;
  close_maker_retries: number;
  close_order_fill_timeout_seconds: number;

  enable_long_trades: boolean;
  enable_short_trades: boolean;
  enable_long_sl_tp: boolean;
  long_stop_loss_percentage: number;
  long_take_profit_percentage: number;
  enable_short_sl_tp: boolean;
  short_stop_loss_percentage: number;
  short_take_profit_percentage: number;
}
