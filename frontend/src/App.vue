<!-- frontend/src/App.vue (最终完整版) -->
<template>
  <v-app>
    <v-app-bar app density="compact">
      <v-app-bar-nav-icon @click="drawer = !drawer" class="d-md-none"></v-app-bar-nav-icon>
      <v-toolbar-title>Web 交易终端</v-toolbar-title>
      <v-spacer></v-spacer>
      <v-chip :color="uiStore.statusColor" class="mr-4" label>{{ uiStore.statusMessage }}</v-chip>
      <v-btn icon @click="uiStore.toggleLogDrawer()">
        <v-badge :content="uiStore.logStore.logs.length" color="error" :model-value="uiStore.logStore.logs.length > 0">
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

    <v-bottom-navigation v-if="$vuetify.display.smAndDown" app grow style="z-index: 1007;">
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

    <LogDrawer v-model="uiStore.showLogDrawer" temporary />
    <RebalanceDialog />
    <CloseDialog />
    <WeightConfigDialog v-model="uiStore.showWeightDialog" />
    <ProgressBar />
  </v-app>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useDisplay } from 'vuetify';
import { useUiStore } from '@/stores/uiStore';
import { useSettingsStore } from '@/stores/settingsStore';
import websocketService from '@/services/websocket';

import LogDrawer from '@/components/LogDrawer.vue';
import RebalanceDialog from '@/components/RebalanceDialog.vue';
import CloseDialog from '@/components/CloseDialog.vue';
import WeightConfigDialog from '@/components/WeightConfigDialog.vue';
import ProgressBar from '@/components/ProgressBar.vue';

const router = useRouter();
const routes = router.getRoutes().filter(r => r.meta && r.meta.title && r.meta.icon);

const uiStore = useUiStore();
const settingsStore = useSettingsStore();
const { mdAndUp } = useDisplay();

const drawer = ref(mdAndUp.value);

onMounted(async () => {
  try {
    // 步骤 1: 获取应用的基础配置
    await settingsStore.fetchSettings();

    // 步骤 2: 检查并恢复持久化的任务状态
    const isTaskRunningInitially = await uiStore.checkInitialStatus();

    // 步骤 3: 在所有初始状态都已确定后，再连接WebSocket
    websocketService.connect();

    // 步骤 4: 如果恢复时发现有任务在运行，主动获取一次最新的仓位数据
    if (isTaskRunningInitially) {
      // 动态导入以避免循环依赖
      const { usePositionStore } = await import('@/stores/positionStore');
      usePositionStore().fetchPositions();
    }
  } catch (error) {
    console.error("应用初始化失败:", error);
    uiStore.setStatus("应用初始化失败", false);
  }
});
</script>

<style>
/* 移除自定义的 main padding-bottom, 让 Vuetify 的 app 属性自动处理布局 */
</style>
