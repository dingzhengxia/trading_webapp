// frontend/src/services/api.ts (最终版)
import axios from 'axios';
import { useAuthStore } from '@/stores/authStore';
import { useUiStore } from '@/stores/uiStore';

const getApiBaseUrl = () => {
  if (import.meta.env.DEV) {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return '';
};

const apiClient = axios.create({
  baseURL: getApiBaseUrl(),
});

apiClient.interceptors.request.use(
  (config) => {
    const authStore = useAuthStore();
    if (authStore.isAuthenticated) {
      config.headers['X-API-KEY'] = authStore.accessKey;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// 响应拦截器，用于在密钥错误时清除密钥并提示
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 403) {
      const authStore = useAuthStore();
      authStore.clearAccessKey();

      const uiStore = useUiStore();
      uiStore.logStore.addLog({ message: '访问密钥无效或已过期，请重新输入。', level: 'error', timestamp: new Date().toLocaleTimeString() });
      // 可以在这里触发一个全局事件或状态，让App.vue显示输入框
      // 为简单起见，我们只清除密钥，用户下次刷新或操作时会被要求输入
    }
    return Promise.reject(error);
  }
);

export default apiClient;
