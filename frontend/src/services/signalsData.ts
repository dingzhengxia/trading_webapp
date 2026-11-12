/**
 * 信号域的默认值 / 选项常量 / 纯归一化函数（T11 自 SignalsView 拆出）。
 *
 * 全部为纯函数与常量，不持有状态；状态与写入口见
 * composables/useSignalsConfig.ts。归一化的目标：后端返回的任何形状
 * 缺字段/类型抖动时，前端拿到的仍是类型完整的数据。
 */
import type {
  LiveExitStatus,
  SignalConfig,
  SignalDirection,
  SignalPushStatus,
  SignalRecord,
  SignalStatus,
  SignalTracking,
} from '@/models/types'

export const POLL_INTERVAL_MS = 10000

/** 抽屉的三个参数 Tab（扫描范围 / 推送与开仓 / 出场规则），?tab= 深链映射到这里 */
export const signalConfigTabs = [
  { key: 'scope', title: '扫描范围', icon: 'mdi-tune-variant' },
  { key: 'push', title: '推送与开仓', icon: 'mdi-bell-ring-outline' },
  { key: 'exit', title: '出场规则', icon: 'mdi-chart-timeline-variant' },
]

export const directionOptions = [
  { title: '做多', value: 'long' },
  { title: '做空', value: 'short' },
]

export const timeframeOptions = ['15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d']

export const strategyOptions = [
  { value: 'ema_cross', title: 'EMA 交叉' },
  { value: 'ma_breakout', title: '均线突破' },
  { value: 'kdj_cross', title: 'KDJ 交叉' },
  { value: 'level_breakout', title: '关键位突破 (BOS)' },
  { value: 'rsi_divergence', title: 'RSI 背离' },
  { value: 'trend_channel_breakout', title: '趋势通道突破' },
  { value: 'ob_luxalgo', title: '订单块 (LuxAlgo)' },
  { value: 'ob_fluxcharts', title: '订单块 (FluxCharts)' },
  { value: 'volatility_breakout', title: '波动率突破（观望，不开仓）' },
  { value: 'consecutive_candles', title: '连续 K 线警示（观望，不开仓）' },
]

/** strategy 原始 key → 中文名，向下传给展示型面板 */
export const strategyLabels: Record<string, string> = Object.fromEntries(
  strategyOptions.map((option) => [option.value, option.title]),
)

export const ATR_TIMEFRAMES = ['15m', '1h', '4h', '1d']

export const defaultSignalStatus: SignalStatus = {
  enabled: false,
  running: false,
  last_scan_at: null,
  next_scan_at: null,
  scanned_symbols: 0,
  emitted_count: 0,
  error_count: 0,
  last_error: null,
  auto_trade_enabled: false,
  last_auto_open: null,
}

export const defaultSignalConfig: SignalConfig = {
  signal_scan_enabled: false,
  signal_scan_interval_seconds: 300,
  signal_scan_static_symbols: [],
  signal_scan_top_n: 20,
  signal_scan_timeframes: ['1h', '4h'],
  signal_auto_trade_enabled: false,
  signal_auto_trade_directions: ['long', 'short'],
  signal_auto_trade_strategies: [
    'ema_cross',
    'ma_breakout',
    'kdj_cross',
    'level_breakout',
    'rsi_divergence',
    'trend_channel_breakout',
    'ob_luxalgo',
    'ob_fluxcharts',
  ],
  signal_auto_trade_timeframes: ['1h', '4h'],
  signal_auto_trade_confirmations: 1,
  signal_auto_trade_confirmation_window_seconds: 300,
  signal_auto_trade_cooldown_seconds: 3600,
  signal_auto_trade_max_positions: 5,
  signal_auto_trade_value_usd: 100,
  signal_ticker_cache_seconds: 30,
  signal_ohlcv_cache_seconds: 300,
  signal_dingtalk_enabled: true,
  signal_paper_enabled: false,
  signal_exit_mode: 'percent',
  signal_paper_sl_atr: 1.5,
  signal_paper_tp_r: 2,
  signal_paper_max_bars: 6,
  signal_live_exit_timeframe: '4h',
  signal_live_exit_timeout_enabled: false,
  signal_live_sltp_guard_enabled: true,
  signal_forward_bars: [4, 12],
}

export const emptyPushStatus = (): SignalPushStatus => ({
  dingtalk_configured: false,
  dingtalk_enabled: false,
  signal_dingtalk_enabled: true,
  signal_push_volume_multiplier: 2,
  static_symbols: [],
})

export const emptyTracking = (): SignalTracking => ({
  params: {
    enabled: false,
    exit_mode: 'percent',
    sl_atr: 1.5,
    tp_r: 2,
    max_bars: 6,
    value_usd: 100,
    forward_bars: [4, 12],
  },
  open_positions: [],
  trades: [],
  paper_stats: {
    total: 0,
    win_rate: null,
    avg_pnl_pct: null,
    avg_bars: null,
    sum_pnl_pct: null,
    by_reason: {},
  },
  forward_stats: [],
})

