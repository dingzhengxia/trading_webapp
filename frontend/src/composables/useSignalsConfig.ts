/**
 * 信号配置域核心层（T11 / ARCH R-P2-2）：共享状态 + 数据拉取 + REST 写路径原语。
 *
 * 三层拆分（依赖方向单向，无环）：
 * - `signalsFormState.ts`：表单状态 / 校验 / 回填（纯状态，无 REST）；
 * - 本文件：模块级单例共享状态、fetchSignals、以及配置域仅有的两条写路径——
 *   `patchSignalsConfig`（signals/config patch）与 `toggleSignalAutoTrade`（auto-trade 开关）；
 * - `useSignalsActions.ts`：各业务动作（开关 / 保存表单 / 扫描 / 清空），
 *   全部经由上述两条写路径落库。
 *
 * 乐观更新 → patch → 失败回滚 的公共骨架由 `runOptimisticPatch` 统一实现。
 */
import { computed, ref } from 'vue'
import api from '@/services/api'
import { ENDPOINTS } from '@/services/endpoints'
import {
  defaultSignalConfig,
  defaultSignalStatus,
  emptyLiveExit,
  emptyPushStatus,
  emptyTracking,
  mergeConfig,
  mergePushStatus,
  mergeStatus,
  mergeTracking,
  normalizeSignals,
} from '@/services/signalsData'
import type {
  LiveExitStatus,
  SignalConfig,
  SignalPushStatus,
  SignalRecord,
  SignalStatus,
  SignalTracking,
} from '@/models/types'
import type { SignalsResponse } from '@/models/types'
import { useSnackbarStore } from '@/stores/snackbar'
import { useUiStore } from '@/stores/uiStore'
import { getErrorMessage, getErrorStatus } from '@/utils/errors'
import { formatIsoTime as formatTime } from '@/utils/format'
import { directionLabel } from '@/utils/tone'
import {
  pushVolumeDirty,
  pushVolumeInput,
  syncAutoForm,
  syncPaperForm,
  syncScopeForm,
} from './signalsFormState'

// ---------------------------------------------------------------------------
// 共享状态（模块级单例）：视图与子面板共享同一份数据，与原先单页持有行为一致
// ---------------------------------------------------------------------------
const status = ref<SignalStatus>({ ...defaultSignalStatus })
const signals = ref<SignalRecord[]>([])
const config = ref<SignalConfig>({ ...defaultSignalConfig })
const pushStatus = ref<SignalPushStatus>(emptyPushStatus())
const tracking = ref<SignalTracking>(emptyTracking())
const liveExit = ref<LiveExitStatus>(emptyLiveExit())

const loading = ref(false)
const scanning = ref(false)
const clearing = ref(false)
const directionFilter = ref<string>('all')

let pollTimer: number | undefined

// ---------------------------------------------------------------------------
// 派生值
// ---------------------------------------------------------------------------
const autoTradeEnabled = computed(() => config.value.signal_auto_trade_enabled)
const paperEnabled = computed(() => tracking.value.params.enabled)
const liveTimeoutEnabled = computed(() => liveExit.value.enabled)
const sltpGuardEnabled = computed(() => liveExit.value.guard_enabled)
const exitMode = computed(() => config.value.signal_exit_mode)

