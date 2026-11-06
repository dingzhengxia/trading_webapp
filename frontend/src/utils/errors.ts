// frontend/src/utils/errors.ts
// 统一从 unknown 错误中提取可展示的中文/接口错误信息，避免使用 any。

interface ApiErrorLike {
  message?: unknown
  response?: {
    status?: unknown
    data?: {
      detail?: unknown
    }
  }
}

/**
 * 把 axios / Error / 任意抛出值转成可读的错误字符串。
 */
export function getErrorMessage(error: unknown): string {
  if (typeof error === 'string') return error
  if (error && typeof error === 'object') {
    const err = error as ApiErrorLike
    const detail = err.response?.data?.detail
    if (typeof detail === 'string' && detail.length > 0) return detail
    if (Array.isArray(detail)) return JSON.stringify(detail)
    if (typeof err.message === 'string' && err.message.length > 0) return err.message
  }
  return String(error)
}

/**
 * 从 axios / 任意抛出值中提取 HTTP 状态码（无则 undefined）。
 */
export function getErrorStatus(error: unknown): number | undefined {
  if (error && typeof error === 'object') {
    const response = (error as ApiErrorLike).response
    if (response && typeof response.status === 'number') {
      return response.status
    }
  }
  return undefined
}
