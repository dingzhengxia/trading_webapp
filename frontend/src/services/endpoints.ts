/**
 * REST 端点唯一来源（T10 / ARCH R-P2-3）。
 *
 * 规则：
 * - 全部后端路径只允许出现在本文件；views/components/stores 一律引用
 *   `ENDPOINTS.xxx` 常量或下方强类型 `api` 门面，禁止裸写 '/api/' 字符串
 *   （由 eslint no-restricted-syntax 护栏强制）；
 * - `api` 门面仅封装最常用、签名稳定的请求；payload 复杂/低频的请求
 *   直接使用 ENDPOINTS 常量 + apiClient，避免门面膨胀。
 */
import apiClient from '@/services/api'

export const ENDPOINTS = {
  status: '/api/status',
  positions: '/api/positions',
  positionsClose: '/api/positions/close',
  positionsCloseBySide: '/api/positions/close-by-side',
  positionsCloseMultiple: '/api/positions/close-multiple',
  settings: '/api/settings',
  settingsUpdateCoinPools: '/api/settings/update-coin-pools',
  settingsAddCoin: '/api/settings/add-coin',
  signals: '/api/signals',
  signalsConfig: '/api/signals/config',
  signalsAutoTrade: '/api/signals/auto-trade',
  signalsScan: '/api/signals/scan',
  signalsClear: '/api/signals/clear',
  protection: '/api/protection',
  protectionConfig: '/api/protection/config',
  protectionEvents: '/api/protection/events',
  rebalancePlan: '/api/rebalance/plan',
  rebalanceExecute: '/api/rebalance/execute',
  tradingManual: '/api/trading/manual',
  tradingStart: '/api/trading/start',
  tradingStop: '/api/trading/stop',
  tradingSyncSltp: '/api/trading/sync-sltp',
  tradingOpenHistory: '/api/trading/open-history',
  reports: '/api/reports',
  reportsConfig: '/api/reports/config',
  reportsRun: '/api/reports/run',
} as const

export type EndpointPath = (typeof ENDPOINTS)[keyof typeof ENDPOINTS]

/** 强类型 API 门面：常用请求的单一写入口 */
export const api = {
  /** 通用 POST：端点必须来自 ENDPOINTS 常量（launchTask 等动态端点场景） */
  post: <T = unknown>(endpoint: EndpointPath, payload?: unknown) =>
    apiClient.post<T>(endpoint, payload),
  /** 登录状态 / 服务健康检查 */
  getStatus: <T = unknown>() => apiClient.get<T>(ENDPOINTS.status),
  /** 全量设置（带 cache-buster，绕过浏览器缓存） */
  getSettings: <T = unknown>() =>
    apiClient.get<T>(ENDPOINTS.settings, { params: { _t: Date.now() } }),
  /** 整包保存设置 */
  postSettings: (payload: unknown) => apiClient.post(ENDPOINTS.settings, payload),
  /** 局部 patch 设置（与整包保存同端点，语义由调用方保证） */
  patchSettings: (partial: Record<string, unknown>) =>
    apiClient.post(ENDPOINTS.settings, partial),
  /** 当前持仓 */
  getPositions: <T = unknown>() => apiClient.get<T>(ENDPOINTS.positions),
  /** 信号列表 */
  getSignals: <T = unknown>() => apiClient.get<T>(ENDPOINTS.signals),
  /** 仓位保护状态 */
  getProtection: <T = unknown>() => apiClient.get<T>(ENDPOINTS.protection),
  /** 仓位保护整包配置写入 */
  postProtectionConfig: (payload: Record<string, unknown>) =>
    apiClient.post(ENDPOINTS.protectionConfig, payload),
  /** 信号配置 patch 写入（每个配置域唯一写路径） */
  postSignalsConfig: <T = unknown>(payload: Record<string, unknown>) =>
    apiClient.post<T>(ENDPOINTS.signalsConfig, payload),
  /** 自动交易开关 */
  postSignalsAutoTrade: (payload: { enabled: boolean }) =>
    apiClient.post(ENDPOINTS.signalsAutoTrade, payload),
  /** 手动触发信号扫描 */
  postSignalsScan: <T = unknown>(payload: Record<string, unknown> = {}) =>
    apiClient.post<T>(ENDPOINTS.signalsScan, payload),
  /** 清空信号列表 */
  postSignalsClear: () => apiClient.post(ENDPOINTS.signalsClear),
  /** 报告状态 */
  getReports: <T = unknown>() => apiClient.get<T>(ENDPOINTS.reports),
  /** 报告配置保存 */
  postReportsConfig: (payload: Record<string, unknown>) =>
    apiClient.post(ENDPOINTS.reportsConfig, payload),
  /** 立即生成报告 */
  postReportsRun: (payload: { report_name: string }) =>
    apiClient.post(ENDPOINTS.reportsRun, payload),
}
