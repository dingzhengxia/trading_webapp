// frontend/src/main.ts (主题切换版)
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'

// Vuetify
import 'vuetify/styles'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import '@mdi/font/css/materialdesignicons.css'

// --- 核心修改：调整初始化顺序 ---
import { useUiStore } from './stores/uiStore' // 提前导入 store

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)

// 在创建 Vuetify 实例之前，先从 store 获取主题
const uiStore = useUiStore()

const vuetify = createVuetify({
  components,
  directives,
  theme: {
    // 使用从 store 中读取的主题作为默认主题
    defaultTheme: uiStore.theme,
  },
})

app.use(router)
app.use(vuetify)
app.mount('#app')
// --- 修改结束 ---
