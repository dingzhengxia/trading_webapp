<!-- frontend/src/components/LogDrawer.vue -->
<template>
  <v-dialog
    v-model="uiStore.showLogDrawer"
    location="bottom"
    fullscreen
    transition="dialog-bottom-transition"
    scrollable
  >
    <v-card class="d-flex flex-column" style="height: 50vh; position: fixed; bottom: 0; left: 0; right: 0;">
      <v-toolbar density="compact" color="blue-grey-darken-3">
        <v-toolbar-title class="text-subtitle-1">执行日志</v-toolbar-title>
        <v-spacer></v-spacer>
        <v-btn variant="text" icon="mdi-delete-sweep" @click="uiStore.logStore.clearLogs"></v-btn>
        <v-btn variant="text" icon="mdi-close" @click="uiStore.closeLogDrawer()"></v-btn>
      </v-toolbar>

      <v-card-text class="flex-grow-1 pa-0">
          <div ref="logContainer" class="log-container fill-height">
            <p v-for="(log, index) in uiStore.logStore.logs" :key="index" :class="`log-${log.level}`" class="ma-0 pa-1">
              <span class="log-timestamp">[{{ log.timestamp }}]</span> {{ log.message }}
            </p>
          </div>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useUiStore } from '@/stores/uiStore';
import { ref, watch, nextTick } from 'vue';

const uiStore = useUiStore();
const logContainer = ref<HTMLDivElement | null>(null);

watch(() => uiStore.logStore.logs, async () => {
  await nextTick();
  if (logContainer.value) {
    logContainer.value.scrollTop = 0; // 滚动到顶部 (因为是 column-reverse)
  }
}, { deep: true });
</script>

<style scoped>
.log-container {
  background-color: #1E1E1E;
  color: #D4D4D4;
  font-family: 'Courier New', Courier, monospace;
  font-size: 0.85rem;
  overflow-y: auto;
  white-space: pre-wrap;
  display: flex;
  flex-direction: column-reverse; /* 新日志在顶部 */
  padding: 8px;
}
.log-timestamp { color: #888; }
.log-info { color: #569CD6; }
.log-success { color: #4EC9B0; }
.log-warning { color: #CE9178; }
.log-error { color: #F44747; font-weight: bold; }
</style>
