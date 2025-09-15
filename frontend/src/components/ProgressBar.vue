<!-- frontend/src/components/ProgressBar.vue (最终优化版) -->
<template>
  <v-footer v-if="uiStore.progress.show" app class="pa-0" style="z-index: 1008; border-top: 1px solid rgba(255, 255, 255, 0.12);">
    <v-card flat tile class="d-flex align-center px-2 px-sm-4 w-100" :color="cardColor" height="48px">

      <!-- 左侧任务名 -->
      <span class="text-caption font-weight-bold flex-shrink-0 mr-4 d-none d-md-flex">
        {{ uiStore.progress.task_name }}
      </span>

      <!-- 核心修改：将统计数字放在 v-progress-linear 的插槽中 -->
      <v-progress-linear
        :model-value="progressPercentage"
        :color="progressColor"
        :indeterminate="uiStore.isStopping"
        height="25"
        rounded
        :striped="!uiStore.isStopping"
        stream
        class="flex-grow-1 font-weight-bold"
      >
        <template v-slot:default>
          <div class="d-flex justify-space-between align-center w-100 px-2 text-white text-caption">
            <!-- 左侧：任务名 (手机端) -->
            <span class="d-md-none">{{ uiStore.progress.task_name }}</span>
            <v-spacer class="d-md-none"></v-spacer>

            <!-- 中间：进度百分比 -->
            <span v-if="!uiStore.isStopping" class="mx-2">{{ Math.ceil(progressPercentage) }}%</span>
            <span v-else class="mx-2">正在停止...</span>

            <!-- 右侧：成功/失败/总数 统计 -->
            <v-spacer></v-spacer>
            <div class="d-flex align-center">
              <v-icon size="small" color="light-green-accent-3" class="mr-1">mdi-check-circle</v-icon>
              <span>{{ uiStore.progress.success_count }}</span>
              <span class="mx-1">/</span>
              <v-icon size="small" :color="uiStore.progress.failed_count > 0 ? 'red-accent-2' : 'grey-lighten-1'" class="mr-1">mdi-close-circle</v-icon>
              <span>{{ uiStore.progress.failed_count }}</span>
              <span class="mx-1">/</span>
              <v-icon size="small" color="grey-lighten-1" class="mr-1">mdi-gauge-full</v-icon>
              <span>{{ uiStore.progress.total }}</span>
            </div>
          </div>
        </template>
      </v-progress-linear>

      <!-- 停止按钮 -->
      <v-btn
        color="white"
        variant="text"
        size="small"
        @click="stopTrading"
        :disabled="!uiStore.isRunning || uiStore.isStopping"
        :loading="uiStore.isStopping"
        class="flex-shrink-0 ml-2"
        icon="mdi-stop-circle-outline"
      >
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
