// frontend/src/services/api.ts (重构版)
import axios from 'axios'
import { useAuthStore } from '@/stores/authStore'
import { useUiStore } from '@/stores/uiStore'

const getApiBaseUrl = () => {
  if (import.meta.env.DEV) {
    // 在开发模式下，前端运行在 5173 端口，后端在 8000 端口
    return `${window.location.protocol}//${window.location.hostname}:8000`
  }
  // 在生产模式下（Docker中），前端和后端在同一源
  return ''
}

const apiClient = axios.create({
  baseURL: getApiBaseUrl(),
})

// 请求拦截器：在每个请求发送前附加 Access Key
apiClient.interceptors.request.use(
  (config) => {
    // Pinia store 必须在函数内部获取，以确保它已被初始化
    const authStore = useAuthStore()
    if (authStore.isAuthenticated) {
      config.headers['X-API-KEY'] = authStore.accessKey
    }
    return config
  },
  (error) => Promise.reject(error),
)

// 响应拦截器：处理 403 Forbidden 错误
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 403) {
      const authStore = useAuthStore()
      const uiStore = useUiStore()

      // 如果收到 403，说明密钥无效，清除它
      authStore.clearAccessKey()

      uiStore.logStore.addLog({
        message: '访问密钥无效或已过期，请重新输入。',
        level: 'error',
        timestamp: new Date().toLocaleTimeString(),
      })
      // 对话框将自动弹出，因为 authStore.isAuthenticated 变为 false
    }
    return Promise.reject(error)
  },
)

export default apiClient
