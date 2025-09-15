<template>
  <v-navigation-drawer
    location="right"
    permanent
    width="400"
    class="log-drawer"
  >
    <v-toolbar density="compact">
      <v-toolbar-title class="text-subtitle-1">执行日志</v-toolbar-title>
      <v-spacer></v-spacer>
      <!-- 点击时，通过 emit 通知父组件清空日志 -->
      <v-btn icon="mdi-delete" size="small" @click="emit('clearLogs')" title="清空日志"></v-btn>
    </v-toolbar>

    <!-- 使用 v-virtual-scroll 提高大量日志渲染时的性能 -->
    <v-virtual-scroll :items="props.logs" height="calc(100vh - 48px)">
      <template v-slot:default="{ item: log, index }">
        <v-list-item :key="index" class="py-1 px-2">
          <div class="log-entry" :class="logLevelColor(log.level)">
            <span class="log-timestamp text-grey">[{{ log.timestamp }}]</span>
            <span class="log-message">{{ log.message }}</span>
          </div>
        </v-list-item>
      </template>
    </v-virtual-scroll>
  </v-navigation-drawer>
</template>

<script setup lang="ts">
import type { Log } from '@/types/ui';

// 步骤1: 定义从父组件接收的 logs prop 和要发出的 clearLogs emit
const props = defineProps<{
  logs: Log[];
}>();

const emit = defineEmits<{
  (e: 'clearLogs'): void;
}>();

// 步骤2: 样式函数保持不变，用于根据日志级别显示不同颜色
const logLevelColor = (level: string) => {
  switch (level) {
    case 'success':
      return 'text-success';
    case 'error':
      return 'text-error';
    case 'warning':
      return 'text-orange';
    case 'info':
        return 'text-info';
    default:
      return '';
  }
};
</script>

<style scoped>
.log-drawer {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 0.8rem;
}
.log-entry {
  display: flex;
  align-items: flex-start;
  line-height: 1.4;
}
.log-timestamp {
  flex-shrink: 0;
  margin-right: 8px;
}
.log-message {
  word-break: break-all;
  white-space: pre-wrap;
}
</style>
