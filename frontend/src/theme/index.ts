/**
 * 设计令牌 · 主题层
 *
 * 分三类槽位，互不借用：
 *   1. 界面槽位：background / surface / surface-variant / primary / info / warning
 *   2. 方向槽位：long / short        —— 只表示「做多 / 做空」
 *   3. 盈亏槽位：up / down           —— 只表示「盈利 / 亏损」
 *   4. 结果槽位：success / error     —— 只表示「操作成功 / 操作失败」
 *      success-strong 是 success 的「实心按钮底」变体：surface 级底色压白字不够 AA，
 *      需要更深一档时用它 + 配套的 on-success-strong（只用于背景，不当文字色）。
 *
 * 前三类今天可能取到相同色值，但必须是独立的键：以后想单独压低「盈利绿」的饱和度时，
 * 不会把全站的「保存成功」提示一起改灰。
 *
 * 取值依据（浅色主题白底对比度）：
 *   #0E7A57 ≈ 5.3:1   #C22B3A ≈ 5.7:1   #5F6975 ≈ 5.6:1   —— 均通过 WCAG AA 4.5:1
 */
export type AppThemeName = 'dark' | 'light'

/** 深色主题：终端底色，避免纯黑，表面分层靠 2 级 surface */
const darkColors = {
  background: '#0E1116',
  surface: '#161A20',
  'surface-bright': '#232A33',
  'surface-light': '#1D2229',
  'surface-variant': '#1D2229',
  'on-surface-variant': '#B6BEC9',

  primary: '#4C8DF6',
  'primary-darken-1': '#2E6FD8',
  secondary: '#7C8694',
  info: '#4C8DF6',
  warning: '#F2A03D',

  // 方向
  long: '#16C08A',
  short: '#F0616D',
  // 盈亏（独立槽位）
  up: '#16C08A',
  down: '#F0616D',
  // 操作结果
  success: '#16C08A',
  error: '#F0616D',
  // 实心主按钮底色（success 变体太亮，白字压不住 —— 见 on-success-strong）
  'success-strong': '#216E39',
  'on-success-strong': '#FFFFFF',
}

/** 浅色主题：同一套槽位在白底上重新取值，不靠透明度凑 */
const lightColors = {
  background: '#F6F7F9',
  surface: '#FFFFFF',
  'surface-bright': '#FFFFFF',
  'surface-light': '#F0F2F5',
  'surface-variant': '#ECEEF2',
  'on-surface-variant': '#3F4750',

  primary: '#1D5FD0',
  'primary-darken-1': '#16479B',
  secondary: '#5F6975',
  info: '#1D5FD0',
  warning: '#9A5B00',

  long: '#0E7A57',
  short: '#C22B3A',
  up: '#0E7A57',
  down: '#C22B3A',
  success: '#0E7A57',
  error: '#C22B3A',
  // 实心主按钮底色：success(#0E7A57) 上压白字只有 3.4:1，
  // 操作类实心按钮单独取一档更深的绿（#157347 上白字 5.8:1，过 AA）
  'success-strong': '#157347',
  'on-success-strong': '#FFFFFF',
}

export const appThemes = {
  dark: { dark: true, colors: darkColors, variables: { 'medium-emphasis-opacity': 0.72 } },
  light: { dark: false, colors: lightColors, variables: { 'medium-emphasis-opacity': 0.68 } },
}
