// frontend/src/main.ts (添加 HMR 逻辑)

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

// --- 核心修改在这里 ---
// 导入我们的 WebSocket 服务单例
import websocketService from './services/websocket'
// --- 修改结束 ---


const vuetify = createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: 'dark'
  }
})

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(vuetify)
app.mount('#app')


// --- 核心修改在这里 ---
// 添加 Vite HMR (热模块替换) 的处理逻辑
if (import.meta.hot) {
  import.meta.hot.on('vite:beforeUpdate', () => {
    // 在 Vite 更新任何模块之前，我们主动断开 WebSocket 连接
    // 这样，当 App.vue 重新挂载并调用 connect() 时，它将建立一个全新的、干净的连接
    console.log("HMR update detected, disconnecting WebSocket.");
    websocketService.disconnect();
  });
}
// --- 修改结束 ---
