<!-- 文件路径: frontend/src/App.vue (已修复移动端显示问题) -->
<template>
  <v-app>
    <!-- App Bar 保持不变 -->
    <v-app-bar app density="compact">
      <v-app-bar-nav-icon @click="drawer = !drawer" class="d-md-none"></v-app-bar-nav-icon>
      <v-toolbar-title>Web 交易终端</v-toolbar-title>
      <v-spacer></v-spacer>
      <v-chip :color="uiStore.statusColor" class="mr-4" label>{{ uiStore.statusMessage }}</v-chip>
      <!-- 点击按钮现在会调用 uiStore.toggleLogDrawer 来控制显示/隐藏 -->
      <v-btn icon @click="uiStore.toggleLogDrawer()">
        <v-badge :content="uiStore.logStore.logs.length" color="error" :model-value="uiStore.logStore.logs.length > 0">
          <v-icon>mdi-console-line</v-icon>
        </v-badge>
      </v-btn>
    </v-app-bar>

    <!-- 左侧导航栏保持不变 -->
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

    <!-- 底部导航栏保持不变 -->
    <v-bottom-navigation v-if="$vuetify.display.smAndDown" app grow>
       <v-btn v-for="route in routes" :key="`bottom-${route.name?.toString()}`" :to="route.path">
        <v-icon>{{ route.meta.icon }}</v-icon>
        <span>{{ route.meta.title }}</span>
      </v-btn>
    </v-bottom-navigation>

    <!-- 主内容区保持不变 -->
    <v-main>
      <v-container fluid>
        <router-view />
      </v-container>
    </v-main>

    <!-- --- 核心修改在这里 --- -->
    <!-- LogDrawer 组件现在通过 v-model 直接绑定到 uiStore.showLogDrawer -->
    <!-- 它不再是 permanent (永久显示)，而是根据 v-model 的值来决定是否显示 -->
    <!-- 添加 temporary 属性使其在小屏幕上表现为临时抽屉，点击外部会自动关闭 -->
    <LogDrawer v-model="uiStore.showLogDrawer" temporary />
    <!-- ----------------------- -->

    <!-- 其他 Dialogs 保持不变 -->
    <RebalanceDialog />
    <CloseDialog />
    <WeightConfigDialog v-model="uiStore.showWeightDialog" />
    <ProgressBar />
  </v-app>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useDisplay } from 'vuetify';
import { useUiStore } from '@/stores/uiStore';
import { useSettingsStore } from '@/stores/settingsStore';
import websocketService from '@/services/websocket';

// --- 核心修改在这里 ---
// 不再直接引用和修改 LogDrawer 组件，而是让 App.vue 统一管理其显示状态
import LogDrawer from '@/components/LogDrawer.vue';
// -----------------------

import RebalanceDialog from '@/components/RebalanceDialog.vue';
import CloseDialog from '@/components/CloseDialog.vue';
import WeightConfigDialog from '@/components/WeightConfigDialog.vue';
import ProgressBar from '@/components/ProgressBar.vue';

const router = useRouter();
const routes = router.getRoutes().filter(r => r.meta.title && r.meta.icon);

const uiStore = useUiStore();
const settingsStore = useSettingsStore();
const { mdAndUp } = useDisplay();

// 左侧导航栏的 drawer 状态管理保持不变
const drawer = ref(mdAndUp.value);

onMounted(() => {
  settingsStore.fetchSettings();
  websocketService.connect();
});
</script>

<style>
/* 样式保持不变 */
main.v-main {
  padding-bottom: 56px !important;
}
.v-footer ~ main.v-main {
    padding-bottom: calc(56px + 48px) !important;
}

@media (min-width: 960px) {
  main.v-main {
    padding-bottom: 0 !important;
  }
  .v-footer ~ main.v-main {
    padding-bottom: 48px !important;
  }
}
</style>
