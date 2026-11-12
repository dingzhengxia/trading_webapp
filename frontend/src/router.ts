// frontend/src/router.ts
// 命名与路径按重设计规格 §1.1：仪表盘→总览(/overview)、交易终端→交易、信号监控→信号、
// 仓位保护→风控、应用设置→设置；`/` 重定向到 `/trading`（默认落地最高频任务）。
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

// 路由级懒加载：各页面不打包进首屏 chunk（原首屏 JS 约 690KB）
const DashboardView = () => import('@/views/DashboardView.vue')
const TradingView = () => import('@/views/TradingView.vue')
const SignalsView = () => import('@/views/SignalsView.vue')
const ProtectionView = () => import('@/views/ProtectionView.vue')
const ReportsView = () => import('@/views/ReportsView.vue')
const SettingsView = () => import('@/views/SettingsView.vue')

// --- 路由元信息类型：icon 供侧栏/Tab 用，hasDock 驱动底部留白（base.css §2.3） ---
declare module 'vue-router' {
  interface RouteMeta {
    title: string
    icon: string
    /** 页面带固定操作条（AppDockFooter）时为 true，用于计算 v-main 底部留白 */
    hasDock?: boolean
  }
}
// ------------------------------------

const routes: Array<RouteRecordRaw> = [
  {
    path: '/',
    redirect: '/trading',
  },

  {
    path: '/trading',
    name: 'trading',
    component: TradingView,
    meta: { title: '交易', icon: 'mdi-candle', hasDock: true },
  },
  // 「手动交易」页已下线（反手/平仓统一在交易页的持仓表里操作），旧链接重定向
  {
    path: '/manual',
    redirect: '/trading',
  },
  {
    path: '/signals',
    name: 'signals',
    component: SignalsView,
    meta: { title: '信号', icon: 'mdi-radar' },
  },
  {
    path: '/protection',
    name: 'protection',
    component: ProtectionView,
    meta: { title: '风控', icon: 'mdi-shield-check-outline' },
  },
  {
    path: '/overview',
    name: 'overview',
    component: DashboardView,
    meta: { title: '总览', icon: 'mdi-view-dashboard-outline' },
  },
  {
    path: '/reports',
    name: 'reports',
    component: ReportsView,
    meta: { title: '周期报告', icon: 'mdi-newspaper-variant-outline' },
  },
  {
    path: '/settings',
    name: 'settings',
    component: SettingsView,
    meta: { title: '设置', icon: 'mdi-cogs', hasDock: true },
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

export default router
