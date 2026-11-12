<!-- frontend/src/views/SignalsView.vue (信号监控) -->
<!--
  结构调整：原来 4 张卡纵向堆叠，首屏是 8 个同权重 chip + 一屏设置表单，
  真正的「信号列表」排在第 4 张卡、首屏看不到。
  现在改成：KPI 指标行 + Tab（信号列表 / 扫描范围 / 推送与开仓 / 出场与统计），
  按「读」和「改」切分——用户 90% 的时间是在读信号，10% 才在调参。
-->
<template>
  <div>
    <!-- 指标行：一眼看到「有多少信号 / 有没有出错 / 自动开仓开着没有」 -->
    <v-row dense>
      <v-col cols="6" sm="3">
        <MetricCard
          label="累计信号"
          :value="status.emitted_count"
          :hint="`已扫描 ${status.scanned_symbols} 个币种`"
          icon="mdi-radar"
        />
      </v-col>
      <v-col cols="6" sm="3">
        <MetricCard
          label="错误数"
          :value="status.error_count"
          :hint="status.last_error ? '存在最近错误，见下方提示' : '无错误'"
          icon="mdi-alert-circle-outline"
          :tone="status.error_count > 0 ? 'down' : 'neutral'"
          :warning="status.error_count > 0"
        />
      </v-col>
      <v-col cols="6" sm="3">
        <MetricCard
          label="纸面胜率"
          :value="winRateText"
          :hint="`样本 ${tracking.paper_stats.total} 笔`"
          icon="mdi-flask-outline"
          :tone="winRateTone"
        />
      </v-col>
      <v-col cols="6" sm="3">
        <MetricCard
          label="自动开仓"
          :value="config.signal_auto_trade_enabled ? '已启用' : '已停用'"
          :hint="`最近：${lastAutoOpenText}`"
          icon="mdi-robot"
        />
      </v-col>
    </v-row>

    <!-- 状态条：运行态与时间戳，弱化为一行文字，不再占用 8 个 chip 的面积 -->
    <div class="status-strip d-flex flex-wrap align-center ga-4 mt-3 mb-3">
      <span class="dot-item">
        <i class="dot" :class="status.running ? 'dot--on' : 'dot--off'"></i>
        {{ status.running ? '扫描中' : '空闲' }}
      </span>
      <span class="dot-item">
        <i class="dot" :class="status.enabled ? 'dot--on' : 'dot--off'"></i>
        {{ status.enabled ? '扫描已启用' : '扫描已停用' }}
      </span>
      <span class="dot-item">
        <i class="dot" :class="pushStatus.dingtalk_configured ? 'dot--on' : 'dot--warn'"></i>
        钉钉{{ pushStatus.dingtalk_configured ? '已配置' : '未配置' }}
      </span>
      <span class="dot-item text-medium-emphasis">上次扫描 {{ formatTime(status.last_scan_at) }}</span>
      <span class="dot-item text-medium-emphasis">下次扫描 {{ formatTime(status.next_scan_at) }}</span>
    </div>

    <v-alert
      v-if="status.last_error"
      type="error"
      variant="tonal"
      density="compact"
      class="mb-3 text-caption"
      closable
    >
      最近错误：{{ status.last_error }}
    </v-alert>

    <v-card variant="flat" class="signal-shell">
      <v-tabs v-model="activeTab" class="tabs-quiet" show-arrows>
        <v-tab value="list">
          <v-icon start size="16">mdi-format-list-bulleted</v-icon>
          信号列表
          <v-chip v-if="signals.length" size="x-small" variant="tonal" class="ml-2">
            {{ signals.length }}
          </v-chip>
        </v-tab>
        <v-tab value="scope">
          <v-icon start size="16">mdi-tune-variant</v-icon>
          扫描范围
        </v-tab>
        <v-tab value="push">
          <v-icon start size="16">mdi-bell-ring-outline</v-icon>
          推送与开仓
        </v-tab>
        <v-tab value="exit">
          <v-icon start size="16">mdi-chart-timeline-variant</v-icon>
          出场与统计
        </v-tab>
      </v-tabs>

      <v-card-text>
        <v-window v-model="activeTab">
          <v-window-item value="list">
            <SignalListPanel
              v-model:direction="directionFilter"
              :signals="filteredSignals"
              :total="signals.length"
              :forward-bars="tracking.params.forward_bars"
              :volume-threshold="pushStatus.signal_push_volume_multiplier"
              :static-symbols="pushStatus.static_symbols"
              :strategy-labels="strategyLabels"
              :scanning="scanning"
              :clearing="clearing"
              :loading="loading"
              @scan="scanNow"
              @clear="clearSignals"
              @refresh="refresh"
            />
          </v-window-item>

          <v-window-item value="scope">
            <ScanScopePanel
              :enabled="status.enabled"
              :saving-scan="savingScan"
              :static-symbols="scanStaticSymbols"
              :static-items="staticSymbolItems"
              :top-n="scopeTopN"
              :timeframes="scopeTimeframes"
              :timeframe-options="timeframeOptions"
              :valid="scopeValid"
              :saving="savingScope"
              :dirty="scopeDirty"
              @update:static-symbols="setStaticSymbols"
              @update:top-n="onScopeTopNChange"
              @update:timeframes="onScopeTimeframesChange"
              @toggle="onToggleScan"
              @save="saveScanScope"
            />
          </v-window-item>

          <v-window-item value="push">
            <PushAutoPanel
              :push-status="pushStatus"
              :push-volume-input="pushVolumeInput"
              :push-volume-dirty="pushVolumeDirty"
              :saving-dingtalk-push="savingDingtalkPush"
              :saving-push-config="savingPushConfig"
              :auto-enabled="autoTradeEnabled"
              :saving-auto-trade="savingAutoTrade"
              :auto-form="autoForm"
              :auto-valid="autoFormValid"
              :saving-auto="savingAuto"
              :last-auto-open-text="lastAutoOpenText"
              :direction-options="directionOptions"
              :timeframe-options="timeframeOptions"
              :strategy-options="strategyOptions"
              @update:push-volume-input="onPushVolumeChange"
              @toggle-dingtalk="onToggleDingtalkPush"
              @save-volume="savePushVolume"
              @toggle-auto="onToggleAutoTrade"
              @save-auto="saveAutoConfig"
              @dirty="markAutoFormDirty"
            />
          </v-window-item>

          <v-window-item value="exit">
            <ExitStatsPanel
              :exit-mode="exitMode"
              :tracking="tracking"
              :live-exit="liveExit"
              :paper-form="paperForm"
              :atr-timeframes="ATR_TIMEFRAMES"
              :strategy-labels="strategyLabels"
              :valid="paperFormValid"
              :saving-paper-config="savingPaperConfig"
              :saving-paper-toggle="savingPaperToggle"
              :saving-live-timeout="savingLiveTimeout"
              :saving-sltp-guard="savingSltpGuard"
              @change-mode="onChangeExitMode"
              @toggle-paper="onTogglePaper"
              @save-paper="savePaperConfig"
              @toggle-live-timeout="onToggleLiveTimeout"
              @toggle-sltp-guard="onToggleSltpGuard"
              @dirty="paperDirty = true"
            />
          </v-window-item>
        </v-window>
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/services/api'
import { useSnackbarStore } from '@/stores/snackbar'
import { useUiStore } from '@/stores/uiStore'
import type {
  LiveExitStatus,
  SignalConfig,
  SignalDirection,
  SignalPushStatus,
  SignalRecord,
  SignalsResponse,
  SignalStatus,
  SignalTracking,
} from '@/models/types'
import { getErrorMessage, getErrorStatus } from '@/utils/errors'
import { formatIsoTime as formatTime } from '@/utils/format'
import { directionLabel } from '@/utils/tone'
import MetricCard from '@/components/MetricCard.vue'
import SignalListPanel from '@/components/signals/SignalListPanel.vue'
import ScanScopePanel from '@/components/signals/ScanScopePanel.vue'
import PushAutoPanel, { type AutoTradeForm } from '@/components/signals/PushAutoPanel.vue'
import ExitStatsPanel, { type PaperForm } from '@/components/signals/ExitStatsPanel.vue'
import { useSettingsStore } from '@/stores/settingsStore'

