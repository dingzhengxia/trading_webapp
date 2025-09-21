// frontend/src/stores/authStore.ts (修正版)
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  // 尝试从 localStorage 初始化 accessKey，实现持久化登录
  const accessKey = ref(localStorage.getItem('access_key') || '')

  const isAuthenticated = computed(() => !!accessKey.value)

  function setAccessKey(newKey: string) {
    if (newKey) {
      accessKey.value = newKey
      localStorage.setItem('access_key', newKey)

      // REFACTOR: 移除强制页面刷新。
      // App.vue 中已经有一个 watcher 在监听 `isAuthenticated` 的变化。
      // 当 accessKey 被设置后，`isAuthenticated` 会变为 true，
      // 该 watcher 会自动触发 initializeApp() 函数。
      // 这种响应式的方式是正确的做法，避免了不必要的页面重载和“闪烁”。
      // window.location.reload(); // <-- 移除此行
    }
  }

  function clearAccessKey() {
    accessKey.value = ''
    localStorage.removeItem('access_key')
  }

  return { accessKey, isAuthenticated, setAccessKey, clearAccessKey }
})
