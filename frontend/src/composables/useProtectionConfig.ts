/**
 * 仓位保护配置域的唯一写入口（T11 / ARCH R-P2-2）。
 *
 * 原 ProtectionView 里 3 处 `api.post(protectionConfig, ...)` 整包/单字段直写，
 * 收敛为本 composable 的 `saveConfig`（整包）与 `patchConfig`（局部 patch，
 * 仿 settingsStore.patchSettings 的 {ok, detail} 语义）两条写路径，
 * 组件内禁止再出现裸的保护配置 POST。
 *
 * 状态为模块级单例：StatusCard / RiskSettingsPanel / ConfigForm /
 * ProtectionView 共享同一份 status 与 form，与原先单页持有行为一致。
 */
import { computed, reactive, ref } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import api from '@/services/api'
import { ENDPOINTS } from '@/services/endpoints'
import { useSnackbarStore } from '@/stores/snackbar'
import { getErrorMessage } from '@/utils/errors'
import type { ProtectionConfig, ProtectionStatus } from '@/models/types'

const status = ref<ProtectionStatus>({
  enabled: false,
  running: false,
  started_at: null,
  last_error: null,
  timeframe: null,
  positions: [],
  api: {
    request_count: 0,
    error_count: 0,
    failures: 0,
    circuit_open: false,
    circuit_open_until: 0,
    cooldown_until: 0,
  },
  config: {} as ProtectionConfig,
})

const saving = ref(false)

/** 参数表单（40 个控件的单一份草稿，ConfigForm 直接绑定） */
const form = reactive({
  engine_version: 'v2',
  dry_run: false,
  v2_timeframe: '2h',
  v2_poll_interval_sec: 3,
  tier_ratios: [0.15, 0.2, 0.25, 0.4] as number[],
  tier_confirm_sec: [30, 45, 60, 0] as number[],
  risk_min_pct: 0.015,
  risk_max_pct: 0.08,
  breakeven_trigger_r: 0.5,
  trailing_atr_mult: 2.5,
  timeframe: '2h',
  tp1_r_multiple: 1,
  tp2_r_multiple: 2,
  tp3_r_multiple: 3,
  t1_structure_lookback: 7,
  t2_structure_lookback: 26,
  t3_structure_lookback: 83,
  structure_buffer_atr: 0.5,
  profit_protection_enabled: true,
  emergency_enabled: true,
  exchange_hard_stop_enabled: true,
  hard_stop_min_distance_pct: 0.05,
  // 双轨治理：守护端接管开仓端遗留 SL/TP/TS 条件单（默认关，不改变现有行为）
  take_over_external_stops: false,
  // 连续移动止损：'step'=阶梯跳（现状）| 'continuous'=浮盈达标后按 ATR 平滑追踪
  trailing_stop_mode: 'step' as 'step' | 'continuous',
  trailing_trigger_r: 1,
})

/** 运行中引擎是否为 v2（状态优先，回退表单值） */
const isV2: ComputedRef<boolean> = computed(
  () => (status.value.engine_version ?? form.engine_version ?? 'v2') === 'v2',
)

