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
import type { ProtectionConfig, ProtectionEventRow, ProtectionStatus } from '@/models/types'

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

/**
 * 持久化台账事件（DB 里那份，跨重启保留）。
 * v2.recent_actions 只在内存里、重启即空，且不含「仓位怎么没的」；
 * 「为什么被平了」只能靠这份事件回看（stop 上移到哪 → flat 触发）。
 */
const events = ref<ProtectionEventRow[]>([])

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

type FormState = typeof form

const formKeys = Object.keys(form) as (keyof FormState)[]
/** 动态读写用视图（key 来自运行期字段名，类型无法静态收敛） */
const rawForm = form as unknown as Record<string, unknown>

/**
 * 后端最后一次确认落库的值 = 脏值判定基线。
 * 10s 轮询拿到的配置只在与基线一致（无未保存改动）时才回填表单，
 * 否则用户刚改的数字/开关会被静默覆盖（曾导致开关「打开过一会自己关掉」）。
 */
const saved = ref<Record<string, unknown>>({})

const valueKey = (value: unknown): string =>
  Array.isArray(value) ? value.join(',') : String(value)

function copyValue(value: unknown): unknown {
  return Array.isArray(value) ? [...value] : value
}

/** 把当前表单视为已落库状态 */
function syncSaved(): void {
  const next: Record<string, unknown> = {}
  for (const key of formKeys) next[key as string] = copyValue(form[key])
  saved.value = next
}

/**
 * 与基线不一致的字段名（数值参数改动后需要手动保存）。
 * 基线里没有的字段不参与比较：首次加载前基线为空，此时不应算「未保存」。
 */
const dirtyKeys: ComputedRef<string[]> = computed(() =>
  formKeys
    .filter((key) => {
      const baseline = saved.value[key as string]
      return baseline !== undefined && valueKey(form[key]) !== valueKey(baseline)
    })
    .map(String),
)

const isDirty: ComputedRef<boolean> = computed(() => dirtyKeys.value.length > 0)

/** 放弃未保存改动，回到后端已落库的值 */
function revertChanges(): void {
  for (const key of formKeys) {
    const baseline = saved.value[key as string]
    if (baseline !== undefined) rawForm[key as string] = copyValue(baseline)
  }
}

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
  syncSaved()
}

async function fetchEvents(limit = 80): Promise<void> {
  try {
    const response = await api.get<{ events: ProtectionEventRow[] }>(
      ENDPOINTS.protectionEvents,
      { params: { limit } },
    )
    events.value = response.data.events ?? []
  } catch (error: unknown) {
    console.warn('获取仓位保护事件失败:', getErrorMessage(error))
  }
}

async function fetchStatus(force = false): Promise<void> {
  try {
    const response = await api.get<ProtectionStatus>(ENDPOINTS.protection)
    status.value = response.data
    // 有未保存改动时只用服务端数据刷新运行状态，不回填表单
    if (force || !isDirty.value) applyConfig(response.data.config ?? {})
  } catch (error: unknown) {
    console.warn('获取仓位保护状态失败:', getErrorMessage(error))
  }
  // 事件列表独立请求：状态拿到就先渲染，事件慢一点不阻塞
  void fetchEvents()
}

/** 写路径 1：整包保存参数表单（保存按钮） */
async function saveConfig(): Promise<boolean> {
  saving.value = true
  try {
    await api.post(ENDPOINTS.protectionConfig, { ...form })
    useSnackbarStore().show({ message: '仓位保护参数已保存并生效。', color: 'success' })
    await fetchStatus(true)
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
    // patch 成功即视为该字段已落库，避免它被算成「未保存」而挡住后续轮询回填
    for (const [key, value] of Object.entries(partial)) {
      if (formKeys.includes(key as keyof FormState)) saved.value[key] = copyValue(value)
    }
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

/**
 * 开关类参数：改动即写回（失败的则回滚到改动前的值）。
 * 这类开关是二值状态，用户预期是「拨了就算数」，不该等「保存参数」。
 */
async function applySwitch<K extends keyof FormState>(
  key: K,
  value: FormState[K],
): Promise<void> {
  const previous = rawForm[key as string]
  rawForm[key as string] = value
  const result = await patchConfig({ [key as string]: value })
  if (!result.ok) rawForm[key as string] = previous
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
  events: Ref<ProtectionEventRow[]>
  form: typeof form
  saving: Ref<boolean>
  isV2: ComputedRef<boolean>
  /** 数值参数有未保存改动（开关类改动即时生效，不计入） */
  isDirty: ComputedRef<boolean>
  dirtyKeys: ComputedRef<string[]>
  fetchStatus: typeof fetchStatus
  fetchEvents: typeof fetchEvents
  saveConfig: typeof saveConfig
  patchConfig: typeof patchConfig
  applySwitch: typeof applySwitch
  revertChanges: typeof revertChanges
  onToggleDryRun: typeof onToggleDryRun
  onToggleEnabled: typeof onToggleEnabled
}

/** 仓位保护配置域状态与写入口（模块级单例） */
export function useProtectionConfig(): UseProtectionConfigReturn {
  return {
    status,
    events,
    form,
    saving,
    isV2,
    isDirty,
    dirtyKeys,
    fetchStatus,
    fetchEvents,
    saveConfig,
    patchConfig,
    applySwitch,
    revertChanges,
    onToggleDryRun,
    onToggleEnabled,
  }
}
