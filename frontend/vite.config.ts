import {fileURLToPath, URL} from 'node:url'

import {defineConfig} from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'
import vuetify from 'vite-plugin-vuetify'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
    // Vuetify 按需引入（T12 / P1-4）：模板内使用的组件 / 指令自动按需注册，
    // 样式经 'vuetify/styles' 转为 sass 源码并随组件摇树，显著降低 CSS 总量。
    // 注意：ConfigDrawer / SmartSelect 内的 <component :is="'v-xxx'"> 字符串派发
    // 无法静态分析，已在对应 .vue 文件显式 import。
    vuetify({ autoImport: true }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
  build: {
    // 大体积第三方库单独成块，主包（业务代码）保持小而稳定
    rollupOptions: {
      output: {
        manualChunks: {
          vuetify: ['vuetify'],
          vendor: ['vue', 'vue-router', 'pinia'],
          axios: ['axios'],
        },
      },
    },
  },
  server: {
    host: '0.0.0.0', // 监听所有网络接口
    port: 5173,      // 保持默认端口
  }
})