function applyConfig(config: Partial<ProtectionConfig>): void {
  if (typeof config.timeframe === 'string') form.timeframe = config.timeframe
  if (typeof config.engine_version === 'string') {
    form.engine_version = config.engine_version === 'v1' ? 'v1' : 'v2'
  }
  if (typeof config.dry_run === 'boolean') form.dry_run = config.dry_run
  if (typeof config.v2_timeframe === 'string') form.v2_timeframe = config.v2_timeframe
  if (Array.isArray(config.tier_ratios) && config.tier_ratios.length === 4) {
    form.tier_ratios = config.tier_ratios.map((x) => Number(x))
  }
  if (Array.isArray(config.tier_confirm_sec) && config.tier_confirm_sec.length === 4) {
    form.tier_confirm_sec = config.tier_confirm_sec.map((x) => Number(x))
  }
  for (const key of [
    'v2_poll_interval_sec',
    'risk_min_pct',
    'risk_max_pct',
    'breakeven_trigger_r',
    'trailing_atr_mult',
  ] as const) {
    const value = Number(config[key])
    if (Number.isFinite(value)) form[key] = value
  }
  for (const key of [
    'tp1_r_multiple',
    'tp2_r_multiple',
    'tp3_r_multiple',
    't1_structure_lookback',
    't2_structure_lookback',
    't3_structure_lookback',
    'structure_buffer_atr',
    'hard_stop_min_distance_pct',
  ] as const) {
    const value = Number(config[key])
    if (Number.isFinite(value)) form[key] = value
  }
  for (const key of [
    'profit_protection_enabled',
    'emergency_enabled',
    'exchange_hard_stop_enabled',
    'take_over_external_stops',
  ] as const) {
    if (typeof config[key] === 'boolean') form[key] = config[key] as boolean
  }
  if (
    config.trailing_stop_mode === 'step' || config.trailing_stop_mode === 'continuous'
  ) {
    form.trailing_stop_mode = config.trailing_stop_mode
  }
  const triggerR = Number(config.trailing_trigger_r)
  if (Number.isFinite(triggerR) && triggerR > 0) form.trailing_trigger_r = triggerR
}

async function fetchStatus(): Promise<void> {
  try {
    const response = await api.get<ProtectionStatus>(ENDPOINTS.protection)
    status.value = response.data
    applyConfig(response.data.config ?? {})
  } catch (error: unknown) {
    console.warn('获取仓位保护状态失败:', getErrorMessage(error))
  }
}

/** 写路径 1：整包保存参数表单（保存按钮） */
async function saveConfig(): Promise<boolean> {
  saving.value = true
  try {
    await api.post(ENDPOINTS.protectionConfig, { ...form })
    useSnackbarStore().show({ message: '仓位保护参数已保存并生效。', color: 'success' })
    await fetchStatus()
    return true
  } catch (error: unknown) {
    useSnackbarStore().show({ message: getErrorMessage(error), color: 'error' })
    return false
  } finally {
    saving.value = false
  }
}

/** 写路径 2：局部 patch（开关类即时生效），返回 {ok, detail} 语义 */
async function patchConfig(
  partial: Record<string, unknown>,
): Promise<{ ok: boolean; detail: string }> {
  saving.value = true
  try {
    await api.post(ENDPOINTS.protectionConfig, partial)
    await fetchStatus()
    return { ok: true, detail: '' }
  } catch (error: unknown) {
    const detail = getErrorMessage(error)
    useSnackbarStore().show({ message: detail, color: 'error' })
    return { ok: false, detail }
  } finally {
    saving.value = false
  }
}

async function onToggleDryRun(value: boolean | null): Promise<void> {
  form.dry_run = value === true
  const result = await patchConfig({ dry_run: value === true })
  if (result.ok) {
    useSnackbarStore().show({
      message: value
        ? '演练模式已开启：引擎照常判断并记录动作，但不会真实下单。'
        : '演练模式已关闭：风控动作将真实执行。',
      color: value ? 'warning' : 'success',
    })
  }
}

async function onToggleEnabled(value: boolean | null): Promise<void> {
  const result = await patchConfig({ enabled: value === true })
  if (result.ok) {
    useSnackbarStore().show({
      message: value ? '仓位保护已启用，引擎将在数秒内启动。' : '仓位保护已停用。',
      color: 'success',
    })
  }
}

export interface UseProtectionConfigReturn {
  status: Ref<ProtectionStatus>
  form: typeof form
  saving: Ref<boolean>
  isV2: ComputedRef<boolean>
  fetchStatus: typeof fetchStatus
  saveConfig: typeof saveConfig
  patchConfig: typeof patchConfig
  onToggleDryRun: typeof onToggleDryRun
  onToggleEnabled: typeof onToggleEnabled
}

/** 仓位保护配置域状态与写入口（模块级单例） */
export function useProtectionConfig(): UseProtectionConfigReturn {
  return {
    status,
    form,
    saving,
    isV2,
    fetchStatus,
    saveConfig,
    patchConfig,
    onToggleDryRun,
    onToggleEnabled,
  }
}
