<template>
  <v-footer v-if="uiStore.progress.show" app class="pa-0" style="z-index: 1008;">
    <v-card flat tile class="flex" color="blue-grey-darken-3">
      <v-card-text class="py-2">
        <v-row align="center" no-gutters>
          <v-col cols="12" sm="4" md="3">
            <span class="text-caption font-weight-bold">
              {{ uiStore.progress.task_name }} ({{ uiStore.progress.current }} / {{ uiStore.progress.total }})
            </span>
          </v-col>

          <v-col cols="12" sm="5" md="7">
            <v-progress-linear
              :model-value="progressPercentage"
              color="light-blue-accent-3"
              height="20"
              striped
              stream
            >
              <strong class="text-white">{{ Math.ceil(progressPercentage) }}%</strong>
            </v-progress-linear>
          </v-col>

          <v-col cols="12" sm="3" md="2" class="text-sm-right pl-sm-4 mt-2 mt-sm-0">
            <v-btn
              color="error"
              variant="tonal"
              size="small"
              @click="stopTrading"
              :disabled="!uiStore.isRunning"
              block
            >
              ⏹ 停止执行
            </v-btn>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>
  </v-footer>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useUiStore } from '@/stores/uiStore';
import api from '@/services/api';

const uiStore = useUiStore();

const progressPercentage = computed(() => {
  if (uiStore.progress.total === 0) return 0;
  return (uiStore.progress.current / uiStore.progress.total) * 100;
});

const stopTrading = async () => {
  try {
    await api.post('/api/trading/stop');
    uiStore.logStore.addLog({ message: "前端已发送停止指令。", level: 'warning', timestamp: new Date().toLocaleTimeString() });
  } catch(e: any) {
    uiStore.logStore.addLog({ message: `发送停止指令失败: ${e.message}`, level: "error", timestamp: new Date().toLocaleTimeString() });
  }
};
</script>
