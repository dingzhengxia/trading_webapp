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

export interface Log {
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

export interface Progress {
  success_count: number;
  failed_count: number;
  total: number;
  task_name: string;
  show: boolean;
  is_final: boolean;
}

export interface UserSettings {
  api_key: string;
  api_secret: string;
  use_testnet: boolean;
  enable_proxy: boolean;
  proxy_url: string;
  leverage: number;
  total_long_position_value: number;
  total_short_position_value: number;
  // --- 修改：改为用户选择的列表 ---
  user_selected_long_coins: string[];
  user_selected_short_coins: string[];
  // --- 修改结束 ---
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
  rel_strength_days: number; // 保持后端命名
  rebalance_foam_days: number;
  rebalance_short_ratio_max: number;
  rebalance_short_ratio_min: number;
}

// --- 新增 CoinPools 接口 ---
export interface CoinPools {
    all_available_coins: string[];
}
// --- 新增结束 ---

export type TradePlan = UserSettings;

export interface RebalanceCriteria {
  method: string;
  top_n: number;
  min_volume_usd: number;
  abs_momentum_days: number;
  rel_strength_days: number;
  foam_days: number;
}

// --- 新增 CloseTarget 的定义 ---
export type CloseTarget =
  | { type: 'single'; position: Position }
  | { type: 'by_side'; side: 'long' | 'short' | 'all' }
  | { type: 'selected'; positions: Position[] };
// --- 新增结束 ---
