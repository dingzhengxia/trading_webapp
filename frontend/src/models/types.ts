// frontend/src/models/types.ts

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

// --- 保持 Log 接口 ---
export interface LogEntry {
  message: string;
  level: 'normal' | 'info' | 'success' | 'warning' | 'error';
  timestamp: string;
}
// --- 保持结束 ---

export interface RebalancePlan {
  target_ratio_perc: number;
  positions_to_close: { symbol: string; close_value: number; close_ratio_perc: number }[];
  positions_to_open: { symbol: string; open_value: number; percentage: number }[];
  error?: string;
}

// --- 确认 Progress 接口存在 ---
export interface Progress {
  success_count: number;
  failed_count: number;
  total: number;
  task_name: string;
  show: boolean;
  is_final: boolean;
}
// --- 确认结束 ---

export interface UserSettings {
  api_key: string;
  api_secret: string;
  use_testnet: boolean;
  enable_proxy: boolean;
  proxy_url: string;
  leverage: number;
  total_long_position_value: number;
  total_short_position_value: number;
  long_coin_list: string[]; // 保留原始列表，作为默认值
  short_coin_list: string[]; // 保留原始列表，作为默认值
  user_selected_long_coins: string[]; // 用户选择的做多列表
  user_selected_short_coins: string[]; // 用户选择的做空列表
  long_custom_weights?: { [key: string]: number };
  enable_long_trades: boolean;
  enable_short_trades: boolean;
  enable_long_sl_tp: boolean;
  long_stop_loss_percentage: number;
  long_take_profit_percentage: number;
  enable_short_sl_tp: boolean;
  short_stop_loss_percentage: number;
  short_take_profit_percentage: number;
  open_maker_retries: number;
  open_order_fill_timeout_seconds: number;
  close_maker_retries: number;
  close_order_fill_timeout_seconds: number;
  rebalance_method: 'multi_factor_weakest' | 'foam';
  rebalance_top_n: number;
  rebalance_min_volume_usd: number;
  rebalance_abs_momentum_days: number;
  rel_strength_days: number;
  rebalance_foam_days: number;
  rebalance_short_ratio_max: number;
  rebalance_short_ratio_min: number;
}

export interface CoinPools {
    all_available_coins: string[];
}

export type TradePlan = UserSettings;

export interface RebalanceCriteria {
  method: string;
  top_n: number;
  min_volume_usd: number;
  abs_momentum_days: number;
  rel_strength_days: number;
  foam_days: number;
}

export type CloseTarget =
  | { type: 'single'; position: Position }
  | { type: 'by_side'; side: 'long' | 'short' | 'all' }
  | { type: 'selected'; positions: Position[] };
