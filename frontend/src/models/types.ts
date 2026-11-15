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
  // R-P0-2 裸仓回收：SL/TP 注入失败后的兜底动作
  unprotected_position_action: 'auto_close' | 'keep_alert'
  // R-P1-5 平仓让价兜底（0=关闭）
  close_price_chase_ticks: number
  // R-P1-2 api_* 限流参数（RestGuardian 热更新）
  api_max_concurrency: number
  api_min_interval_sec: number
  api_max_retries: number
  api_failure_threshold: number
  api_circuit_breaker_cooldown_sec: number
  api_418_cooldown_sec: number
  api_429_base_backoff_sec: number
  api_429_max_backoff_sec: number
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
  volume_ratio: number | null
  fwd: Record<string, number> | null
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
  signal_paper_enabled: boolean
  signal_exit_mode: 'percent' | 'atr'
  signal_paper_sl_atr: number
  signal_paper_tp_r: number
  signal_paper_max_bars: number
  signal_live_exit_timeframe: '15m' | '1h' | '4h' | '1d'
  signal_live_exit_timeout_enabled: boolean
  signal_live_sltp_guard_enabled: boolean
  signal_forward_bars: number[]
}

export interface SignalPushStatus {
  dingtalk_configured: boolean
  dingtalk_enabled: boolean
  signal_dingtalk_enabled: boolean
  signal_push_volume_multiplier: number
  static_symbols: string[]
}

export interface PaperPosition {
  id: string
  symbol: string
  timeframe: string
  strategy: string
  direction: SignalDirection
  entry_price: number
  stop_loss: number
  take_profit: number
  max_bars: number
  opened_at: string
}

export interface PaperStats {
  total: number
  win_rate: number | null
  avg_pnl_pct: number | null
  avg_bars: number | null
  sum_pnl_pct: number | null
  by_reason: Record<string, number>
}

export interface ForwardStatRow {
  timeframe: string
  strategy: string
  samples: number
  [key: string]: string | number | null
}

export interface SignalTracking {
  params: {
    enabled: boolean
    exit_mode: 'percent' | 'atr'
    sl_atr: number
    tp_r: number
    max_bars: number
    value_usd: number
    forward_bars: number[]
  }
  open_positions: PaperPosition[]
  trades: Array<
    PaperPosition & { exit_price: number; pnl_pct: number; reason: string; bars_held: number }
  >
  paper_stats: PaperStats
  forward_stats: ForwardStatRow[]
}

export interface LiveExitPosition {
  symbol: string
  full_symbol: string
  side: SignalDirection
  timeframe: string
  strategy: string
  entry_ts: number
  bars_held: number | null
  max_bars: number
}

export interface LiveExitStatus {
  enabled: boolean
  guard_enabled: boolean
  max_bars: number
  positions: LiveExitPosition[]
}

export interface SignalsResponse {
  status: SignalStatus
  signals: SignalRecord[]
  config: Partial<SignalConfig>
  push?: SignalPushStatus
  tracking?: SignalTracking
  live_exit?: LiveExitStatus
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
  t4_done?: boolean
  tp1_done: boolean
  tp2_done: boolean
  tp3_done: boolean
  /** v2：当前挂在交易所上的止盈档位（1/2/3，无挂单为 null） */
  /** 已突破、等回落到该档就止盈（引擎判定，交易所无挂单） */
  tp_armed_level?: number | null
  /** 还没突破的下一档：价格越过它之后才开始等回落 */
  tp_wait_level?: number | null
  /** v2：止盈挂单的挂出价（post-only，到价由交易所撮合） */
  risk_cycle_started_at: number | null
  position_version: number | null
  // v2 专属（v1 引擎不返回）
  engine?: 'v1' | 'v2'
  cycle_id?: string
  risk?: number | null
  tier_levels?: number[]
  disaster_stop?: number | null
  /** 灾难线相对持仓均价的百分比（= 单笔最大亏损） */
  disaster_pct?: number | null
  /** 分批比例的分母：历史最大持仓量，人工加仓后跟进、减仓不缩 */
  size_anchor?: number | null
  /** 兼容字段，与 size_anchor 同值 */
  base_contracts?: number | null
  /** 因加仓重算过几次风险基准（0 = 建仓以来没加过仓） */
  rebase_count?: number | null
  /** 最近的人工加减仓记录 */
  interventions?: ProtectionIntervention[]
  updated_at?: number | null
}

