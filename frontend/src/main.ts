// frontend/src/main.ts
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
// 设计令牌底座（字体 / 数字排版 / 语义色），必须在 vuetify 样式之后
import './styles/base.css'
// 移动端可用性补丁（放在最后，便于覆盖）
import './styles/mobile.css'
// 币种选择区通用布局（CoinPoolsManager / ControlPanel 共用）
import './styles/selection-wrapper.css'

import { useUiStore } from './stores/uiStore'
import { appThemes } from './theme'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)

// 在创建 Vuetify 实例之前，先从 store 获取主题
const uiStore = useUiStore()

const vuetify = createVuetify({
  components,
  directives,
  // 全局组件默认值：表单只允许 outlined + compact 一种形态，
  // 从根上杜绝同一页里 filled / outlined 并存
  defaults: {
    VTextField: { variant: 'outlined', density: 'compact', hideDetails: 'auto' },
    VTextarea: { variant: 'outlined', density: 'compact', hideDetails: 'auto' },
    VSelect: { variant: 'outlined', density: 'compact', hideDetails: 'auto' },
    VAutocomplete: { variant: 'outlined', density: 'compact', hideDetails: 'auto' },
    VCombobox: { variant: 'outlined', density: 'compact', hideDetails: 'auto' },
    VFileInput: { variant: 'outlined', density: 'compact', hideDetails: 'auto' },
    VSwitch: { color: 'primary', density: 'compact', hideDetails: 'auto', inset: true },
  },
  theme: {
    defaultTheme: uiStore.theme,
    // 语义令牌：long/short（方向）与 up/down（盈亏）是两组独立槽位
    themes: appThemes,
  },
})

app.use(router)
app.use(vuetify)
app.mount('#app')
