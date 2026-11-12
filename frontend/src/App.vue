<!-- frontend/src/App.vue -->
<!-- 应用外壳：应用栏（汉堡移左 / 状态 chip 手机只显示圆点）、导航抽屉（md+ 常驻，
     手机 overlay + 「更多」入口）、底部 Tab 栏（手机专用）、v-main 底部留白按 hasDock 声明 -->
<template>
  <v-app>
    <v-app-bar app density="compact">
      <!-- 汉堡移到左侧：手机端主入口是底部 Tab，抽屉只承载「更多」 -->
      <v-app-bar-nav-icon
        class="d-md-none"
        aria-label="打开导航菜单"
        @click="drawer = !drawer"
      />

      <v-toolbar-title>Web 交易终端</v-toolbar-title>

      <v-spacer></v-spacer>

      <!-- 状态 chip：<600px 只显示 8px 圆点，避免 375px 下五个元素互相挤压 -->
      <v-chip :color="uiStore.statusColor" class="mr-2" label>
        <span class="status-dot" aria-hidden="true"></span>
        <span class="d-none d-sm-inline">{{ uiStore.statusMessage }}</span>
      </v-chip>

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

    <!-- 桌面：常驻侧栏（含 primaryNav + secondaryNav）。
         手机：单独的临时抽屉，只放 secondaryNav（primaryNav 已在底部 Tab）。
         两个实例分开写而不是用 :permanent 翻转 —— 同一个实例切换 permanent 时
         Vuetify 会残留内联宽度与位移，手机上「关闭」状态依然可见并压住内容。 -->
    <v-navigation-drawer v-if="mdAndUp" permanent app>
      <div class="drawer-brand px-4 py-3">
        <span class="text-subtitle-1 font-weight-medium">交易终端</span>
        <div class="text-caption text-medium-emphasis">Signals · Positions · Risk</div>
      </div>
      <v-divider />
      <v-list nav density="compact">
        <v-list-item
          v-for="item in primaryNav"
          :key="item.path"
          :prepend-icon="item.icon"
          :title="item.title"
          :to="item.path"
          exact
        ></v-list-item>
        <v-divider class="my-2"></v-divider>
        <v-list-item
          v-for="item in secondaryNav"
          :key="item.path"
          :prepend-icon="item.icon"
          :title="item.title"
          :to="item.path"
          exact
        ></v-list-item>
      </v-list>
    </v-navigation-drawer>

    <v-navigation-drawer v-else v-model="drawer" temporary :width="280" app>
      <div class="drawer-brand px-4 py-3">
        <div class="d-flex align-center">
          <span class="text-subtitle-1 font-weight-medium">更多</span>
          <v-spacer></v-spacer>
          <v-btn icon="mdi-close" size="small" aria-label="关闭菜单" @click="drawer = false" />
        </div>
        <div class="text-caption text-medium-emphasis">周期报告 · 设置</div>
      </div>
      <v-divider />
      <v-list nav density="comfortable">
        <v-list-item
          v-for="item in secondaryNav"
          :key="item.path"
          :prepend-icon="item.icon"
          :title="item.title"
          :to="item.path"
          exact
        ></v-list-item>
      </v-list>
    </v-navigation-drawer>

    <!-- with-dock：路由 meta.hasDock 驱动底部留白（base.css §2.3），不再全局预留 -->
    <v-main :class="{ 'with-dock': hasDock }">
      <v-container fluid class="page-shell">
        <router-view />
      </v-container>
    </v-main>

    <!-- 手机底部 Tab 栏：「更多」打开的就是上面这个抽屉 -->
    <BottomTabBar @open-more="drawer = true" />

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
import { useRoute } from 'vue-router'
import { useDisplay, useTheme } from 'vuetify'
import { useUiStore } from '@/stores/uiStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { useAuthStore } from '@/stores/authStore'
import websocketService from '@/services/websocket'
import { primaryNav, secondaryNav } from '@/config/nav'
import BottomTabBar from '@/components/BottomTabBar.vue'

// 导入所有全局组件
import LogDrawer from '@/components/LogDrawer.vue'
import RebalanceDialog from '@/components/RebalanceDialog.vue'
import CloseDialog from '@/components/CloseDialog.vue'
import WeightConfigDialog from '@/components/WeightConfigDialog.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import AccessKeyDialog from '@/components/AccessKeyDialog.vue'
import AppSnackbar from '@/components/AppSnackbar.vue'

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

// 手机抽屉默认关闭；桌面用独立的常驻实例（见模板），两者不共用状态。
const drawer = ref(false)

// 从桌面切回手机时，抽屉必须回到关闭态（否则一进小屏就盖住页面）
watch(mdAndUp, (up) => {
  if (up) drawer.value = false
})

// 当前页面是否带固定操作条 → v-main 的底部留白交给 base.css 的 .with-dock 规则
const currentRoute = useRoute()
const hasDock = computed(() => currentRoute.meta.hasDock === true)

// 手机端：路由变化后自动收起抽屉，避免抽屉盖住页面让用户误以为点击无效
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
/* 状态 chip 里的 8px 圆点：<600px 时是唯一可见内容，颜色跟随 chip */
.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}
</style>
