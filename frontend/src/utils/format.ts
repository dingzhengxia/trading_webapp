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

/** 毫秒时间戳 → 时分秒（24 小时制）：“已保存 hh:mm:ss” 这类状态提示专用 */
export function formatClockTime(value: number | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleTimeString('zh-CN', { hour12: false })
}

/** ISO 时间字符串 → 本地时间字符串；无法解析时原样返回 */
export function formatIsoTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

/**
 * 带符号的数值：**永远**给出 + 或 −。
 *
 * 盈亏必须带符号 —— 只靠红绿区分赚赔，等于把色弱用户（约 8% 男性）排除在外。
 * 负号使用真正的减号 U+2212，等宽字体下比连字符窄且垂直居中，右对齐时列不会歪。
 */
export function formatSigned(value: number | string | null | undefined, digits = 2): string {
  const num = Number(value)
  if (!Number.isFinite(num)) return '—'
  const body = Math.abs(num).toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
  return num < 0 ? `−${body}` : `+${body}`
}

/** 带符号的百分比，与 formatSigned 同口径 */
export function formatSignedPercent(
  value: number | string | null | undefined,
  digits = 2,
): string {
  const num = Number(value)
  if (!Number.isFinite(num)) return '—'
  const body = Math.abs(num).toFixed(digits)
  return num < 0 ? `−${body}%` : `+${body}%`
}

/**
 * 以下为 T10 新增：承接组件里散落的 toFixed / toLocaleString 显示格式化
 * （eslint no-restricted-syntax 禁止组件直接调用，统一走本文件）。
 */

/** 固定小数位（无千分位），与 toFixed 显示口径一致；非法值按 0 处理 */
export function formatFixed(value: number | string | null | undefined, digits = 2): string {
  const num = Number(value)
  if (!Number.isFinite(num)) return (0).toFixed(digits)
  return num.toFixed(digits)
}

/** 开仓价：千分位 + 最多 6 位小数；非法值按 0 处理 */
export function formatQuantity(value: number | string | null | undefined): string {
  const num = Number(value)
  if (!Number.isFinite(num)) return '0'
  return num.toLocaleString('en-US', { maximumFractionDigits: 6 })
}

/** 价格自适应精度：≥1000 保留 2 位小数，否则最多 6 位；非法值显示破折号 */
export function formatAutoPrecision(value: number | string | null | undefined): string {
  const num = Number(value)
  if (!Number.isFinite(num)) return '—'
  const digits = Math.abs(num) >= 1000 ? 2 : 6
  return num.toLocaleString('en-US', { maximumFractionDigits: digits })
}

/** 美元金额（zh-CN 千分位 + 最多 2 位小数）；非法值显示破折号 */
export function formatUsdLoose(value: number | string | null | undefined): string {
  const num = Number(value)
  if (!Number.isFinite(num)) return '—'
  return `$${num.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`
}

/**
 * 美元金额·紧凑版：≥100 万压到一位小数并用 M 后缀（$1.2M），其余保持千分位（$2,000）。
 * 用于抽屉动作区的摘要条这类只有一行宽度的位置；非法值显示破折号。
 */
export function formatUsdCompact(value: number | string | null | undefined): string {
  const num = Number(value)
  if (!Number.isFinite(num)) return '—'
  if (Math.abs(num) >= 1_000_000) {
    const millions = num / 1_000_000
    return `$${millions.toLocaleString('en-US', { maximumFractionDigits: 1 })}M`
  }
  return `$${num.toLocaleString('en-US', { maximumFractionDigits: 2 })}`
}

/** Unix 毫秒级时间戳 → 本地时间字符串 */
export function formatMillis(value: number | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

/** 数值取整到固定小数位（返回 number，用于权重分配等计算而非展示） */
export function roundTo(value: number, digits = 2): number {
  const factor = 10 ** digits
  return Math.round((value + Number.EPSILON) * factor) / factor
}
