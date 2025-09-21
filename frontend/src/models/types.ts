// frontend/src/models/types.ts (完整代码)
export interface Position {
  symbol: string
  full_symbol: string
  side: 'long' | 'short'
  contracts: number
  notional: number
  pnl: number
  pnl_percentage: number
  entry_price: number
  mark_price: number
}

export interface Log {
  message: string
  level: 'normal' | 'info' | 'success' | 'warning' | 'error'
  timestamp: string
}

export interface RebalancePlan {
  target_ratio_perc: number
  positions_to_close: {
    symbol: string
    notional: number
    close_value: number
    close_ratio_perc: number
    close_ratio: number
  }[]
  positions_to_open: {
    symbol: string
    open_value: number
    percentage: number
  }[]
  error?: string
}

export interface ProgressState {
  success_count: number
  failed_count: number
  total: number
  task_name: string
  show: boolean
  is_final: boolean
}

export interface UserSettings {
  api_key: string
  api_secret: string
  use_testnet: boolean
  enable_proxy: boolean
  proxy_url: string
  leverage: number
  total_long_position_value: number
  total_short_position_value: number
  long_coin_list: string[]
  short_coin_list: string[]
  long_custom_weights?: { [key: string]: number }
  enable_long_trades: boolean
  enable_short_trades: boolean
  enable_long_sl_tp: boolean
  long_stop_loss_percentage: number
  long_take_profit_percentage: number
  enable_short_sl_tp: boolean
  short_stop_loss_percentage: number
  short_take_profit_percentage: number
  open_maker_retries: number
  open_order_fill_timeout_seconds: number
  close_maker_retries: number
  close_order_fill_timeout_seconds: number
  rebalance_method: 'multi_factor_weakest' | 'foam'
  rebalance_top_n: number
  rebalance_min_volume_usd: number
  rebalance_abs_momentum_days: number
  rebalance_rel_strength_days: number
  rebalance_foam_days: number
  // --- 新增字段 ---
  rebalance_volume_ma_days: number
  rebalance_volume_spike_ratio: number
}

export interface RebalanceCriteria {
  method: string
  top_n: number
  min_volume_usd: number
  abs_momentum_days: number
  rel_strength_days: number
  foam_days: number
  // --- 新增字段 ---
  rebalance_volume_ma_days: number
  rebalance_volume_spike_ratio: number
}
