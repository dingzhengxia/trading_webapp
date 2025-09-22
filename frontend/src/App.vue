<!-- frontend/src/App.vue (完整代码) -->
<template>
  <v-app>
    <v-app-bar app density="compact">
      <v-app-bar-nav-icon @click="drawer = !drawer" class="d-md-none"></v-app-bar-nav-icon>
      <v-toolbar-title>Web 交易终端</v-toolbar-title>
      <v-spacer></v-spacer>
      <v-chip :color="uiStore.statusColor" class="mr-4" label>{{ uiStore.statusMessage }}</v-chip>

      <!-- 主题切换按钮 -->
      <v-btn
        icon
        @click="uiStore.toggleTheme(theme)"
        :title="`切换到${uiStore.theme === 'dark' ? '浅色' : '深色'}模式`"
      >
        <v-icon>{{ themeIcon }}</v-icon>
      </v-btn>

      <!-- 日志按钮 -->
      <v-btn icon @click="uiStore.toggleLogDrawer()">
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
      <v-list nav>
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

    <v-bottom-navigation v-if="$vuetify.display.smAndDown" app grow style="z-index: 1007">
      <v-btn v-for="route in routes" :key="`bottom-${route.name?.toString()}`" :to="route.path">
        <v-icon>{{ route.meta.icon }}</v-icon>
        <span>{{ route.meta.title }}</span>
      </v-btn>
    </v-bottom-navigation>

    <v-main>
      <v-container fluid>
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
    <Snackbar />
  </v-app>
</template>

<script setup lang="ts">
import { onMounted, ref, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
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
import Snackbar from '@/components/Snackbar.vue'

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
/* 保持样式为空，让 Vuetify 自动处理布局 */
</style>
