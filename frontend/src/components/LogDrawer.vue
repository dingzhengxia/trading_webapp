<!-- 文件路径: frontend/src/components/LogDrawer.vue (已适配 v-model) -->
<!--
  执行日志抽屉：
  - 级别筛选（全部 / 重要 = 成功+警告+错误 / 错误）+ 关键字过滤；
  - 仓位保护的心跳类 INFO 已由后端 ui_log_sink 收口，不再进抽屉；这里再兜一层，方便定位真正要看的日志。
-->
<template>
  <v-navigation-drawer v-model="show" location="right" width="420" class="log-drawer">
    <v-toolbar density="compact">
      <v-toolbar-title class="text-subtitle-1">执行日志</v-toolbar-title>
      <v-spacer></v-spacer>
      <!-- 清空日志的 emit 保持不变 -->
      <v-btn icon="mdi-delete" size="small" @click="logStore.clearLogs()" title="清空日志"></v-btn>
    </v-toolbar>

    <div class="px-2 pt-2">
      <div class="d-flex align-center ga-1 flex-wrap">
        <v-chip
          v-for="option in FILTERS"
          :key="option.value"
          size="x-small"
          :color="activeFilter === option.value ? 'primary' : undefined"
          :variant="activeFilter === option.value ? 'flat' : 'tonal'"
          @click="activeFilter = option.value"
        >
          {{ option.label }} {{ countOf(option.value) }}
        </v-chip>
      </div>
      <v-text-field
        v-model="keyword"
        density="compact"
        variant="outlined"
        hide-details
        clearable
        placeholder="过滤关键字（币种 / 策略 / 文本）"
        prepend-inner-icon="mdi-magnify"
        class="mt-2"
      ></v-text-field>
      <div class="text-caption text-medium-emphasis mt-1">
        显示 {{ visibleLogs.length }} / {{ logStore.logs.length }} 条
      </div>
    </div>

    <v-virtual-scroll :items="visibleLogs" height="calc(100vh - 170px)" class="mt-2">
      <template v-slot:default="{ item, index }">
        <v-list-item :key="index" class="py-1 px-2">
          <div class="log-entry" :class="logLevelColor(toLogEntry(item).level)">
            <span class="log-timestamp text-grey">[{{ toLogEntry(item).timestamp }}]</span>
            <span class="log-message">{{ toLogEntry(item).message }}</span>
          </div>
        </v-list-item>
      </template>
    </v-virtual-scroll>
  </v-navigation-drawer>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useLogStore } from '@/stores/logStore'
import type { LogEntry } from '@/models/types'

type FilterValue = 'all' | 'important' | 'error'

const FILTERS: { value: FilterValue; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'important', label: '重要' },
  { value: 'error', label: '错误' },
]

// 重要 = 会改变仓位或需要人看一眼的事件；info/normal 是例行流水
const IMPORTANT_LEVELS: LogEntry['level'][] = ['success', 'warning', 'error']

// v-virtual-scroll 的 slot item 类型为 unknown，这里收窄为 LogEntry
const toLogEntry = (item: unknown): LogEntry => item as LogEntry

// 使用 defineModel 来创建一个双向绑定的 v-model
const show = defineModel<boolean>()

const logStore = useLogStore()
const activeFilter = ref<FilterValue>('all')
const keyword = ref('')

const countOf = (filter: FilterValue): number => {
  if (filter === 'all') return logStore.logs.length
  if (filter === 'error') return logStore.logs.filter((log) => log.level === 'error').length
  return logStore.logs.filter((log) => IMPORTANT_LEVELS.includes(log.level)).length
}

const visibleLogs = computed<LogEntry[]>(() => {
  const word = keyword.value.trim().toUpperCase()
  return logStore.logs.filter((log) => {
    const matchesLevel =
      activeFilter.value === 'all'
        ? true
        : activeFilter.value === 'error'
          ? log.level === 'error'
          : IMPORTANT_LEVELS.includes(log.level)
    if (!matchesLevel) return false
    return word ? log.message.toUpperCase().includes(word) : true
  })
})

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
