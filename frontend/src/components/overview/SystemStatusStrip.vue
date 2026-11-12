<!-- frontend/src/components/overview/SystemStatusStrip.vue -->
<!-- 总览页系统状态条（spec 2026-11-13 B1）：扫描 / 自动开仓 / 风控 / 连接 四个可点击状态块。
     异常项用 error 色描边，整块可点击跳转对应页面；纯展示组件，数据由总览页轮询后传入。 -->
<template>
  <div class="status-strip-grid">
    <v-card
      v-for="item in items"
      :key="item.key"
      :to="item.to"
      variant="flat"
      class="status-cell"
      :class="{ 'status-cell--error': !item.ok }"
    >
      <div class="d-flex align-center ga-2">
        <v-icon size="16" :color="item.ok ? 'success' : 'error'">{{ item.icon }}</v-icon>
        <span class="text-caption text-medium-emphasis">{{ item.label }}</span>
      </div>
      <div class="status-cell__value" :class="{ 'text-error': !item.ok }">{{ item.value }}</div>
      <div v-if="item.sub" class="text-caption text-medium-emphasis text-truncate">{{ item.sub }}</div>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatIsoTime } from '@/utils/format'

const props = defineProps<{
  scanEnabled: boolean
  scanRunning: boolean
  lastScanAt: string | null
  autoTradeEnabled: boolean
  protectionEnabled: boolean
  protectionRunning: boolean
  guardedCount: number
  connectionText: string
  connectionOk: boolean
}>()

interface StatusCell {
  key: string
  label: string
  icon: string
  value: string
  sub?: string
  ok: boolean
  to: string
}

const items = computed<StatusCell[]>(() => [
  {
    key: 'scan',
    label: '信号扫描',
    icon: 'mdi-radar',
    value: props.scanEnabled ? '已开启' : '已关闭',
    sub: props.scanRunning ? '扫描进行中' : `上次扫描 ${formatIsoTime(props.lastScanAt)}`,
    ok: props.scanEnabled,
    to: '/signals',
  },
  {
    key: 'auto',
    label: '自动开仓',
    icon: 'mdi-robot-outline',
    value: props.autoTradeEnabled ? '已启用' : '已停用',
    ok: props.autoTradeEnabled,
    to: '/signals',
  },
  {
    key: 'protection',
    label: '仓位风控',
    icon: 'mdi-shield-check-outline',
    value: props.protectionRunning ? '守护中' : props.protectionEnabled ? '已启用' : '已停用',
    sub: `守卫 ${props.guardedCount} 个仓位`,
    ok: props.protectionEnabled && props.protectionRunning,
    to: '/protection',
  },
  {
    key: 'connection',
    label: '连接状态',
    icon: 'mdi-lan-connect',
    value: props.connectionText,
    ok: props.connectionOk,
    to: '/trading',
  },
])
</script>

<style scoped>
/* xs 两列、sm 起四列；与 KPI 行的 cols="6" sm="3" 网格节奏一致 */
.status-strip-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
@media (min-width: 960px) {
  .status-strip-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
.status-cell {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
  padding: 10px 12px;
  min-width: 0;
}
.status-cell--error {
  border-color: rgb(var(--v-theme-error));
}
.status-cell__value {
  font-size: 14px;
  font-weight: 600;
  margin: 2px 0;
}
</style>
