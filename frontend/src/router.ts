// frontend/src/router.ts (完整修复版)
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

// 路由级懒加载：各页面不打包进首屏 chunk（原首屏 JS 约 690KB）
const DashboardView = () => import('@/views/DashboardView.vue')
const TradingView = () => import('@/views/TradingView.vue')
const SignalsView = () => import('@/views/SignalsView.vue')
const ProtectionView = () => import('@/views/ProtectionView.vue')
const ReportsView = () => import('@/views/ReportsView.vue')
const SettingsView = () => import('@/views/SettingsView.vue')

// --- 核心修复：定义路由元信息的类型 ---
declare module 'vue-router' {
  interface RouteMeta {
    title: string
    icon: string // 明确告诉 TypeScript, icon 字段是一个字符串
  }
}
// ------------------------------------

const routes: Array<RouteRecordRaw> = [
  {
    path: '/',
    name: 'dashboard',
    component: DashboardView,
    meta: { title: '仪表盘', icon: 'mdi-view-dashboard' },
  },

  {
    path: '/trading',
    name: 'trading',
    component: TradingView,
    meta: { title: '交易终端', icon: 'mdi-swap-horizontal-bold' },
  },
  // 「手动交易」页已下线（反手/平仓统一在交易终端的持仓表里操作），旧链接重定向
  {
    path: '/manual',
    redirect: '/trading',
  },
  {
    path: '/signals',
    name: 'signals',
    component: SignalsView,
    meta: { title: '信号监控', icon: 'mdi-radar' },
  },
  {
    path: '/protection',
    name: 'protection',
    component: ProtectionView,
    meta: { title: '仓位保护', icon: 'mdi-shield-check-outline' },
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
    meta: { title: '应用设置', icon: 'mdi-cogs' },
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

export default router