/** 人工（或其它策略）对仓位的干预记录 */
export interface ProtectionIntervention {
  ts: number
  kind: 'add' | 'reduce'
  delta_qty: number
  qty_pct: number
  prev_qty: number
  prev_entry: number
}

export interface ProtectionActionRow {
  ts: number
  symbol: string
  side: string
  text: string
  level: string
}

/** 持久化台账事件（/api/protection/events）：跨重启保留，用于事后复盘「为什么平了」 */
export interface ProtectionEventRow {
  ts: number
  symbol: string
  side: string
  /** cycle_new | reduce | stop | exit | flat | replan | error */
  kind: string
  level: string
  message: string
  /** kind=flat 时：是否判定为交易所兜底 STOP 触发 */
  triggered_stop?: boolean
  stop?: number | null
  last_price?: number | null
  entry?: number | null
  price?: number | null
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
  engine_version?: 'v1' | 'v2'
  dry_run?: boolean
  v2_timeframe?: string
  v2_poll_interval_sec?: number
  tier_ratios?: number[]
  tier_confirm_sec?: number[]
  risk_min_pct?: number
  /** 单笔最大亏损 = 灾难线的位置（相对持仓均价的百分比） */
  risk_max_pct?: number
  /** T1 的距离上限：结构位太远时把第一档收回来 */
  t1_max_pct?: number
  /** 浮盈多少个 ATR 才把止损推到成本价 */
  breakeven_trigger_atr?: number
  /** 保本位至少距离开仓价多少个 ATR（与 breakeven_buffer_pct 取大） */
  breakeven_atr_ratio?: number
  /** 浮盈多少个 ATR 开始按 ATR 追踪 */
  trailing_start_atr?: number
  /** 追踪宽度（峰值 − n×ATR） */
  trailing_atr_mult?: number
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
  /** 黑天鹅判定用的 K 线周期（默认 1h，越小越灵敏也越容易误杀） */
  emergency_timeframe?: string
  /** 黑天鹅全平后同币冷却（秒），0=不冷却 */
  emergency_cooldown_sec?: number
  /** 开仓前黑天鹅预检：命中当前崩盘状态则不下单 */
  emergency_block_new_entries?: boolean
  /** v2 止盈阶梯：三档的 R 倍数（默认 1.5 / 2.5 / 4） */
  tp_r_multiples?: number[]
  /** v2 止盈阶梯：三档各减初始仓位的比例（默认 0.20 / 0.25 / 0.30） */
  tp_ratios?: number[]
  /** 三档之后不挂止盈单、留给追踪止损的仓位比例（默认 0.25） */
  tp_keep_ratio?: number
  /** 「算突破」的缓冲：价格要越过 TP 这么多，才进入等回落状态 */
  tp_breakout_confirm_pct?: number
  exchange_hard_stop_enabled: boolean
  // 双轨治理（接管开仓端遗留的 SL/TP/TS 单）
  take_over_external_stops?: boolean
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
  engine_version?: 'v1' | 'v2'
  positions: ProtectionPositionRow[]
  api: ProtectionApiStats
  config: ProtectionConfig
  /** 黑天鹅冷却中的币（键 `ETH|long`），开仓闸门会据此跳过 */
  cooldowns?: Record<string, { remaining_sec: number; reason: string; symbol: string }>
  v2?: {
    cycle_count: number
    last_cycle_ts: number
    recent_actions: ProtectionActionRow[]
    dry_run: boolean
  }
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
