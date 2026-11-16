// frontend/src/composables/usePolling.ts
import { onMounted, onUnmounted } from 'vue'

export interface UsePollingOptions {
  /** 挂载后立即执行一次（默认 false） */
  immediate?: boolean
  /** 仅页面可见时执行（默认 false；仪表盘等允许后台挂起的轮询用它） */
  visibility?: boolean
  /** 挂载后自动启动（默认 true）；需要按业务状态手动启停时传 false */
  autoStart?: boolean
}

/**
 * 统一轮询：负责 interval 的创建与**卸载清理**，避免各页面各写一份
 * "pollTimer + onUnmounted clearInterval" 而漏清理造成泄漏。
 */
export function usePolling(
  fn: () => void | Promise<void>,
  intervalMs: number,
  options: UsePollingOptions = {},
): { start: () => void; stop: () => void } {
  let timer: number | undefined

  const tick = (): void => {
    if (options.visibility && document.visibilityState !== 'visible') return
    void fn()
  }
  const start = (): void => {
    if (timer === undefined) timer = window.setInterval(tick, intervalMs)
  }
  const stop = (): void => {
    if (timer !== undefined) {
      window.clearInterval(timer)
      timer = undefined
    }
  }

  onMounted(() => {
    if (options.immediate) void fn()
    if (options.autoStart !== false) start()
  })
  onUnmounted(stop)

  return { start, stop }
}
