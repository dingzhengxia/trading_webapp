// frontend/src/main.ts (完整代码)
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

// --- 新增：PrimeVue ---
import PrimeVue from 'primevue/config';
// 引入一个与 Vuetify 暗色主题比较接近的 PrimeVue 主题
import 'primevue/resources/themes/aura-dark-noir/theme.css';

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
app.use(PrimeVue); // <-- 注册 PrimeVue
app.mount('#app')
