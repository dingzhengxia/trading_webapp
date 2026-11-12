/**
 * 色彩语义映射 · 唯一判色入口
 *
 * 铁律：模板里不允许再出现 `x >= 0 ? 'text-success' : 'text-error'` 这种写法。
 * 红色同时表示「做空」和「亏损」时，用户扫读会把方向当成盈亏；
 * 这里把两条通道彻底分开：
 *   · 方向 → 箭头图标 + 文案 + 色（三者同时给出，色盲也能读）
 *   · 盈亏 → 正负号 + 色（符号是主要信息，色只是强化）
 */
import { formatSigned } from '@/utils/format'

export type SignalDirection = 'long' | 'short' | 'neutral'
type ToneColor = 'long' | 'short' | 'grey' | 'up' | 'down'

export interface DirectionTone {
  key: SignalDirection
  /** Vuetify 主题槽位名，可直接传给 color="" */
  color: ToneColor
  /** 对应的文本色 class */
  textClass: string
  /** 方向图标，保证颜色不是唯一的信息载体 */
  icon: string
  label: string
}

const DIRECTION_TONES: Record<SignalDirection, DirectionTone> = {
  long: { key: 'long', color: 'long', textClass: 'text-long', icon: 'mdi-arrow-up-bold', label: '做多' },
  short: { key: 'short', color: 'short', textClass: 'text-short', icon: 'mdi-arrow-down-bold', label: '做空' },
  neutral: { key: 'neutral', color: 'grey', textClass: 'text-grey', icon: 'mdi-minus', label: '观望' },
}

/** 归一化：后端偶尔给 buy / sell / LONG 这类写法，统一收口到三种方向 */
const normalizeDirection = (value: unknown): SignalDirection => {
  const raw = String(value ?? '').toLowerCase()
  if (raw === 'long' || raw === 'buy') return 'long'
  if (raw === 'short' || raw === 'sell') return 'short'
  return 'neutral'
}

export const directionTone = (value: unknown): DirectionTone =>
  DIRECTION_TONES[normalizeDirection(value)]

export const directionLabel = (value: unknown): string => directionTone(value).label

export interface PnlTone {
  color: ToneColor
  textClass: string
  /** 已带正负号的展示文本；非法值返回 '—' */
  text: string
  sign: 1 | -1 | 0
}

/**
 * 盈亏色调。注意：0 按「持平」处理，用主文字色而不是赚钱色，
 * 免得一堆 0.00 把屏幕刷成一片绿。
 */
export const pnlTone = (
  value: number | string | null | undefined,
  digits = 2,
): PnlTone => {
  const num = Number(value)
  if (!Number.isFinite(num)) {
    return { color: 'grey', textClass: 'text-medium-emphasis', text: '—', sign: 0 }
  }
  if (num > 0) {
    return { color: 'up', textClass: 'text-up', text: formatSigned(num, digits), sign: 1 }
  }
  if (num < 0) {
    return { color: 'down', textClass: 'text-down', text: formatSigned(num, digits), sign: -1 }
  }
  return { color: 'grey', textClass: 'text-medium-emphasis', text: formatSigned(0, digits), sign: 0 }
}

/** 只要 class 的场景（表格单元格） */
export const pnlClass = (value: number | string | null | undefined): string =>
  pnlTone(value).textClass

/** 只要 class 的百分比场景 */
export const pnlPercentClass = (value: number | string | null | undefined): string => {
  const num = Number(value)
  if (!Number.isFinite(num)) return 'text-medium-emphasis'
  if (num > 0) return 'text-up'
  if (num < 0) return 'text-down'
  return 'text-medium-emphasis'
}

/** 开仓记录的 buy / sell / close 三态 */
export const positionSideTone = (side: unknown): DirectionTone & { isClose: boolean } => {
  const raw = String(side ?? '').toLowerCase()
  if (raw === 'close') return { ...DIRECTION_TONES.neutral, isClose: true }
  return { ...directionTone(raw), isClose: false }
}
