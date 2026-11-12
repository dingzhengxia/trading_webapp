// frontend/src/stores/authStore.ts (最终安全版)
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/services/endpoints'

export const useAuthStore = defineStore('auth', () => {
  const accessKey = ref(localStorage.getItem('access_key') || '')

  // --- 新增：加载状态 ---
  const isLoading = ref(false)

  const isAuthenticated = computed(() => !!accessKey.value)

  // --- 核心修改：这是一个新的、安全的 action ---
  async function validateAndSetKey(newKey: string): Promise<boolean> {
    isLoading.value = true

    // 步骤 1: 临时将 key 存入内存中的 ref，以便下一个 API 请求可以使用它
    accessKey.value = newKey

    // 步骤 2: 用最简单的受保护接口做探针。
    // 不能用 settingsStore.fetchSettings()：它内部 catch 掉错误，永远 resolve，
    // 会导致无效 Key 也被写入 localStorage，之后每次刷新都带脏 Key 反复 403。
    try {
      await api.getStatus()

      // 步骤 3: 请求成功（200）才把 Key 持久化
      localStorage.setItem('access_key', newKey)
      isLoading.value = false
      return true
    } catch (error) {
      // 步骤 4: 403/网络错误 → 清除内存与 localStorage，返回失败
      console.error('Key validation failed:', error)
      clearAccessKey()
      isLoading.value = false
      return false
    }
  }

  function clearAccessKey() {
    accessKey.value = ''
    localStorage.removeItem('access_key')
  }

  return {
    accessKey,
    isAuthenticated,
    isLoading, // 导出加载状态
    validateAndSetKey, // 导出新的 action
    clearAccessKey,
  }
})
