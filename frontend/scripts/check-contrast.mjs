#!/usr/bin/env node
/**
 * 对比度守门脚本
 *
 * 读 src/theme/index.ts 里的色值，逐个校验「语义色 vs 表面色」的 WCAG 对比度。
 * 任何一组低于 4.5:1（AA 正文标准）就让构建失败 —— 这是唯一能防止规则倒退的办法：
 * 靠自觉，三个月后就会有人把盈利绿调成 #4CAF50。
 *
 * 用法：npm run check:contrast
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const themeFile = resolve(here, '../src/theme/index.ts')
const source = readFileSync(themeFile, 'utf8')

/** 从 `const darkColors = { ... }` 这样的块里取出键值对 */
function readPalette(blockName) {
  const start = source.indexOf(`const ${blockName} = {`)
  if (start < 0) throw new Error(`找不到色板定义：${blockName}`)
  const end = source.indexOf('\n}', start)
  const block = source.slice(start, end)
  const palette = {}
  for (const line of block.split('\n')) {
    const match = line.match(/^\s*'?([\w-]+)'?\s*:\s*'(#[0-9A-Fa-f]{6})'/)
    if (match) palette[match[1]] = match[2]
  }
  return palette
}

const srgbToLinear = (channel) => {
  const c = channel / 255
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

const luminance = (hex) => {
  const value = hex.replace('#', '')
  const r = parseInt(value.slice(0, 2), 16)
  const g = parseInt(value.slice(2, 4), 16)
  const b = parseInt(value.slice(4, 6), 16)
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b)
}

const contrast = (fg, bg) => {
  const l1 = luminance(fg)
  const l2 = luminance(bg)
  const [light, dark] = l1 > l2 ? [l1, l2] : [l2, l1]
  return (light + 0.05) / (dark + 0.05)
}

// 每个语义色都会用于文字（数字、标签、状态），所以要同时对它可能落到的两种表面色达标
const FOREGROUNDS = ['up', 'down', 'long', 'short', 'primary', 'warning']
const SURFACES = ['surface', 'background']
const MIN_RATIO = 4.5

let failed = 0
const rows = []

for (const [themeName, blockName] of [
  ['dark', 'darkColors'],
  ['light', 'lightColors'],
]) {
  const palette = readPalette(blockName)
  for (const fg of FOREGROUNDS) {
    for (const bg of SURFACES) {
      const fgHex = palette[fg]
      const bgHex = palette[bg]
      if (!fgHex || !bgHex) {
        console.error(`✗ ${themeName}: 缺少色值 ${fg} 或 ${bg}`)
        failed += 1
        continue
      }
      const ratio = contrast(fgHex, bgHex)
      const ok = ratio >= MIN_RATIO
      if (!ok) failed += 1
      rows.push({
        theme: themeName,
        pair: `${fg} on ${bg}`,
        ratio: ratio.toFixed(2),
        ok,
      })
    }
  }
}

const pad = (text, width) => String(text).padEnd(width)
console.log(pad('主题', 8) + pad('组合', 22) + pad('对比度', 10) + '结果')
console.log('-'.repeat(52))
for (const row of rows) {
  console.log(
    pad(row.theme, 8) + pad(row.pair, 22) + pad(`${row.ratio}:1`, 10) + (row.ok ? '通过' : '低于 4.5:1'),
  )
}

if (failed > 0) {
  console.error(`\n✗ ${failed} 组未通过 WCAG AA（≥ ${MIN_RATIO}:1），请调整 src/theme/index.ts`)
  process.exit(1)
}
console.log(`\n✓ 全部 ${rows.length} 组通过 WCAG AA（≥ ${MIN_RATIO}:1）`)
