// frontend/src/stores/authStore.ts (最终安全版)
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useSettingsStore } from './settingsStore' // 导入 settings store 用于验证

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

    // 步骤 2: 尝试执行一个需要认证的 API 请求作为“探针”
    const settingsStore = useSettingsStore()

    try {
      // fetchSettings() 会自动带上我们刚刚临时设置的 key
      await settingsStore.fetchSettings()

      // 步骤 3: 如果上面的请求没有抛出错误 (即成功返回 200)，说明 key 是有效的
      // 此时，才将 key 写入 localStorage 持久化
      localStorage.setItem('access_key', newKey)
      isLoading.value = false
      return true
    } catch (error) {
      // 步骤 4: 如果请求失败 (例如返回403或请求本身就因无效字符失败)
      // api.ts 中的拦截器会调用 clearAccessKey()，自动清空内存和 localStorage
      // 我们在这里只需要处理最终状态
      console.error('Key validation failed:', error)
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
