// frontend/src/stores/authStore.ts
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';

export const useAuthStore = defineStore('auth', () => {
    // 尝试从 localStorage 初始化 accessKey
    const accessKey = ref(localStorage.getItem('access_key') || '');

    const isAuthenticated = computed(() => !!accessKey.value);

    function setAccessKey(newKey: string) {
        if (newKey) {
            accessKey.value = newKey;
            localStorage.setItem('access_key', newKey);
        }
    }

    function clearAccessKey() {
        accessKey.value = '';
        localStorage.removeItem('access_key');
    }

    return { accessKey, isAuthenticated, setAccessKey, clearAccessKey };
});
