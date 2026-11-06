// frontend/src/router.ts (完整修复版)
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import DashboardView from '@/views/DashboardView.vue'
import TradingView from '@/views/TradingView.vue'
import ManualTradeView from '@/views/ManualTradeView.vue'
import SignalsView from '@/views/SignalsView.vue'
import SettingsView from '@/views/SettingsView.vue'

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
  {
    path: '/manual',
    name: 'manual',
    component: ManualTradeView,
    meta: { title: '手动交易', icon: 'mdi-hand-coin-outline' },
  },
  {
    path: '/signals',
    name: 'signals',
    component: SignalsView,
    meta: { title: '信号监控', icon: 'mdi-radar' },
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
