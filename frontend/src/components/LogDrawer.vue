<!-- 文件路径: frontend/src/components/LogDrawer.vue (已适配 v-model) -->
<template>
  <!-- v-model="show" 会自动处理抽屉的打开和关闭 -->
  <v-navigation-drawer v-model="show" location="right" width="400" class="log-drawer">
    <v-toolbar density="compact">
      <v-toolbar-title class="text-subtitle-1">执行日志</v-toolbar-title>
      <v-spacer></v-spacer>
      <!-- 清空日志的 emit 保持不变 -->
      <v-btn icon="mdi-delete" size="small" @click="logStore.clearLogs()" title="清空日志"></v-btn>
    </v-toolbar>

    <!-- 日志列表显示逻辑保持不变 -->
    <v-virtual-scroll :items="logStore.logs" height="calc(100vh - 48px)">
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
import { computed } from 'vue'
import { useLogStore } from '@/stores/logStore'
import type { LogEntry } from '@/models/types' // <-- 修正为 LogEntry

// --- 核心修改在这里 ---
// 使用 defineModel 来创建一个双向绑定的 v-model
const show = defineModel<boolean>()
// -----------------------

const logStore = useLogStore()

// 样式函数保持不变
const logLevelColor = (level: string) => {
  switch (level) {
    case 'success':
      return 'text-success'
    case 'error':
      return 'text-error'
    case 'warning':
      return 'text-orange'
    case 'info':
      return 'text-info'
    default:
      return ''
  }
}
</script>

<style scoped>
/* 样式保持不变 */
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
