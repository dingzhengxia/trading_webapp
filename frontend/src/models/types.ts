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

export interface LogEntry {
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
  target_coin_list: string[]
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

// --- 手动交易（做多/做空/反手）相关类型 ---
export type ManualTradeAction = 'long' | 'short' | 'reverse'

export interface ManualTradeItem {
  symbol: string
  action: ManualTradeAction
  value: number
}

export interface ResolvedSymbol {
  symbol: string
  full_symbol: string | null
  quote: string | null
  available: boolean
}

export interface ResolveSymbolsResponse {
  symbols: ResolvedSymbol[]
}

// 手动交易页持久化预设（保存在后端 settings 中）
export interface ManualTradePreset {
  selected_coins: string[]
  rows: ManualTradeItem[]
  default_value: number
}
// --------------------------------------------

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

  // --- 新增 ---
  enable_long_trailing_stop: boolean
  long_trailing_stop_callback_rate: number
  enable_short_trailing_stop: boolean
  short_trailing_stop_callback_rate: number
  // -----------

  open_maker_retries: number
  open_order_fill_timeout_seconds: number
  close_maker_retries: number
  close_order_fill_timeout_seconds: number
  // 后端仅实现了 multi_factor_weakest 策略，前端不再暴露未实现的策略
  rebalance_method: 'multi_factor_weakest'
  rebalance_top_n: number
  rebalance_min_volume_usd: number
  rebalance_abs_momentum_days: number
  rebalance_rel_strength_days: number
  rebalance_volume_ma_days: number
  rebalance_volume_spike_ratio: number
  rebalance_benchmark_coin: string[]

  enable_rebalance_filters: boolean
  rebalance_rsi_period: number
  rebalance_rsi_threshold: number
  rebalance_short_term_momentum_days: number
  rebalance_short_term_momentum_threshold: number
  rebalance_bollinger_period: number
  rebalance_bollinger_std_dev: number
  rebalance_bollinger_width_spike_ratio: number

  manual_trade_preset?: ManualTradePreset
}

export interface RebalanceCriteria {
  method: 'multi_factor_weakest'
  top_n: number
  min_volume_usd: number
  abs_momentum_days: number
  rel_strength_days: number
  rebalance_volume_ma_days: number
  rebalance_volume_spike_ratio: number
  rebalance_benchmark_coin: string[]

  enable_rebalance_filters: boolean
  rebalance_rsi_period: number
  rebalance_rsi_threshold: number
  rebalance_short_term_momentum_days: number
  rebalance_short_term_momentum_threshold: number
  rebalance_bollinger_period: number
  rebalance_bollinger_std_dev: number
  rebalance_bollinger_width_spike_ratio: number

  manual_target_ratio_perc?: number
}

// --- Phase 2：信号监控（/signals）相关类型 ---
export type SignalDirection = 'long' | 'short' | 'neutral'

export interface SignalRecord {
  id: string
  created_at: string | null
  symbol: string
  full_symbol: string | null
  timeframe: string
  strategy: string
  strategy_index: number
  direction: SignalDirection
  price: number
  title: string
  message: string
}

export interface SignalStatus {
  enabled: boolean
  running: boolean
  last_scan_at: string | null
  next_scan_at: string | null
  scanned_symbols: number
  emitted_count: number
  error_count: number
  last_error: string | null
  auto_trade_enabled: boolean
  last_auto_open: string | Record<string, unknown> | null
}

export interface SignalConfig {
  signal_scan_enabled: boolean
  signal_scan_interval_seconds: number
  signal_scan_static_symbols: string[]
  signal_scan_top_n: number
  signal_scan_timeframes: string[]
  signal_auto_trade_enabled: boolean
  signal_auto_trade_directions: string[]
  signal_auto_trade_strategies: string[]
  signal_auto_trade_timeframes: string[]
  signal_auto_trade_confirmations: number
  signal_auto_trade_confirmation_window_seconds: number
  signal_auto_trade_cooldown_seconds: number
  signal_auto_trade_max_positions: number
  signal_auto_trade_value_usd: number
  signal_ticker_cache_seconds: number
  signal_ohlcv_cache_seconds: number
  signal_dingtalk_enabled: boolean
}