const POLL_INTERVAL_MS = 10000

const directionOptions = [
  { title: '做多', value: 'long' },
  { title: '做空', value: 'short' },
]

const timeframeOptions = ['15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d']

const strategyOptions = [
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

/** strategy 原始 key → 中文名，向下传给两个展示型面板 */
const strategyLabels = Object.fromEntries(
  strategyOptions.map((option) => [option.value, option.title]),
) as Record<string, string>

const defaultSignalStatus: SignalStatus = {
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

const defaultSignalConfig: SignalConfig = {
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

const snackbarStore = useSnackbarStore()
const uiStore = useUiStore()
const settingsStore = useSettingsStore()

// 支持 ?tab=list|scope|push|exit 深链，方便把某一页配置直接发给别人
const route = useRoute()
const activeTab = ref(
  ['list', 'scope', 'push', 'exit'].includes(String(route.query.tab))
    ? String(route.query.tab)
    : 'list',
)
const status = ref<SignalStatus>({ ...defaultSignalStatus })
const signals = ref<SignalRecord[]>([])
const config = ref<SignalConfig>({ ...defaultSignalConfig })
const loading = ref(false)
const scanning = ref(false)
const clearing = ref(false)
const savingScan = ref(false)
const savingAutoTrade = ref(false)
const savingAuto = ref(false)
const directionFilter = ref<string>('all')
const savingDingtalkPush = ref(false)
const pushStatus = ref<SignalPushStatus>({
  dingtalk_configured: false,
  dingtalk_enabled: false,
  signal_dingtalk_enabled: true,
  signal_push_volume_multiplier: 2,
  static_symbols: [],
})
const savingPushConfig = ref(false)
const pushVolumeInput = ref<number>(2)
const pushVolumeDirty = ref(false)

// ------------------------------------------------- 纸面跟踪（只记录不下单）
const emptyTracking = (): SignalTracking => ({
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
const tracking = ref<SignalTracking>(emptyTracking())
const savingPaperConfig = ref(false)
const savingPaperToggle = ref(false)
const paperDirty = ref(false)
const ATR_TIMEFRAMES = ['15m', '1h', '4h', '1d']
const paperForm = ref<PaperForm>({ slAtr: 1.5, tpR: 2, maxBars: 6, atrTimeframe: '4h' })
const paperEnabled = computed(() => tracking.value.params.enabled)

// ------------------------------------------------- 实盘出场层（超时平仓 + 登记）
const liveExit = ref<LiveExitStatus>({
  enabled: false,
  guard_enabled: true,
  max_bars: 6,
  positions: [],
})
const savingLiveTimeout = ref(false)
const savingSltpGuard = ref(false)
const liveTimeoutEnabled = computed(() => liveExit.value.enabled)
const sltpGuardEnabled = computed(() => liveExit.value.guard_enabled)
const exitMode = computed(() => config.value.signal_exit_mode)
const paperFormValid = computed(
  () =>
    Number(paperForm.value.slAtr) >= 0.2 &&
    Number(paperForm.value.slAtr) <= 10 &&
    Number(paperForm.value.tpR) >= 0.5 &&
    Number(paperForm.value.tpR) <= 10 &&
    Number(paperForm.value.maxBars) >= 1 &&
    Number(paperForm.value.maxBars) <= 100,
)

// ------------------------------------------------- 扫描范围（静态币 / TopN / 周期）
const savingScope = ref(false)
const scopeDirty = ref(false)
const scanStaticSymbols = ref<string[]>([...defaultSignalConfig.signal_scan_static_symbols])
const scopeTopN = ref<number>(defaultSignalConfig.signal_scan_top_n)
const scopeTimeframes = ref<string[]>([...defaultSignalConfig.signal_scan_timeframes])

const autoForm = ref<AutoTradeForm>({
  directions: [...defaultSignalConfig.signal_auto_trade_directions],
  strategies: [...defaultSignalConfig.signal_auto_trade_strategies],
  timeframes: [...defaultSignalConfig.signal_auto_trade_timeframes],
  confirmations: defaultSignalConfig.signal_auto_trade_confirmations,
  confirmationWindowSeconds: defaultSignalConfig.signal_auto_trade_confirmation_window_seconds,
  cooldownSeconds: defaultSignalConfig.signal_auto_trade_cooldown_seconds,
  valueUsd: defaultSignalConfig.signal_auto_trade_value_usd,
  maxPositions: defaultSignalConfig.signal_auto_trade_max_positions,
})

const autoFormDirty = ref(false)

let pollTimer: number | undefined

const autoTradeEnabled = computed(() => config.value.signal_auto_trade_enabled)

// ---- KPI 展示值 ----
const winRateText = computed(() => {
  const rate = tracking.value.paper_stats.win_rate
  return rate == null ? '—' : `${rate}%`
})
const winRateTone = computed<'up' | 'down' | 'neutral'>(() => {
  const rate = tracking.value.paper_stats.win_rate
  if (rate == null) return 'neutral'
  return rate >= 50 ? 'up' : 'down'
})

const scopeValid = computed(
  () =>
    scopeTimeframes.value.length > 0 &&
    Number(scopeTopN.value) >= 1 &&
    Number(scopeTopN.value) <= 500,
)

const autoFormValid = computed(() => {
  const form = autoForm.value
  return (
    form.directions.length > 0 &&
    form.strategies.length > 0 &&
    form.timeframes.length > 0 &&
    Number(form.confirmations) >= 1 &&
    Number(form.confirmationWindowSeconds) > 0 &&
    Number(form.cooldownSeconds) >= 0 &&
    Number(form.valueUsd) > 0 &&
    Number(form.maxPositions) >= 1
  )
})

const filteredSignals = computed(() => {
  const list =
    directionFilter.value === 'all'
      ? signals.value
      : signals.value.filter((signal) => signal.direction === directionFilter.value)
  return list.slice(0, 200)
})

const lastAutoOpenText = computed(() => {
  const value = status.value.last_auto_open
  if (!value) return '—'
  if (typeof value === 'string') return value
  const symbol = typeof value.symbol === 'string' ? value.symbol : ''
  const direction = typeof value.direction === 'string' ? value.direction : ''
  const at = typeof value.at === 'string' ? value.at : ''
  if (symbol) {
    const directionText = direction ? directionLabel(direction) : ''
    const atText = at ? formatTime(at) : ''
    return [symbol, directionText, atText].filter((part) => part.length > 0).join(' ')
  }
  return JSON.stringify(value)
})

const toNumber = (value: unknown, fallback: number): number => {
  const num = Number(value)
  return Number.isFinite(num) ? num : fallback
}

const toStringArray = (value: unknown, fallback: string[]): string[] => {
  if (!Array.isArray(value)) return [...fallback]
  return value.filter((item): item is string => typeof item === 'string')
}

const normalizeDirection = (value: unknown): SignalDirection =>
  value === 'long' || value === 'short' || value === 'neutral' ? value : 'neutral'

const normalizeLastAutoOpen = (value: unknown): string | Record<string, unknown> | null => {
  if (typeof value === 'string') return value
  if (value !== null && typeof value === 'object') return value as Record<string, unknown>
  return null
}

const mergePushStatus = (raw: unknown): SignalPushStatus => {
  if (raw === null || typeof raw !== 'object') {
    return {
      dingtalk_configured: false,
      dingtalk_enabled: false,
      signal_dingtalk_enabled: true,
      signal_push_volume_multiplier: 2,
      static_symbols: [],
    }
  }
  const source = raw as Partial<Record<keyof SignalPushStatus, unknown>>
  return {
    dingtalk_configured: source.dingtalk_configured === true,
    dingtalk_enabled: source.dingtalk_enabled === true,
    signal_dingtalk_enabled: source.signal_dingtalk_enabled !== false,
    signal_push_volume_multiplier: toNumber(source.signal_push_volume_multiplier, 2),
    static_symbols: toStringArray(source.static_symbols, []),
  }
}

const mergeStatus = (raw: unknown): SignalStatus => {
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

const mergeConfig = (raw: Partial<SignalConfig> | undefined): SignalConfig => {
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

const normalizeSignals = (raw: unknown): SignalRecord[] => {
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

const mergeTracking = (raw: unknown): SignalTracking => {
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

// 用 Object.assign 只改字段、不换对象：
// 子面板持有的是同一个对象引用，父组件整体替换会让子面板读写到旧对象。
const syncPaperForm = (next: SignalTracking): void => {
  if (paperDirty.value) return
  Object.assign(paperForm.value, {
    slAtr: next.params.sl_atr,
    tpR: next.params.tp_r,
    maxBars: next.params.max_bars,
    atrTimeframe: config.value.signal_live_exit_timeframe,
  })
}

const syncAutoForm = (nextConfig: SignalConfig): void => {
  if (autoFormDirty.value) return
  Object.assign(autoForm.value, {
    directions: [...nextConfig.signal_auto_trade_directions],
    strategies: [...nextConfig.signal_auto_trade_strategies],
    timeframes: [...nextConfig.signal_auto_trade_timeframes],
    confirmations: nextConfig.signal_auto_trade_confirmations,
    confirmationWindowSeconds: nextConfig.signal_auto_trade_confirmation_window_seconds,
    cooldownSeconds: nextConfig.signal_auto_trade_cooldown_seconds,
    valueUsd: nextConfig.signal_auto_trade_value_usd,
    maxPositions: nextConfig.signal_auto_trade_max_positions,
  })
}

const markAutoFormDirty = (): void => {
  autoFormDirty.value = true
}

const fetchSignals = async (silent: boolean): Promise<void> => {
  if (!silent) loading.value = true
  try {
    const response = await api.get<SignalsResponse>('/api/signals')
    const data = response.data
    status.value = mergeStatus(data.status)
    signals.value = normalizeSignals(data.signals)
    const nextConfig = mergeConfig(data.config)
    config.value = nextConfig
    pushStatus.value = mergePushStatus(data.push)
    if (!pushVolumeDirty.value) pushVolumeInput.value = pushStatus.value.signal_push_volume_multiplier
    tracking.value = mergeTracking(data.tracking)
    liveExit.value = data.live_exit ?? {
      enabled: false,
      guard_enabled: true,
      max_bars: 6,
      positions: [],
    }
    syncPaperForm(tracking.value)
    syncScopeForm(nextConfig)
    syncAutoForm(nextConfig)
  } catch (error: unknown) {
    if (!silent) {
      snackbarStore.show({
        message: '获取信号数据失败: ' + getErrorMessage(error),
        color: 'error',
      })
    }
  } finally {
    if (!silent) loading.value = false
  }
}

const refresh = (): void => {
  void fetchSignals(false)
}

const onScopeTopNChange = (value: number): void => {
  scopeTopN.value = value
  scopeDirty.value = true
}

const onScopeTimeframesChange = (value: unknown): void => {
  scopeTimeframes.value = Array.isArray(value) ? value.map(String) : []
  scopeDirty.value = true
}

const onPushVolumeChange = (value: number): void => {
  pushVolumeInput.value = value
  pushVolumeDirty.value = true
}

const pushLog = (message: string, level: 'info' | 'success' | 'warning' | 'error'): void => {
  uiStore.logStore.addLog({
    message,
    level,
    timestamp: new Date().toLocaleTimeString(),
  })
}

const onToggleScan = async (value: unknown): Promise<void> => {
  const enabled = Boolean(value)
  if (savingScan.value || enabled === status.value.enabled) return
  savingScan.value = true
  const previous = status.value.enabled
  status.value.enabled = enabled
  try {
    const response = await api.post<{ config?: Partial<SignalConfig> }>('/api/signals/config', {
      signal_scan_enabled: enabled,
    })
    if (response.data.config) {
      config.value = mergeConfig({ ...config.value, ...response.data.config })
    }
    config.value.signal_scan_enabled = enabled
    snackbarStore.show({
      message: enabled ? '信号扫描已启用。' : '信号扫描已停用。',
      color: 'success',
    })
    pushLog('[前端] 信号扫描已' + (enabled ? '启用' : '停用') + '。', 'info')
    await fetchSignals(true)
  } catch (error: unknown) {
    status.value.enabled = previous
    config.value.signal_scan_enabled = previous
    snackbarStore.show({
      message: '切换扫描开关失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    savingScan.value = false
  }
}

const syncScopeForm = (nextConfig: SignalConfig): void => {
  // 有未保存的编辑时不回填，避免 10 秒轮询覆盖用户输入
  if (scopeDirty.value) return
  scanStaticSymbols.value = [...nextConfig.signal_scan_static_symbols]
  scopeTopN.value = nextConfig.signal_scan_top_n
  scopeTimeframes.value = [...nextConfig.signal_scan_timeframes]
}

const normalizeSymbolInput = (value: string): string =>
  value.trim().toUpperCase().split('/')[0].split(':')[0]

// 下拉选项 = 备选总池 ∪ 已选（保证已选但不在池内的币种照常显示）
const staticSymbolItems = computed<string[]>(() => {
  const pool = (settingsStore.availableCoins ?? [])
    .map((item) => normalizeSymbolInput(item))
    .filter(Boolean)
  return [...new Set([...scanStaticSymbols.value, ...pool])].sort()
})

const setStaticSymbols = (value: unknown): void => {
  const list = Array.isArray(value) ? value : []
  const next = [...new Set(list.map((item) => normalizeSymbolInput(String(item))).filter(Boolean))]
  // 顺序稳定：新选中的追加在尾部，避免 chips 顺序抖动
  scanStaticSymbols.value = next
  scopeDirty.value = true
}

const saveScanScope = async (): Promise<void> => {
  if (!scopeValid.value || savingScope.value) return
  savingScope.value = true
  try {
    const payload = {
      signal_scan_static_symbols: [...scanStaticSymbols.value],
      signal_scan_top_n: Number(scopeTopN.value),
      signal_scan_timeframes: [...scopeTimeframes.value],
    }
    const response = await api.post<{ config?: Partial<SignalConfig> }>(
      '/api/signals/config',
      payload,
    )
    if (response.data.config) {
      config.value = mergeConfig({ ...config.value, ...response.data.config })
    }
    scopeDirty.value = false
    snackbarStore.show({
      message: `扫描范围已保存（静态币 ${scanStaticSymbols.value.length} 个 / Top ${scopeTopN.value}）。`,
      color: 'success',
    })
    pushLog(
      '[前端] 扫描范围已保存：静态币 ' +
        (scanStaticSymbols.value.join(',') || '无') +
        `；Top ${scopeTopN.value}；周期 ${scopeTimeframes.value.join('/')}`,
      'success',
    )
    await fetchSignals(true)
  } catch (error: unknown) {
    snackbarStore.show({
      message: '保存扫描范围失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    savingScope.value = false
  }
}

const onTogglePaper = async (value: unknown): Promise<void> => {
  const enabled = Boolean(value)
  if (savingPaperToggle.value || enabled === paperEnabled.value) return
  savingPaperToggle.value = true
  const previous = tracking.value.params.enabled
  tracking.value.params.enabled = enabled
  try {
    await api.post('/api/signals/config', { signal_paper_enabled: enabled })
    snackbarStore.show({
      message: enabled ? '纸面跟踪已启用（只记录，不下单）。' : '纸面跟踪已停用。',
      color: 'success',
    })
    pushLog('[前端] 纸面跟踪已' + (enabled ? '启用' : '停用') + '。', 'info')
    await fetchSignals(true)
  } catch (error: unknown) {
    tracking.value.params.enabled = previous
    snackbarStore.show({
      message: '切换纸面跟踪失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    savingPaperToggle.value = false
  }
}

const onToggleLiveTimeout = async (value: unknown): Promise<void> => {
  const enabled = Boolean(value)
  if (savingLiveTimeout.value || enabled === liveTimeoutEnabled.value) return
  savingLiveTimeout.value = true
  const previous = liveExit.value.enabled
  liveExit.value.enabled = enabled
  try {
    await api.post('/api/signals/config', { signal_live_exit_timeout_enabled: enabled })
    snackbarStore.show({
      message: enabled
        ? `实盘超时平仓已启用：自动仓持有满 ${liveExit.value.max_bars} 根将市价平掉。`
        : '实盘超时平仓已关闭（已有登记保留，仅对账）。',
      color: enabled ? 'warning' : 'success',
    })
    pushLog('[前端] 实盘超时平仓已' + (enabled ? '启用' : '关闭') + '。', enabled ? 'warning' : 'info')
    await fetchSignals(true)
  } catch (error: unknown) {
    liveExit.value.enabled = previous
    snackbarStore.show({
      message: '切换实盘超时平仓失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    savingLiveTimeout.value = false
  }
}

const onToggleSltpGuard = async (value: unknown): Promise<void> => {
  const enabled = Boolean(value)
  if (savingSltpGuard.value || enabled === sltpGuardEnabled.value) return
  savingSltpGuard.value = true
  const previous = liveExit.value.guard_enabled
  liveExit.value.guard_enabled = enabled
  try {
    await api.post('/api/signals/config', { signal_live_sltp_guard_enabled: enabled })
    snackbarStore.show({
      message: enabled
        ? '止损巡检已启用：手动与自动仓位缺少止损时会自动补挂。'
        : '止损巡检已关闭：挂单失败或人为撤单后将不再自动补挂。',
      color: enabled ? 'success' : 'warning',
    })
    pushLog('[前端] 止损巡检已' + (enabled ? '启用' : '关闭') + '。', enabled ? 'success' : 'warning')
    await fetchSignals(true)
  } catch (error: unknown) {
    liveExit.value.guard_enabled = previous
    snackbarStore.show({
      message: '切换止损巡检失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    savingSltpGuard.value = false
  }
}

const onChangeExitMode = async (value: unknown): Promise<void> => {
  const mode = value === 'atr' ? 'atr' : 'percent'
  if (savingPaperConfig.value || mode === exitMode.value) return
  savingPaperConfig.value = true
  const previous = config.value.signal_exit_mode
  config.value.signal_exit_mode = mode
  try {
    await api.post('/api/signals/config', { signal_exit_mode: mode })
    snackbarStore.show({
      message: mode === 'percent' ? '已改用现有止盈止损（实盘同款）。' : '已切换到 ATR 研究模式。',
      color: 'success',
    })
    pushLog('[前端] 出场模式: ' + (mode === 'percent' ? '现有止盈止损' : 'ATR 研究模式'), 'info')
    await fetchSignals(true)
  } catch (error: unknown) {
    config.value.signal_exit_mode = previous
    snackbarStore.show({
      message: '切换出场模式失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    savingPaperConfig.value = false
  }
}

const savePaperConfig = async (): Promise<void> => {
  if (savingPaperConfig.value || !paperFormValid.value) return
  savingPaperConfig.value = true
  const payload = {
    signal_paper_sl_atr: Number(paperForm.value.slAtr),
    signal_paper_tp_r: Number(paperForm.value.tpR),
    signal_paper_max_bars: Number(paperForm.value.maxBars),
    signal_live_exit_timeframe: paperForm.value.atrTimeframe,
  }
  try {
    await api.post('/api/signals/config', payload)
    paperDirty.value = false
    snackbarStore.show({ message: '出场参数已保存（实盘与纸面同时生效）。', color: 'success' })
    pushLog(
      `[前端] 出场参数: 止损 ${payload.signal_paper_sl_atr} ATR / 止盈 ${payload.signal_paper_tp_r}R / 最多 ${payload.signal_paper_max_bars} 根 / ATR 周期 ${payload.signal_live_exit_timeframe}`,
      'success',
    )
    await fetchSignals(true)
  } catch (error: unknown) {
    snackbarStore.show({
      message: '保存纸面出场参数失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    savingPaperConfig.value = false
  }
}

const savePushVolume = async (): Promise<void> => {
  if (savingPushConfig.value) return
  const raw = Number(pushVolumeInput.value)
  const value = Number.isFinite(raw) && raw >= 0 ? Math.min(raw, 100) : 0
  savingPushConfig.value = true
  const previous = pushStatus.value.signal_push_volume_multiplier
  try {
    await api.post('/api/signals/config', { signal_push_volume_multiplier: value })
    pushStatus.value.signal_push_volume_multiplier = value
    pushVolumeDirty.value = false
    const label = value > 0 ? `${value}x` : '不过滤'
    snackbarStore.show({ message: `推送量能门槛已保存（${label}）。`, color: 'success' })
    pushLog(`[前端] 推送量能门槛已保存: ${label}`, 'success')
    await fetchSignals(true)
  } catch (error: unknown) {
    pushStatus.value.signal_push_volume_multiplier = previous
    snackbarStore.show({
      message: '保存推送量能门槛失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    savingPushConfig.value = false
  }
}

const onToggleDingtalkPush = async (value: unknown): Promise<void> => {
  const enabled = Boolean(value)
  if (savingDingtalkPush.value || enabled === pushStatus.value.signal_dingtalk_enabled) return
  savingDingtalkPush.value = true
  const previous = pushStatus.value.signal_dingtalk_enabled
  pushStatus.value.signal_dingtalk_enabled = enabled
  config.value.signal_dingtalk_enabled = enabled
  try {
    await api.post('/api/signals/config', { signal_dingtalk_enabled: enabled })
    snackbarStore.show({
      message: enabled ? '币种信号钉钉推送已启用。' : '币种信号钉钉推送已停用。',
      color: 'success',
    })
    pushLog('[前端] 币种信号钉钉推送已' + (enabled ? '启用' : '停用') + '。', 'info')
    await fetchSignals(true)
  } catch (error: unknown) {
    pushStatus.value.signal_dingtalk_enabled = previous
    config.value.signal_dingtalk_enabled = previous
    snackbarStore.show({
      message: '切换钉钉推送开关失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    savingDingtalkPush.value = false
  }
}

const onToggleAutoTrade = async (value: unknown): Promise<void> => {
  const enabled = Boolean(value)
  if (savingAutoTrade.value || enabled === config.value.signal_auto_trade_enabled) return
  savingAutoTrade.value = true
  const previous = config.value.signal_auto_trade_enabled
  config.value.signal_auto_trade_enabled = enabled
  try {
    await api.post('/api/signals/auto-trade', { enabled })
    snackbarStore.show({
      message: enabled ? '自动开仓已启用。' : '自动开仓已停用。',
      color: 'success',
    })
    pushLog('[前端] 信号自动开仓已' + (enabled ? '启用' : '停用') + '。', 'info')
    await fetchSignals(true)
  } catch (error: unknown) {
    config.value.signal_auto_trade_enabled = previous
    snackbarStore.show({
      message: '切换自动开仓开关失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    savingAutoTrade.value = false
  }
}

const buildAutoConfigPayload = (): Record<string, unknown> => ({
  signal_auto_trade_enabled: config.value.signal_auto_trade_enabled,
  signal_auto_trade_directions: [...autoForm.value.directions],
  signal_auto_trade_strategies: [...autoForm.value.strategies],
  signal_auto_trade_timeframes: [...autoForm.value.timeframes],
  signal_auto_trade_confirmations: Number(autoForm.value.confirmations),
  signal_auto_trade_confirmation_window_seconds: Number(
    autoForm.value.confirmationWindowSeconds,
  ),
  signal_auto_trade_cooldown_seconds: Number(autoForm.value.cooldownSeconds),
  signal_auto_trade_value_usd: Number(autoForm.value.valueUsd),
  signal_auto_trade_max_positions: Number(autoForm.value.maxPositions),
})

const saveAutoConfig = async (): Promise<void> => {
  if (!autoFormValid.value || savingAuto.value) return
  savingAuto.value = true
  try {
    const response = await api.post<{ config?: Partial<SignalConfig> }>(
      '/api/signals/config',
      buildAutoConfigPayload(),
    )
    if (response.data.config) {
      config.value = mergeConfig({ ...config.value, ...response.data.config })
    }
    autoFormDirty.value = false
    syncAutoForm(config.value)
    snackbarStore.show({ message: '自动开仓配置已保存。', color: 'success' })
    pushLog('[前端] 信号自动开仓配置已保存。', 'success')
  } catch (error: unknown) {
    snackbarStore.show({
      message: '保存自动开仓配置失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    savingAuto.value = false
  }
}

const scanNow = async (): Promise<void> => {
  if (scanning.value) return
  scanning.value = true
  try {
    const response = await api.post<{ message?: string }>('/api/signals/scan')
    snackbarStore.show({
      message: response.data?.message ?? '扫描任务已提交。',
      color: 'success',
    })
    pushLog('[前端] 已提交信号扫描任务。', 'info')
    await fetchSignals(true)
  } catch (error: unknown) {
    const statusCode = getErrorStatus(error)
    const isConflict = statusCode === 409
    snackbarStore.show({
      message: isConflict
        ? '已有扫描任务正在运行，请稍后再试。'
        : '提交扫描失败: ' + getErrorMessage(error),
      color: isConflict ? 'warning' : 'error',
    })
  } finally {
    scanning.value = false
  }
}

const clearSignals = async (): Promise<void> => {
  if (clearing.value) return
  clearing.value = true
  try {
    await api.post('/api/signals/clear')
    signals.value = []
    snackbarStore.show({ message: '信号已清空。', color: 'success' })
    pushLog('[前端] 已清空信号列表。', 'info')
    await fetchSignals(true)
  } catch (error: unknown) {
    snackbarStore.show({
      message: '清空信号失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    clearing.value = false
  }
}

const stopPolling = (): void => {
  if (pollTimer !== undefined) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
}

const startPolling = (): void => {
  stopPolling()
  pollTimer = window.setInterval(() => {
    if (document.visibilityState === 'visible') {
      void fetchSignals(true)
    }
  }, POLL_INTERVAL_MS)
}

const onVisibilityChange = (): void => {
  if (document.visibilityState === 'visible') {
    void fetchSignals(true)
  }
}

onMounted(() => {
  void fetchSignals(true)
  startPolling()
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onUnmounted(() => {
  stopPolling()
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<style scoped>
.status-strip {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.72);
}
.dot-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: 0 0 auto;
}
.dot--on {
  background: rgb(var(--v-theme-long));
  box-shadow: 0 0 0 3px rgba(var(--v-theme-long), 0.16);
}
.dot--off {
  background: rgba(var(--v-theme-on-surface), 0.34);
}
.dot--warn {
  background: rgb(var(--v-theme-warning));
  box-shadow: 0 0 0 3px rgba(var(--v-theme-warning), 0.16);
}
.signal-shell {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
}
</style>
