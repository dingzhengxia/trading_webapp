<!-- frontend/src/components/ProgressBar.vue (完整代码) -->
<template>
  <v-footer v-if="uiStore.progress.show" app class="pa-0" style="z-index: 1008; border-top: 1px solid rgba(255, 255, 255, 0.12);">
    <v-card flat tile class="d-flex align-center px-4 w-100" :color="cardColor" height="48px">

        <span class="text-caption font-weight-bold flex-shrink-0 mr-4 d-none d-sm-flex">
          {{ uiStore.progress.task_name }}
        </span>

        <v-progress-linear
          :model-value="progressPercentage"
          :color="progressColor"
          :indeterminate="uiStore.isStopping"
          height="20"
          :striped="!uiStore.isStopping"
          stream
          class="flex-grow-1"
        >
          <strong v-if="!uiStore.isStopping" class="text-white">{{ Math.ceil(progressPercentage) }}%</strong>
           <strong v-else class="text-white">正在停止...</strong>
        </v-progress-linear>

        <div class="d-flex flex-shrink-0 ml-4 align-center text-caption">
          <v-chip size="x-small" color="green" label class="mr-1 mr-sm-2">
            <v-icon start icon="mdi-check-circle"></v-icon>
            {{ uiStore.progress.success_count }}
          </v-chip>
          <v-chip size="x-small" :color="uiStore.progress.failed_count > 0 ? 'red' : 'grey'" label class="mr-1 mr-sm-2">
            <v-icon start icon="mdi-close-circle"></v-icon>
            {{ uiStore.progress.failed_count }}
          </v-chip>
          <v-chip size="x-small" color="blue-grey" label class="d-none d-md-flex">
             总数: {{ uiStore.progress.total }}
          </v-chip>
        </div>

        <v-btn
          color="white"
          variant="text"
          size="small"
          @click="stopTrading"
          :disabled="!uiStore.isRunning || uiStore.isStopping"
          :loading="uiStore.isStopping"
          class="flex-shrink-0 ml-2"
        >
          ⏹ 停止
        </v-btn>

    </v-card>
  </v-footer>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useUiStore } from '@/stores/uiStore';
import api from '@/services/api';

const uiStore = useUiStore();

const progressPercentage = computed(() => {
  const total = uiStore.progress.total;
  if (total === 0) return 0;
  const processed = uiStore.progress.success_count + uiStore.progress.failed_count;
  return (processed / total) * 100;
});

const stopTrading = () => {
  uiStore.initiateStop();
  uiStore.logStore.addLog({ message: "前端已发送停止指令，等待后端确认...", level: 'warning', timestamp: new Date().toLocaleTimeString() });

  api.post('/api/trading/stop').catch(e => {
    uiStore.logStore.addLog({ message: `发送停止指令失败: ${e.message}`, level: "error", timestamp: new Date().toLocaleTimeString() });
    uiStore.setStatus("停止失败", false);
  });
};

const cardColor = computed(() => {
  if (uiStore.isStopping) return 'red-darken-3';
  const hasErrors = uiStore.progress.failed_count > 0;
  if (uiStore.progress.is_final) {
    return hasErrors ? 'red-darken-3' : 'green-darken-3';
  }
  return hasErrors ? 'red-darken-3' : 'blue-grey-darken-3';
});

const progressColor = computed(() => {
  if (uiStore.isStopping) return 'white';
  return uiStore.progress.failed_count > 0 ? 'red-lighten-2' : 'light-blue-accent-3';
});
</script>
