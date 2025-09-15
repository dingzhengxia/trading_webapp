// 文件路径: frontend/src/models/types.ts

// Position 接口保持不变，它是正确的
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

// --- 修改: 将 LogEntry 重命名为 Log ---
// 这将匹配 TradingView.vue 中的导入和使用
export interface Log {
  message: string;
  level: 'normal' | 'info' | 'success' | 'warning' | 'error';
  timestamp: string;
}

// RebalancePlan 接口保持不变，它是正确的
export interface RebalancePlan {
  target_ratio_perc: number;
  positions_to_close: { symbol: string; close_value: number; close_ratio_perc: number }[];
  positions_to_open: { symbol: string; open_value: number; percentage: number }[];
  error?: string;
}

// --- 添加: 缺失的 Progress 接口 ---
// 这个类型用于驱动进度条组件
export interface Progress {
  visible: boolean;
  current: number;
  total: number;
  task_name: string;
}

// UserSettings 接口保持不变，它是正确的
export interface UserSettings {
  api_key: string;
  api_secret: string;
  use_testnet: boolean;
  enable_proxy: boolean;
  proxy_url: string;
  leverage: number;
  total_long_position_value: number;
  total_short_position_value: number;
  long_coin_list: string[];
  short_coin_list: string[];
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

// --- 添加: 缺失的 TradePlan 和 RebalanceCriteria 接口 ---
// 尽管 UserSettings 包含了所有字段，但为 API 调用定义精确的类型是更好的做法
export type TradePlan = UserSettings;

export interface RebalanceCriteria {
  method: string;
  top_n: number;
  min_volume_usd: number;
  abs_momentum_days: number;
  rel_strength_days: number;
  foam_days: number;
}
