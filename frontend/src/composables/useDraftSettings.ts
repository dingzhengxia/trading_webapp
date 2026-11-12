/**
 * 设置草稿模式（T11 / ARCH R-P2-4）。
 *
 * 原实现：表单双向直绑 settingsStore.settings + 3 个深 watch（自动保存 /
 * 排序 / 收起），store 同时充当「服务端数据」与「编辑缓冲」两个角色。
 * 草稿模式：
 * - `draft` = 深拷贝(settings)，表单只单向绑定 draft；
 * - `hydrated` 作为渲染闸门（settings 未灌入前不渲染表单）；
 * - 保存时与基线做 diff，只提交被改动的键（沿用原空值/NaN 过滤口径）；
 * - 服务端 settings 外部变化且当前无未保存编辑时自动重灌草稿。
 *
 * 模块级单例：ControlPanel 在 ConfigDrawer 的 general / rebalance 两个插槽
 * 各挂一个实例，两实例共享同一份草稿（与原先共享 settingsStore.settings 的
 * 语义一致）；内部 watcher 只注册一次，不随组件卸载反复创建。
 */
import { computed, ref, watch } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import type { UserSettings } from '@/models/types'
import { useSettingsStore } from '@/stores/settingsStore'
import { useSnackbarStore } from '@/stores/snackbar'
import { debounce } from '@/utils/debounce'
import { getErrorMessage } from '@/utils/errors'

const draft: Ref<UserSettings | null> = ref(null)
const baselineJson = ref('')

/** 服务端 settings 已灌入草稿，表单可以渲染 */
const hydrated: ComputedRef<boolean> = computed(() => draft.value !== null)

/** 草稿与基线是否存在未保存差异 */
const isDirty: ComputedRef<boolean> = computed(
  () => draft.value !== null && JSON.stringify(draft.value) !== baselineJson.value,
)

let watchersReady = false
let commitInFlight = false
let autoSave: ReturnType<typeof debounce> | null = null

const deepClone = (value: UserSettings): UserSettings => JSON.parse(JSON.stringify(value))

function hydrateFromSnapshot(snapshot: string): void {
  baselineJson.value = snapshot
  draft.value = deepClone(JSON.parse(snapshot) as UserSettings)
}

/** 与基线 diff 出被改动的键（沿用原整包保存的空值/NaN 过滤口径） */
function diffKeys(): Record<string, unknown> {
  if (!draft.value) return {}
  const current = draft.value as unknown as Record<string, unknown>
  let base: Record<string, unknown> = {}
  try {
    base = JSON.parse(baselineJson.value || '{}') as Record<string, unknown>
  } catch {
    base = {}
  }
  const changed: Record<string, unknown> = {}
  for (const key of Object.keys(current)) {
    if (JSON.stringify(current[key]) !== JSON.stringify(base[key])) {
      changed[key] = current[key]
    }
  }
  // 空字符串/空值/NaN 不提交：与原 saveGeneralSettings 的过滤行为一致，
  // 这些键保持服务端旧值（例如清空输入框不应把非法值写进配置）
  const payload: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(changed)) {
    if (value === '' || value === null || value === undefined) continue
    if (typeof value === 'number' && !Number.isFinite(value)) continue
    payload[key] = value
  }
  return payload
}

/**
 * 把草稿差异提交到后端（经 settingsStore.patchSettings 的 {ok, detail} 语义）。
 * @param force true=不做 dirty 检查直接提交（手动「保存」按钮）
 * @returns 是否提交成功（无差异视为成功）
 */
export async function commitDraft(force = false): Promise<boolean> {
  if (!draft.value || commitInFlight) return false
  if (!force && !isDirty.value) return true

  commitInFlight = true
  const store = useSettingsStore()
  const payload = diffKeys()
  let ok = true
  try {
    if (Object.keys(payload).length > 0) {
      const result = await store.patchSettings(payload as Partial<UserSettings>)
      ok = result.ok
      if (!ok) {
        useSnackbarStore().show({
          // 服务端原因（例如“open_maker_retries 超出允许范围 [0,10]”）必须原样展示
          message: `保存失败：${result.detail}`,
          color: 'error',
          timeout: 8000,
        })
      }
    }
  } catch (error) {
    ok = false
    useSnackbarStore().show({
      message: `保存失败：${getErrorMessage(error)}`,
      color: 'error',
      timeout: 8000,
    })
  }
  if (ok) {
    baselineJson.value = JSON.stringify(draft.value)
  }
  commitInFlight = false
  return ok
}

/** 立即丢弃草稿，重新从服务端 settings 灌入（外部数据刷新时使用） */
export function hydrateDraft(): void {
  const store = useSettingsStore()
  if (store.settings) {
    hydrateFromSnapshot(JSON.stringify(store.settings))
  }
}

function ensureWatchers(): void {
  if (watchersReady) return
  watchersReady = true
  const store = useSettingsStore()

  // 服务端 settings 变化且当前没有未保存草稿 → 重灌（首次灌入也在这里完成）。
  // 有未保存编辑时绝不重灌，避免把用户正在输入的内容覆盖掉。
  watch(
    () => store.settings,
    () => {
      if (!store.settings) return
      const snapshot = JSON.stringify(store.settings)
      if (draft.value === null || !isDirty.value) {
        hydrateFromSnapshot(snapshot)
      }
    },
    { deep: true, immediate: true },
  )

  // 草稿被编辑 → 防抖 diff 提交（替代原深 watch settingsStore.settings 自动保存）
  autoSave = debounce(() => {
    void commitDraft()
  }, 1500)
  watch(
    draft,
    () => {
      if (isDirty.value && autoSave) autoSave()
    },
    { deep: true },
  )
}

export interface UseDraftSettingsReturn {
  draft: Ref<UserSettings | null>
  hydrated: ComputedRef<boolean>
  isDirty: ComputedRef<boolean>
  /** 手动提交（force=true 时忽略 dirty 检查） */
  commitDraft: typeof commitDraft
  /** 立即提交尚在防抖窗口内的编辑（组件卸载前调用，避免“改完就切页”丢失） */
  flushDraftSave: () => void
}

/**
 * 设置草稿模式入口。多实例共享同一份模块级草稿；内部 watcher 只注册一次。
 */
export function useDraftSettings(): UseDraftSettingsReturn {
  ensureWatchers()
  return {
    draft,
    hydrated,
    isDirty,
    commitDraft,
    flushDraftSave: () => autoSave?.flush(),
  }
}