export const emptyLiveExit = (): LiveExitStatus => ({
  enabled: false,
  guard_enabled: true,
  max_bars: 6,
  positions: [],
})

// ---------------------------------------------------------------------------
// 归一化辅助
// ---------------------------------------------------------------------------

export const toNumber = (value: unknown, fallback: number): number => {
  const num = Number(value)
  return Number.isFinite(num) ? num : fallback
}

export const toStringArray = (value: unknown, fallback: string[]): string[] => {
  if (!Array.isArray(value)) return [...fallback]
  return value.filter((item): item is string => typeof item === 'string')
}

export const normalizeDirection = (value: unknown): SignalDirection =>
  value === 'long' || value === 'short' || value === 'neutral' ? value : 'neutral'

export const normalizeLastAutoOpen = (value: unknown): string | Record<string, unknown> | null => {
  if (typeof value === 'string') return value
  if (value !== null && typeof value === 'object') return value as Record<string, unknown>
  return null
}

export const mergePushStatus = (raw: unknown): SignalPushStatus => {
  if (raw === null || typeof raw !== 'object') return emptyPushStatus()
  const source = raw as Partial<Record<keyof SignalPushStatus, unknown>>
  return {
    dingtalk_configured: source.dingtalk_configured === true,
    dingtalk_enabled: source.dingtalk_enabled === true,
    signal_dingtalk_enabled: source.signal_dingtalk_enabled !== false,
    signal_push_volume_multiplier: toNumber(source.signal_push_volume_multiplier, 2),
    static_symbols: toStringArray(source.static_symbols, []),
  }
}

export const mergeStatus = (raw: unknown): SignalStatus => {
  if (raw === null || typeof raw !== 'object') return { ...defaultSignalStatus }
  const source = raw as Partial<Record<keyof SignalStatus, unknown>>
  return {
    enabled: source.enabled === true,
    running: source.running === true,
    last_scan_at: typeof source.last_scan_at === 'string' ? source.last_scan_at : null,
    next_scan_at: typeof source.next_scan_at === 'string' ? source.next_scan_at : null,
    scanned_symbols: toNumber(source.scanned_symbols, 0),
    emitted_count: toNumber(source.emitted_count, 0),
    error_count: toNumber(source.error_count, 0),
    last_error: typeof source.last_error === 'string' ? source.last_error : null,
    auto_trade_enabled: source.auto_trade_enabled === true,
    last_auto_open: normalizeLastAutoOpen(source.last_auto_open),
  }
}

export const mergeConfig = (raw: Partial<SignalConfig> | undefined): SignalConfig => {
  const source = (raw ?? {}) as Partial<Record<keyof SignalConfig, unknown>>
  const fallback = defaultSignalConfig
  return {
    signal_scan_enabled: source.signal_scan_enabled === true,
    signal_scan_interval_seconds: toNumber(
      source.signal_scan_interval_seconds,
      fallback.signal_scan_interval_seconds,
    ),
    signal_scan_static_symbols: toStringArray(
      source.signal_scan_static_symbols,
      fallback.signal_scan_static_symbols,
    ),
    signal_scan_top_n: toNumber(source.signal_scan_top_n, fallback.signal_scan_top_n),
    signal_scan_timeframes: toStringArray(
      source.signal_scan_timeframes,
      fallback.signal_scan_timeframes,
    ),
    signal_auto_trade_enabled: source.signal_auto_trade_enabled === true,
    signal_auto_trade_directions: toStringArray(
      source.signal_auto_trade_directions,
      fallback.signal_auto_trade_directions,
    ),
    signal_auto_trade_strategies: toStringArray(
      source.signal_auto_trade_strategies,
      fallback.signal_auto_trade_strategies,
    ),
    signal_auto_trade_timeframes: toStringArray(
      source.signal_auto_trade_timeframes,
      fallback.signal_auto_trade_timeframes,
    ),
    signal_auto_trade_confirmations: toNumber(
      source.signal_auto_trade_confirmations,
      fallback.signal_auto_trade_confirmations,
    ),
    signal_auto_trade_confirmation_window_seconds: toNumber(
      source.signal_auto_trade_confirmation_window_seconds,
      fallback.signal_auto_trade_confirmation_window_seconds,
    ),
    signal_auto_trade_cooldown_seconds: toNumber(
      source.signal_auto_trade_cooldown_seconds,
      fallback.signal_auto_trade_cooldown_seconds,
    ),
    signal_auto_trade_max_positions: toNumber(
      source.signal_auto_trade_max_positions,
      fallback.signal_auto_trade_max_positions,
    ),
    signal_auto_trade_value_usd: toNumber(
      source.signal_auto_trade_value_usd,
      fallback.signal_auto_trade_value_usd,
    ),
    signal_ticker_cache_seconds: toNumber(
      source.signal_ticker_cache_seconds,
      fallback.signal_ticker_cache_seconds,
    ),
    signal_ohlcv_cache_seconds: toNumber(
      source.signal_ohlcv_cache_seconds,
      fallback.signal_ohlcv_cache_seconds,
    ),
    signal_dingtalk_enabled: source.signal_dingtalk_enabled !== false,
    signal_paper_enabled: source.signal_paper_enabled === true,
    signal_exit_mode: source.signal_exit_mode === 'atr' ? 'atr' : 'percent',
    signal_paper_sl_atr: toNumber(source.signal_paper_sl_atr, fallback.signal_paper_sl_atr),
    signal_paper_tp_r: toNumber(source.signal_paper_tp_r, fallback.signal_paper_tp_r),
    signal_paper_max_bars: toNumber(source.signal_paper_max_bars, fallback.signal_paper_max_bars),
    signal_live_exit_timeframe: ATR_TIMEFRAMES.includes(String(source.signal_live_exit_timeframe))
      ? (source.signal_live_exit_timeframe as SignalConfig['signal_live_exit_timeframe'])
      : fallback.signal_live_exit_timeframe,
    signal_live_exit_timeout_enabled: source.signal_live_exit_timeout_enabled === true,
    signal_live_sltp_guard_enabled: source.signal_live_sltp_guard_enabled !== false,
    signal_forward_bars: Array.isArray(source.signal_forward_bars)
      ? (source.signal_forward_bars as unknown[]).map((bar) => toNumber(bar, 4))
      : [...fallback.signal_forward_bars],
  }
}

