/**
 * 多头权重的默认分配（与后端 app/logic/plan_calculator.py 的 _default_allocation 一一对应）。
 *
 * 为什么前端要复刻一份：后端在「没有自定义权重」时会用 BTC 40% / ETH 30% / 其余均分，
 * 而旧版权重弹窗在同样情况下显示的是「均分」——界面说的和后端做的不是一回事
 * （2026-11-15 用户按「均分」理解，结果 BTC 拿了 40%）。默认值必须两边一致，
 * 改一边就要改另一边。
 */

export const DEFAULT_BTC_WEIGHT = 40
export const DEFAULT_ETH_WEIGHT = 30
export const BTC_ETH_ONLY_WEIGHT = { BTC: 60, ETH: 40 }

const round2 = (value: number) => Math.round(value * 100) / 100

/** 百分数按 2 位小数均分，尾差并入最后一项，保证合计正好 100 */
export function evenWeights(coins: string[]): Record<string, number> {
  const list = coins.map((coin) => coin.toUpperCase())
  if (list.length === 0) return {}
  const per = round2(100 / list.length)
  const result: Record<string, number> = {}
  let accumulated = 0
  list.forEach((coin, index) => {
    const weight = index === list.length - 1 ? round2(100 - accumulated) : per
    result[coin] = weight
    accumulated = round2(accumulated + weight)
  })
  return result
}

/** 后端「未设置自定义权重」时的实际分配 */
export function defaultWeights(coins: string[]): Record<string, number> {
  const list = coins.map((coin) => coin.toUpperCase())
  const hasBtc = list.includes('BTC')
  const hasEth = list.includes('ETH')
  const satellites = list.filter((coin) => coin !== 'BTC' && coin !== 'ETH')

  if ((hasBtc || hasEth) && satellites.length > 0) {
    const result: Record<string, number> = {}
    let remaining = 100
    if (hasBtc) {
      result.BTC = DEFAULT_BTC_WEIGHT
      remaining -= DEFAULT_BTC_WEIGHT
    }
    if (hasEth) {
      result.ETH = DEFAULT_ETH_WEIGHT
      remaining -= DEFAULT_ETH_WEIGHT
    }
    const per = round2(Math.max(remaining, 0) / satellites.length)
    satellites.forEach((coin, index) => {
      result[coin] =
        index === satellites.length - 1 ? round2(Math.max(remaining, 0) - per * index) : per
    })
    return result
  }

  if (hasBtc && hasEth && satellites.length === 0) return { ...BTC_ETH_ONLY_WEIGHT }
  return evenWeights(list)
}