const winRateText = computed(() => {
  const rate = tracking.value.paper_stats.win_rate
  return rate == null ? '—' : `${rate}%`
})
const winRateTone = computed<'up' | 'down' | 'neutral'>(() => {
  const rate = tracking.value.paper_stats.win_rate
  if (rate == null) return 'neutral'
  return rate >= 50 ? 'up' : 'down'
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

// ---------------------------------------------------------------------------
// 数据拉取（10 秒轮询与手动刷新共用）
// ---------------------------------------------------------------------------
const pushLog = (message: string, level: 'info' | 'success' | 'warning' | 'error'): void => {
  useUiStore().logStore.addLog({
    message,
    level,
    timestamp: new Date().toLocaleTimeString(),
  })
}

const fetchSignals = async (silent: boolean): Promise<void> => {
  if (!silent) loading.value = true
  try {
    const response = await api.get<SignalsResponse>(ENDPOINTS.signals)
    const data = response.data
    status.value = mergeStatus(data.status)
    signals.value = normalizeSignals(data.signals)
    const nextConfig = mergeConfig(data.config)
    config.value = nextConfig
    pushStatus.value = mergePushStatus(data.push)
    if (!pushVolumeDirty.value) pushVolumeInput.value = pushStatus.value.signal_push_volume_multiplier
    tracking.value = mergeTracking(data.tracking)
    liveExit.value = data.live_exit ?? emptyLiveExit()
    // 回填三个表单（有未保存编辑时由 sync* 内部跳过，避免轮询覆盖用户输入）
    syncPaperForm(tracking.value, config.value.signal_live_exit_timeframe)
    syncScopeForm(nextConfig)
    syncAutoForm(nextConfig)
  } catch (error: unknown) {
    if (!silent) {
      useSnackbarStore().show({
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

// ---------------------------------------------------------------------------
// 写路径原语：本配置域仅有的两条 REST 写入口 + 乐观更新骨架
// ---------------------------------------------------------------------------
const applyMergedConfig = (raw: { config?: Partial<SignalConfig> } | undefined): void => {
  if (raw?.config) {
    config.value = mergeConfig({ ...config.value, ...raw.config })
  }
}

/** 配置域唯一写路径 1：signals/config patch（返回 {ok, detail} 语义） */
const patchSignalsConfig = async (
  payload: Record<string, unknown>,
): Promise<{ ok: boolean; detail: string; config?: Partial<SignalConfig> }> => {
  try {
    const response = await api.post<{ config?: Partial<SignalConfig> }>(
      ENDPOINTS.signalsConfig,
      payload,
    )
    applyMergedConfig(response.data)
    return { ok: true, detail: '', config: response.data?.config }
  } catch (error: unknown) {
    return { ok: false, detail: getErrorMessage(error) }
  }
}

/** 配置域唯一写路径 2：auto-trade 开关端点 */
const toggleSignalAutoTrade = async (enabled: boolean): Promise<{ ok: boolean; detail: string }> => {
  try {
    await api.post(ENDPOINTS.signalsAutoTrade, { enabled })
    return { ok: true, detail: '' }
  } catch (error: unknown) {
    return { ok: false, detail: getErrorMessage(error) }
  }
}

interface OptimisticPatchOptions {
  /** 乐观写入（失败时由 revert 回滚） */
  apply: () => void
  /** 回滚乐观写入 */
  revert: () => void
  payload: Record<string, unknown>
  /** 成功提示 */
  successMessage: string
  successLevel?: 'info' | 'success' | 'warning' | 'error'
  /** 失败提示前缀（自动拼 detail） */
  failLabel: string
  logMessage?: string
}

/** 乐观更新 → patch → 失败回滚 的统一骨架（原 15 处单字段 post 的公共部分） */
const runOptimisticPatch = async (options: OptimisticPatchOptions): Promise<boolean> => {
  options.apply()
  const result = await patchSignalsConfig(options.payload)
  if (result.ok) {
    if (options.successMessage) {
      useSnackbarStore().show({
        message: options.successMessage,
        color: options.successLevel ?? 'success',
      })
    }
    if (options.logMessage) pushLog(options.logMessage, options.successLevel ?? 'info')
    await fetchSignals(true)
  } else {
    options.revert()
    useSnackbarStore().show({
      message: `${options.failLabel}: ${result.detail}`,
      color: 'error',
    })
  }
  return result.ok
}

// ---------------------------------------------------------------------------
// 扫描 / 清空 / 轮询
// ---------------------------------------------------------------------------
const scanNow = async (): Promise<void> => {
  if (scanning.value) return
  scanning.value = true
  try {
    const response = await api.post<{ message?: string }>(ENDPOINTS.signalsScan)
    useSnackbarStore().show({
      message: response.data?.message ?? '扫描任务已提交。',
      color: 'success',
    })
    pushLog('[前端] 已提交信号扫描任务。', 'info')
    await fetchSignals(true)
  } catch (error: unknown) {
    const isConflict = getErrorStatus(error) === 409
    useSnackbarStore().show({
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
    await api.post(ENDPOINTS.signalsClear)
    signals.value = []
    useSnackbarStore().show({ message: '信号已清空。', color: 'success' })
    pushLog('[前端] 已清空信号列表。', 'info')
    await fetchSignals(true)
  } catch (error: unknown) {
    useSnackbarStore().show({
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
  }, 10000)
}

const onVisibilityChange = (): void => {
  if (document.visibilityState === 'visible') {
    void fetchSignals(true)
  }
}

/** 信号配置域核心层：共享状态 + 数据拉取 + 写路径原语（模块级单例） */
export function useSignalsConfig() {
  return {
    // 共享状态
    status,
    signals,
    config,
    pushStatus,
    tracking,
    liveExit,
    loading,
    scanning,
    clearing,
    directionFilter,
    // 派生值
    autoTradeEnabled,
    paperEnabled,
    liveTimeoutEnabled,
    sltpGuardEnabled,
    exitMode,
    winRateText,
    winRateTone,
    filteredSignals,
    lastAutoOpenText,
    // 数据拉取
    fetchSignals,
    refresh,
    pushLog,
    // 写路径原语
    patchSignalsConfig,
    toggleSignalAutoTrade,
    runOptimisticPatch,
    // 扫描 / 清空 / 轮询
    scanNow,
    clearSignals,
    startPolling,
    stopPolling,
    onVisibilityChange,
  }
}