export const normalizeSignals = (raw: unknown): SignalRecord[] => {
  if (!Array.isArray(raw)) return []
  const result: SignalRecord[] = []
  for (const item of raw) {
    if (item === null || typeof item !== 'object') continue
    const record = item as Partial<Record<keyof SignalRecord, unknown>>
    if (typeof record.symbol !== 'string') continue
    result.push({
      id:
        typeof record.id === 'string'
          ? record.id
          : String(record.symbol) + '-' + String(record.created_at ?? result.length),
      created_at: typeof record.created_at === 'string' ? record.created_at : null,
      symbol: record.symbol,
      full_symbol: typeof record.full_symbol === 'string' ? record.full_symbol : null,
      timeframe: typeof record.timeframe === 'string' ? record.timeframe : '',
      strategy: typeof record.strategy === 'string' ? record.strategy : '',
      strategy_index: toNumber(record.strategy_index, 0),
      direction: normalizeDirection(record.direction),
      price: toNumber(record.price, 0),
      volume_ratio:
        typeof record.volume_ratio === 'number' && Number.isFinite(record.volume_ratio)
          ? record.volume_ratio
          : null,
      fwd:
        record.fwd !== null && typeof record.fwd === 'object'
          ? Object.fromEntries(
              Object.entries(record.fwd as Record<string, unknown>)
                .map(([key, value]) => [key, Number(value)])
                .filter(([, value]) => Number.isFinite(value as number)),
            )
          : null,
      title: typeof record.title === 'string' ? record.title : '',
      message: typeof record.message === 'string' ? record.message : '',
    })
  }
  return result
}

export const mergeTracking = (raw: unknown): SignalTracking => {
  const base = emptyTracking()
  if (raw === null || typeof raw !== 'object') return base
  const data = raw as Record<string, unknown>
  const params = (data.params ?? {}) as Record<string, unknown>
  return {
    params: {
      enabled: params.enabled === true,
      exit_mode: params.exit_mode === 'atr' ? 'atr' : 'percent',
      sl_atr: toNumber(params.sl_atr, base.params.sl_atr),
      tp_r: toNumber(params.tp_r, base.params.tp_r),
      max_bars: toNumber(params.max_bars, base.params.max_bars),
      value_usd: toNumber(params.value_usd, base.params.value_usd),
      forward_bars: Array.isArray(params.forward_bars)
        ? (params.forward_bars as number[]).map((bar) => toNumber(bar, 4))
        : base.params.forward_bars,
    },
    open_positions: Array.isArray(data.open_positions)
      ? (data.open_positions as SignalTracking['open_positions'])
      : [],
    trades: Array.isArray(data.trades) ? (data.trades as SignalTracking['trades']) : [],
    paper_stats: {
      ...base.paper_stats,
      ...((data.paper_stats ?? {}) as Partial<SignalTracking['paper_stats']>),
    },
    forward_stats: Array.isArray(data.forward_stats)
      ? (data.forward_stats as SignalTracking['forward_stats'])
      : [],
  }
}
