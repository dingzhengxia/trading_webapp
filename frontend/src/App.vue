<!-- frontend/src/App.vue (完整代码) -->
<template>
  <v-app>
    <v-app-bar app density="compact">
      <v-toolbar-title>Web 交易终端</v-toolbar-title>
      <v-spacer></v-spacer>
      <v-chip :color="uiStore.statusColor" class="mr-2" label>{{ uiStore.statusMessage }}</v-chip>

      <!-- 导航抽屉按钮：移到应用栏右侧，手机端不再使用底部导航 -->
      <v-btn icon aria-label="打开导航菜单" class="d-md-none" @click="drawer = !drawer">
        <v-icon>mdi-menu</v-icon>
      </v-btn>

      <!-- 主题切换按钮 -->
      <v-btn
        icon
        :aria-label="`切换到${uiStore.theme === 'dark' ? '浅色' : '深色'}模式`"
        :title="`切换到${uiStore.theme === 'dark' ? '浅色' : '深色'}模式`"
        @click="uiStore.toggleTheme(theme)"
      >
        <v-icon>{{ themeIcon }}</v-icon>
      </v-btn>

      <!-- 日志按钮 -->
      <v-btn icon aria-label="打开运行日志" title="运行日志" @click="uiStore.toggleLogDrawer()">
        <v-badge
          :content="uiStore.logStore.logs.length"
          color="error"
          :model-value="uiStore.logStore.logs.length > 0"
        >
          <v-icon>mdi-console-line</v-icon>
        </v-badge>
      </v-btn>
    </v-app-bar>

    <v-navigation-drawer v-model="drawer" :permanent="$vuetify.display.mdAndUp" app>
      <div class="drawer-brand px-4 py-3">
        <span class="text-subtitle-1 font-weight-medium">交易终端</span>
        <div class="text-caption text-medium-emphasis">Signals · Positions · Risk</div>
      </div>
      <v-divider />
      <v-list nav density="compact">
        <v-list-item
          v-for="route in routes"
          :key="route.name?.toString()"
          :prepend-icon="route.meta.icon"
          :title="route.meta.title"
          :to="route.path"
          exact
        ></v-list-item>
      </v-list>
    </v-navigation-drawer>

    <v-main>
      <v-container fluid class="page-shell">
        <router-view />
      </v-container>
    </v-main>

    <!-- App-level Dialogs and Components -->
    <LogDrawer v-model="uiStore.showLogDrawer" />
    <RebalanceDialog />
    <CloseDialog />
    <WeightConfigDialog v-model="uiStore.showWeightDialog" />
    <ProgressBar />
    <AccessKeyDialog />
    <AppSnackbar />
  </v-app>
</template>

<script setup lang="ts">
import { onMounted, ref, watch, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useDisplay, useTheme } from 'vuetify'
import { useUiStore } from '@/stores/uiStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { useAuthStore } from '@/stores/authStore'
import websocketService from '@/services/websocket'

// 导入所有全局组件
import LogDrawer from '@/components/LogDrawer.vue'
import RebalanceDialog from '@/components/RebalanceDialog.vue'
import CloseDialog from '@/components/CloseDialog.vue'
import WeightConfigDialog from '@/components/WeightConfigDialog.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import AccessKeyDialog from '@/components/AccessKeyDialog.vue'
import AppSnackbar from '@/components/AppSnackbar.vue'

const router = useRouter()
const routes = router.getRoutes().filter((r) => r.meta && r.meta.title && r.meta.icon)

// 初始化所有需要的 store
const uiStore = useUiStore()
const settingsStore = useSettingsStore()
const authStore = useAuthStore()

// Vuetify 响应式和主题相关的 hooks
const { mdAndUp } = useDisplay()
const theme = useTheme()

// 根据当前主题动态计算图标
const themeIcon = computed(() =>
  uiStore.theme === 'dark' ? 'mdi-weather-sunny' : 'mdi-weather-night',
)

const drawer = ref(mdAndUp.value)

// 手机端：路由变化后自动收起抽屉，避免抽屉盖住页面让用户误以为点击无效
const currentRoute = useRoute()
watch(
  () => currentRoute.path,
  () => {
    if (!mdAndUp.value) drawer.value = false
  },
)

// 应用初始化函数
const initializeApp = async () => {
  // 只有在认证通过后才执行初始化
  if (authStore.isAuthenticated) {
    try {
      await settingsStore.fetchSettings()
      await uiStore.checkInitialStatus()
      websocketService.connect()
    } catch (error) {
      console.error('应用初始化失败:', error)
      if (!String(error).includes('403')) {
        uiStore.setStatus('应用初始化失败', false)
      }
    }
  }
}

// 组件挂载时尝试初始化
onMounted(() => {
  initializeApp()
})

// 监听认证状态的变化
// 当用户输入密钥后，isAuthenticated会变为true，从而触发初始化
watch(
  () => authStore.isAuthenticated,
  (isAuth) => {
    if (isAuth) {
      initializeApp()
    }
  },
)
</script>

<style>
/* 页面外壳：统一最大宽度与内边距，超宽屏不会把表格拉到整行 */
.page-shell {
  max-width: 1600px;
  margin: 0 auto;
  padding: 16px 20px;
}
@media (max-width: 600px) {
  .page-shell {
    padding: 12px 12px;
  }
}
.drawer-brand {
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>
