/**
 * 多头权重：与后端 app/logic/plan_calculator.py 的 reconcile_weights 一一对应。
 *
 * 口径只有一套：权重键集合 = 当前做多清单，合计 100，默认均分。
 * 换币种时两者必须在同一次保存里一起提交（POST /api/settings），
 * 不存在「没设过就用 BTC 40% / ETH 30%」这层隐藏默认值。
 *
 * 为什么前端要复刻：权重弹窗与「选币」都要在提交前算出真实权重，
 * 界面显示的必须就是后端会存、会用的那份，否则又会回到
 * 「我设的是均分，BTC 却拿了 40%」（2026-11-15）这种界面撒谎的老问题。
 */

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

/**
 * 把权重对齐到币种清单：键集合 = 清单，合计 = 100。
 * - 没有可用权重 → 均分；
 * - 只覆盖部分币种 → 剩余比例由未覆盖的币均分（已分配达 100 时按均值参与）；
 * - 清单外的键丢弃，不会串到下一套清单。
 */
export function reconcileWeights(
  coins: string[] | null | undefined,
  weights: Record<string, number> | null | undefined,
): Record<string, number> {
  const list = (coins ?? []).map((coin) => String(coin).trim().toUpperCase()).filter(Boolean)
  const unique = [...new Set(list)]
  if (unique.length === 0) return {}

  const saved: Record<string, number> = {}
  for (const [rawCoin, rawWeight] of Object.entries(weights ?? {})) {
    const coin = String(rawCoin).trim().toUpperCase()
    if (!unique.includes(coin)) continue
    const value = Number(rawWeight)
    if (!Number.isFinite(value) || value <= 0) continue
    saved[coin] = (saved[coin] ?? 0) + value
  }
  if (Object.keys(saved).length === 0) return evenWeights(unique)

  const missing = unique.filter((coin) => saved[coin] === undefined)
  if (missing.length > 0) {
    const assigned = Object.values(saved).reduce((sum, value) => sum + value, 0)
    const share =
      assigned < 100 ? (100 - assigned) / missing.length : assigned / Object.keys(saved).length
    missing.forEach((coin) => {
      saved[coin] = share
    })
  }

  const total = Object.values(saved).reduce((sum, value) => sum + value, 0)
  if (total <= 0) return evenWeights(unique)

  const result: Record<string, number> = {}
  let accumulated = 0
  for (let index = 0; index < unique.length; index += 1) {
    const coin = unique[index]
    const value =
      index === unique.length - 1 ? round2(100 - accumulated) : round2((saved[coin] * 100) / total)
    // 币种极多时两位小数误差可能吃光最后一项 → 整体退回均分
    if (value <= 0) return evenWeights(unique)
    result[coin] = value
    accumulated = round2(accumulated + value)
  }
  return result
}
