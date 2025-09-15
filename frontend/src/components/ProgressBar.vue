<!-- frontend/src/components/ProgressBar.vue (最终布局优化版) -->
<template>
  <v-footer v-if="uiStore.progress.show" app class="pa-0" style="z-index: 1008; border-top: 1px solid rgba(255, 255, 255, 0.12);">
    <!-- v-card 设置为 height: 100% 并直接作为 flex 容器 -->
    <v-card flat tile class="d-flex align-center px-4 w-100" :color="cardColor" height="48px">

        <!-- 左侧任务名 -->
        <span class="text-caption font-weight-bold flex-shrink-0 mr-4">
          {{ uiStore.progress.task_name }}
        </span>

        <!-- 中间进度条 -->
        <v-progress-linear
          :model-value="progressPercentage"
          :color="progressColor"
          height="20"
          striped
          stream
          class="flex-grow-1"
        >
          <strong class="text-white">{{ Math.ceil(progressPercentage) }}%</strong>
        </v-progress-linear>

        <!-- 右侧详细统计 -->
        <div class="d-flex flex-shrink-0 ml-4 align-center text-caption">
          <v-chip size="x-small" color="green" label class="mr-2">
            成功: {{ uiStore.progress.success_count }}
          </v-chip>
          <v-chip size="x-small" :color="uiStore.progress.failed_count > 0 ? 'red' : 'grey'" label class="mr-2">
            失败: {{ uiStore.progress.failed_count }}
          </v-chip>
          <v-chip size="x-small" color="blue-grey" label>
            总数: {{ uiStore.progress.total }}
          </v-chip>
        </div>

        <!-- 停止按钮 -->
        <v-btn
          color="white"
          variant="text"
          size="small"
          @click="stopTrading"
          :disabled="!uiStore.isRunning"
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

const stopTrading = async () => {
  try {
    await api.post('/api/trading/stop');
    uiStore.logStore.addLog({ message: "前端已发送停止指令。", level: 'warning', timestamp: new Date().toLocaleTimeString() });
  } catch(e: any) {
    uiStore.logStore.addLog({ message: `发送停止指令失败: ${e.message}`, level: "error", timestamp: new Date().toLocaleTimeString() });
  }
};

const cardColor = computed(() => {
  const hasErrors = uiStore.progress.failed_count > 0;
  if (uiStore.progress.is_final) {
    return hasErrors ? 'red-darken-3' : 'green-darken-3';
  }
  return hasErrors ? 'red-darken-3' : 'blue-grey-darken-3';
});

const progressColor = computed(() => {
  return uiStore.progress.failed_count > 0 ? 'red-lighten-2' : 'light-blue-accent-3';
});
</script>