export interface SignalPushStatus {
  dingtalk_configured: boolean
  dingtalk_enabled: boolean
  signal_dingtalk_enabled: boolean
  signal_push_volume_multiplier: number
  static_symbols: string[]
}

export interface SignalsResponse {
  status: SignalStatus
  signals: SignalRecord[]
  config: Partial<SignalConfig>
  push?: SignalPushStatus
}
// ------------------------------------------------

// ------------------------------------------------
// 仓位保护（Phase 3，自 monitor 并入）
// ------------------------------------------------
export interface ProtectionPositionRow {
  symbol: string
  side: 'long' | 'short'
  contracts: number
  entry_price: number
  mark_price: number
  stop_price: number | null
  protected_stop: number | null
  tp1_price: number | null
  tp2_price: number | null
  tp3_price: number | null
  t1_done: boolean
  t2_done: boolean
  t3_done: boolean
  tp1_done: boolean
  tp2_done: boolean
  tp3_done: boolean
  risk_cycle_started_at: number | null
  position_version: number | null
}

export interface ProtectionApiStats {
  request_count: number
  error_count: number
  failures: number
  circuit_open: boolean
  circuit_open_until: number
  cooldown_until: number
}

export interface ProtectionConfig {
  enabled: boolean
  timeframe: string
  tp1_r_multiple: number
  tp2_r_multiple: number
  tp3_r_multiple: number
  tp1_ratio: number
  tp2_ratio: number
  t1_structure_lookback: number
  t2_structure_lookback: number
  t3_structure_lookback: number
  structure_buffer_atr: number
  t1_atr_confirmation: number
  t2_atr_confirmation: number
  t3_atr_confirmation: number
  profit_protection_enabled: boolean
  profit_protection_trigger_r: number
  emergency_enabled: boolean
  exchange_hard_stop_enabled: boolean
  hard_stop_min_distance_pct: number
  hard_stop_atr_multiplier: number
  dynamic_stop_max_distance_pct: number
  [key: string]: unknown
}

export interface ProtectionStatus {
  enabled: boolean
  running: boolean
  started_at: number | null
  last_error: string | null
  timeframe: string | null
  positions: ProtectionPositionRow[]
  api: ProtectionApiStats
  config: ProtectionConfig
}

// ------------------------------------------------
// 周期报告（自 monitor periodic_reports 并入）
// ------------------------------------------------
export interface ReportSentimentConfig {
  enabled: boolean
  rsi_period?: number
  rsi_overbought?: number
  rsi_oversold?: number
}

export interface PeriodicReportConfig {
  report_name: string
  enabled: boolean
  run_interval: string
  top_n_by_volume: number
  top_n_gainers: number
  top_n_volume_ratio: number
  min_consecutive_candles: number
  volume_ma_period: number
  market_sentiment: ReportSentimentConfig
}

export interface ReportRow extends PeriodicReportConfig {
  last_run: number | null
  next_run: number | null
  due_in_seconds: number
  running: boolean
  last_error: string | null
  title: string | null
  scanned: number | null
}

export interface ReportCounts {
  gainers: number
  volume_ratios: number
  overbought: number
  oversold: number
  consecutive: number
}

export interface ReportResult {
  report_name: string
  title: string
  markdown: string
  generated_at: number
  generated_at_text: string
  scanned: number
  symbols_total: number
  counts: ReportCounts
  trigger?: string
}

export interface ReportsStatus {
  reports: ReportRow[]
  dingtalk_configured: boolean
  dingtalk_enabled: boolean
  running: boolean
  latest: Record<string, ReportResult>
}
