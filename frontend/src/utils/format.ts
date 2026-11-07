/**
 * 数字 / 时间格式化。
 *
 * 原先 ManualTradeView / ProtectionView / ReportsView / SignalsView 各写了一份
 * 语义略有差异的同名函数（formatNumber / formatTime），这里按用途拆开统一实现。
 */

/** 金额：固定两位小数，非法值按 0.00 处理（手动交易页目标价值用） */
export function formatAmount(value: number | string | null | undefined): string {
  const num = Number(value)
  if (!Number.isFinite(num)) return '0.00'
  return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** 数值：0 / 空 / 非法值显示破折号，适合表格里的价格与百分比 */
export function formatNumberOrDash(
  value: number | string | null | undefined,
  digits = 2,
): string {
  const num = Number(value)
  if (!Number.isFinite(num) || num === 0) return '—'
  return num.toLocaleString('en-US', { maximumFractionDigits: digits })
}

/** Unix 秒级时间戳 → 本地时间字符串 */
export function formatUnixSeconds(value: number | null | undefined): string {
  if (!value) return '—'
  return new Date(value * 1000).toLocaleString('zh-CN', { hour12: false })
}

/** ISO 时间字符串 → 本地时间字符串；无法解析时原样返回 */
export function formatIsoTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}
