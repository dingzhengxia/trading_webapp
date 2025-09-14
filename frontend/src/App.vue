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

    <v-bottom-navigation v-if="$vuetify.display.smAndDown" app grow>
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

    <LogDrawer />
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

import LogDrawer from '@/components/LogDrawer.vue';
import RebalanceDialog from '@/components/RebalanceDialog.vue';
import CloseDialog from '@/components/CloseDialog.vue';
import WeightConfigDialog from '@/components/WeightConfigDialog.vue';
import ProgressBar from '@/components/ProgressBar.vue';

const router = useRouter();
const routes = router.getRoutes().filter(r => r.meta.title && r.meta.icon);

const uiStore = useUiStore();
const settingsStore = useSettingsStore();
const { mdAndUp } = useDisplay();

const drawer = ref(mdAndUp.value);

onMounted(() => {
  settingsStore.fetchSettings();
  websocketService.connect();
});
</script>

<style>
main.v-main {
  padding-bottom: 56px !important; /* 底部导航的高度 */
}
/* 当进度条显示时，增加额外的 padding */
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
