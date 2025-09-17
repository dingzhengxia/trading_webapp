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

    <!-- App-level Dialogs and Components -->
    <LogDrawer v-model="uiStore.showLogDrawer" temporary />
    <RebalanceDialog />
    <CloseDialog />
    <WeightConfigDialog v-model="uiStore.showWeightDialog" />
    <ProgressBar />

    <!-- 新增：访问密钥输入对话框 -->
    <AccessKeyDialog />

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
import AccessKeyDialog from '@/components/AccessKeyDialog.vue'; // 导入新组件
import CoinPoolsDialog from '@/components/CoinPoolsManager.vue'; // 确保导入

const router = useRouter();
const routes = router.getRoutes().filter(r => r.meta && r.meta.title && r.meta.icon);

const uiStore = useUiStore();
const settingsStore = useSettingsStore();
const { mdAndUp } = useDisplay();

const drawer = ref(mdAndUp.value);

onMounted(async () => {
  try {
    // 严格的、同步的启动流程
    await settingsStore.fetchSettings();
    const isTaskRunningInitially = await uiStore.checkInitialStatus();
    websocketService.connect();
    if (isTaskRunningInitially) {
      const { usePositionStore } = await import('@/stores/positionStore');
      usePositionStore().fetchPositions();
    }
  } catch (error) {
    console.error("应用初始化失败:", error);
    // 密钥错误会在api拦截器中处理，这里捕获其他可能的初始化错误
    if (!String(error).includes('403')) {
        uiStore.setStatus("应用初始化失败", false);
    }
  }
});
</script>

<style>
/* 保持样式为空，让 Vuetify 自动处理布局 */
</style>
