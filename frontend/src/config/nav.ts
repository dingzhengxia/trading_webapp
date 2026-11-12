/**
 * 一级导航单一数据源（规格 §3 A1）
 *
 * App.vue 侧栏、BottomTabBar 底部 Tab 共用，避免两处重复维护。
 * 顺序即 Tab 顺序（按任务频率：交易最高频、默认落地页）。
 */
export interface NavItem {
  path: string
  title: string
  icon: string
}

/** 底部 Tab 第 1–4 项 / PC 侧栏第 1 组 */
export const primaryNav: NavItem[] = [
  { path: '/trading', title: '交易', icon: 'mdi-candle' },
  { path: '/signals', title: '信号', icon: 'mdi-radar' },
  { path: '/protection', title: '风控', icon: 'mdi-shield-check-outline' },
  { path: '/overview', title: '总览', icon: 'mdi-view-dashboard-outline' },
]

/** 底部 Tab「更多」抽屉内 / PC 侧栏第 2 组 */
export const secondaryNav: NavItem[] = [
  { path: '/reports', title: '周期报告', icon: 'mdi-newspaper-variant-outline' },
  { path: '/settings', title: '设置', icon: 'mdi-cogs' },
]
