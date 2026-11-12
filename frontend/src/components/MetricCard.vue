<!-- frontend/src/components/MetricCard.vue -->
<!-- KPI 指标卡：替代页面顶部一排同权重的 tonal chip，让关键数字有视觉权重 -->
<template>
  <v-card variant="flat" class="metric-card h-100">
    <div class="d-flex align-center ga-2 mb-1">
      <v-icon v-if="icon" size="14" :color="iconColor" class="metric-icon">{{ icon }}</v-icon>
      <span class="text-caption text-medium-emphasis">{{ label }}</span>
      <v-spacer></v-spacer>
      <v-icon v-if="warning" size="14" color="error">mdi-alert-circle-outline</v-icon>
    </div>
    <div class="metric-value num" :class="valueClass">{{ value }}</div>
    <div v-if="hint" class="text-caption text-medium-emphasis mt-1 text-truncate">{{ hint }}</div>
  </v-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    label: string
    value: string | number
    hint?: string
    icon?: string
    /** 数字色彩：盈亏类用 up/down，状态类留空 */
    tone?: 'up' | 'down' | 'neutral'
    /** 是否高亮为异常（右上角挂一个红色提示点） */
    warning?: boolean
  }>(),
  { hint: '', icon: '', tone: 'neutral', warning: false },
)

const valueClass = computed(() => {
  if (props.tone === 'up') return 'text-up'
  if (props.tone === 'down') return 'text-down'
  return ''
})

const iconColor = computed(() => (props.warning ? 'error' : 'medium-emphasis'))
</script>

<style scoped>
.metric-card {
  background: rgba(var(--v-theme-surface), 1);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
  padding: 12px 14px;
}
.metric-value {
  font-size: 20px;
  font-weight: 600;
  line-height: 1.25;
  letter-spacing: -0.01em;
}
.metric-icon {
  opacity: 0.8;
}
</style>
