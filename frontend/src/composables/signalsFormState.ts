/**
 * 信号配置抽屉的三个表单（扫描范围 / 推送 / 出场 / 自动开仓）的共享状态与同步（T11）。
 *
 * 纯状态 + 同步函数，不含 REST 调用；写动作见 useSignalsActions.ts，
 * REST 原语见 useSignalsConfig.ts。模块级单例，与原单页持有行为一致。
 */
import { computed, ref } from 'vue'
import type { ComputedRef } from 'vue'
import type { AutoTradeForm } from '@/components/signals/PushAutoPanel.vue'
import type { PaperForm } from '@/components/signals/ExitParamsPanel.vue'
import type {
  SignalConfig,
  SignalTracking,
} from '@/models/types'
import { defaultSignalConfig } from '@/services/signalsData'
import { useSettingsStore } from '@/stores/settingsStore'

// 扫描范围表单
export const savingScan = ref(false)
export const savingScope = ref(false)
export const scopeDirty = ref(false)
export const scanStaticSymbols = ref<string[]>([...defaultSignalConfig.signal_scan_static_symbols])
export const scopeTopN = ref<number>(defaultSignalConfig.signal_scan_top_n)
export const scopeTimeframes = ref<string[]>([...defaultSignalConfig.signal_scan_timeframes])

// 推送表单
export const savingDingtalkPush = ref(false)
export const savingPushConfig = ref(false)
export const pushVolumeInput = ref<number>(2)
export const pushVolumeDirty = ref(false)

// 出场规则表单
export const savingPaperConfig = ref(false)
export const savingPaperToggle = ref(false)
export const savingLiveTimeout = ref(false)
export const savingSltpGuard = ref(false)
export const paperDirty = ref(false)
export const paperForm = ref<PaperForm>({ slAtr: 1.5, tpR: 2, maxBars: 6, atrTimeframe: '4h' })

// 自动开仓表单
export const savingAutoTrade = ref(false)
export const savingAuto = ref(false)
export const autoFormDirty = ref(false)
export const autoForm = ref<AutoTradeForm>({
  directions: [...defaultSignalConfig.signal_auto_trade_directions],
  strategies: [...defaultSignalConfig.signal_auto_trade_strategies],
  timeframes: [...defaultSignalConfig.signal_auto_trade_timeframes],
  confirmations: defaultSignalConfig.signal_auto_trade_confirmations,
  confirmationWindowSeconds: defaultSignalConfig.signal_auto_trade_confirmation_window_seconds,
  cooldownSeconds: defaultSignalConfig.signal_auto_trade_cooldown_seconds,
  valueUsd: defaultSignalConfig.signal_auto_trade_value_usd,
  maxPositions: defaultSignalConfig.signal_auto_trade_max_positions,
})

// ---------------------------------------------------------------------------
// 表单校验
// ---------------------------------------------------------------------------
export const scopeValid: ComputedRef<boolean> = computed(
  () =>
    scopeTimeframes.value.length > 0 &&
    Number(scopeTopN.value) >= 1 &&
    Number(scopeTopN.value) <= 500,
)

export const paperFormValid: ComputedRef<boolean> = computed(
  () =>
    Number(paperForm.value.slAtr) >= 0.2 &&
    Number(paperForm.value.slAtr) <= 10 &&
    Number(paperForm.value.tpR) >= 0.5 &&
    Number(paperForm.value.tpR) <= 10 &&
    Number(paperForm.value.maxBars) >= 1 &&
    Number(paperForm.value.maxBars) <= 100,
)

export const autoFormValid: ComputedRef<boolean> = computed(() => {
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

export const normalizeSymbolInput = (value: string): string =>
  value.trim().toUpperCase().split('/')[0].split(':')[0]

/** 下拉选项 = 备选总池 ∪ 已选（保证已选但不在池内的币种照常显示） */
export const staticSymbolItems: ComputedRef<string[]> = computed<string[]>(() => {
  const settingsStore = useSettingsStore()
  const pool = (settingsStore.availableCoins ?? [])
    .map((item) => normalizeSymbolInput(item))
    .filter(Boolean)
  return [...new Set([...scanStaticSymbols.value, ...pool])].sort()
})

export const markAutoFormDirty = (): void => {
  autoFormDirty.value = true
}

// ---------------------------------------------------------------------------
// 服务端数据 → 表单回填（Object.assign 只改字段、不换对象：子面板持有的是
// 同一个对象引用，整体替换会让子面板读写到旧对象。有未保存编辑时不回填，
// 避免 10 秒轮询覆盖用户输入。）
// ---------------------------------------------------------------------------
export const syncPaperForm = (next: SignalTracking, exitTimeframe: string): void => {
  if (paperDirty.value) return
  Object.assign(paperForm.value, {
    slAtr: next.params.sl_atr,
    tpR: next.params.tp_r,
    maxBars: next.params.max_bars,
    atrTimeframe: exitTimeframe,
  })
}

export const syncAutoForm = (nextConfig: SignalConfig): void => {
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

export const syncScopeForm = (nextConfig: SignalConfig): void => {
  if (scopeDirty.value) return
  scanStaticSymbols.value = [...nextConfig.signal_scan_static_symbols]
  scopeTopN.value = nextConfig.signal_scan_top_n
  scopeTimeframes.value = [...nextConfig.signal_scan_timeframes]
}
