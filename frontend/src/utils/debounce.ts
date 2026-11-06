// frontend/src/utils/debounce.ts
// 本地 debounce 实现，替代原先的第三方 debounce 工具（无网络环境不新增依赖）。

export interface DebouncedFunction {
  (...args: unknown[]): void
  /** 取消尚未执行的调用 */
  cancel(): void
  /** 立即执行尚未执行的调用（若有） */
  flush(): void
}

/**
 * 创建一个防抖函数：在最后一次调用后 wait 毫秒才执行。
 * @param fn 需要防抖的函数
 * @param wait 等待毫秒数，默认 0
 */
export function debounce<F extends (...args: unknown[]) => unknown>(
  fn: F,
  wait = 0,
): DebouncedFunction {
  let timer: ReturnType<typeof setTimeout> | undefined
  let pendingArgs: unknown[] | null = null

  const invoke = (): unknown => {
    timer = undefined
    if (pendingArgs === null) return undefined
    const args = pendingArgs
    pendingArgs = null
    return (fn as (...args: unknown[]) => unknown)(...args)
  }

  const debounced = ((...args: unknown[]): void => {
    pendingArgs = args
    if (timer !== undefined) {
      clearTimeout(timer)
    }
    timer = setTimeout(invoke, wait)
  }) as DebouncedFunction

  debounced.cancel = (): void => {
    if (timer !== undefined) {
      clearTimeout(timer)
      timer = undefined
    }
    pendingArgs = null
  }

  debounced.flush = (): void => {
    if (timer === undefined) return
    clearTimeout(timer)
    invoke()
  }

  return debounced
}
