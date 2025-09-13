// frontend/src/services/api.ts (完整修复版)
import axios from 'axios';

// --- 核心修复：动态确定 baseURL ---
const getApiBaseUrl = () => {
  // 在开发环境中，我们知道后端运行在 8000 端口
  if (import.meta.env.DEV) {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  // 在生产环境中，通常前端和后端部署在同一个域下，可以直接使用相对路径
  return '';
};
// ------------------------------------

const apiClient = axios.create({
  baseURL: getApiBaseUrl(),
});

export default apiClient;
