<!-- frontend/src/components/signals/SignalListPanel.vue -->
<!-- 信号列表：本页的主内容，首屏即可见。
     xs：9 列表格降级为卡片（§2.5 判据），可点展开看量能 / 前视 / 完整说明；
     sm+：保留表格 + 横滚 + 首列 sticky。工具栏右侧留 toolbar-append 插槽（信号页放「配置」按钮） -->
<template>
  <div>
    <div class="list-toolbar d-flex align-center flex-wrap ga-2 mb-3">
      <v-btn-toggle
        :model-value="direction"
        mandatory
        density="compact"
        variant="outlined"
        divided
        class="dir-toggle"
        @update:model-value="onDirectionChange"
      >
        <v-btn value="all" size="small">全部</v-btn>
        <v-btn value="long" size="small">做多</v-btn>
        <v-btn value="short" size="small">做空</v-btn>
        <v-btn value="neutral" size="small">观望</v-btn>
      </v-btn-toggle>

      <span class="text-caption text-medium-emphasis num">
        {{ signals.length }} / {{ total }} 条
      </span>

      <v-spacer></v-spacer>

      <span class="text-caption text-medium-emphasis d-none d-md-inline">每 10 秒自动刷新</span>
      <v-btn size="small" variant="text" prepend-icon="mdi-refresh" :loading="loading" @click="emit('refresh')">
        刷新
      </v-btn>
      <v-btn
        size="small"
        color="primary"
        variant="tonal"
        prepend-icon="mdi-magnify-scan"
        :loading="scanning"
        :disabled="scanning"
        @click="emit('scan')"
      >
        立即扫描
      </v-btn>
      <v-btn
        size="small"
        color="error"
        variant="text"
        prepend-icon="mdi-broom"
        :loading="clearing"
        :disabled="clearing || total === 0"
        @click="emit('clear')"
      >
        清空
      </v-btn>
      <slot name="toolbar-append"></slot>
    </div>

    <template v-if="signals.length > 0">
      <!-- ============ xs：卡片化 ============ -->
      <div class="d-md-none">
        <div v-for="signal in signals" :key="signal.id" class="signal-card">
          <button
            type="button"
            class="signal-card__head"
            :aria-expanded="isExpanded(signal.id)"
            @click="toggleExpand(signal.id)"
          >
            <!-- 头行：币种 + 方向徽章 + 时间 -->
            <div class="d-flex align-center ga-2">
              <span class="signal-card__symbol">{{ signal.symbol }}</span>
              <span class="dir-badge" :class="`dir-badge--${directionTone(signal.direction).key}`">
                <v-icon>{{ directionTone(signal.direction).icon }}</v-icon>
                {{ directionTone(signal.direction).label }}
              </span>
              <v-spacer />
              <span class="text-caption text-medium-emphasis">{{ formatTime(signal.created_at) }}</span>
            </div>
            <!-- 次行：策略 · 周期 · 价格 -->
            <div class="signal-card__meta">
              {{ strategyLabel(signal.strategy) }} · {{ signal.timeframe }} ·
              <span class="num">{{ formatPrice(signal.price) }}</span>
            </div>
            <!-- 第三行：量能达标色点 + 倍数（达标 up 色，否则中性） -->
            <div class="signal-card__vol d-flex align-center ga-1 text-caption" :class="volumeClass(signal)">
              <i class="vol-dot" :class="{ 'vol-dot--on': volumeOk(signal) }"></i>
              量能 {{ volumeLabel(signal) }}
              <v-spacer />
              <v-icon size="16" class="text-medium-emphasis">
                {{ isExpanded(signal.id) ? 'mdi-chevron-up' : 'mdi-chevron-down' }}
              </v-icon>
            </div>
          </button>

          <!-- 展开区：前视收益 + 完整说明（3 行 clamp） -->
          <div v-if="isExpanded(signal.id)" class="signal-card__body">
            <div class="text-caption">
              前视：<span :class="fwdClass(signal)">{{ fwdLabel(signal) }}</span>
            </div>
            <div class="signal-card__message">{{ plainMessage(signal.message) }}</div>
          </div>
        </div>
      </div>

      <!-- ============ sm+：表格（横滚 + 首列 sticky） ============ -->
      <div class="d-none d-md-block signal-table-wrap">
        <v-table density="compact" class="signal-table">
          <thead>
            <tr>
              <th class="text-left">时间</th>
              <th class="text-left">币种</th>
              <th class="text-left">方向</th>
              <th class="text-left">策略</th>
              <th class="text-left">周期</th>
              <th class="text-right">价格</th>
              <th class="text-right">量能</th>
              <th class="text-left">前视</th>
              <th class="text-left">标题 / 说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="signal in signals" :key="signal.id">
              <td class="text-caption text-medium-emphasis text-no-wrap">{{ formatTime(signal.created_at) }}</td>
              <td class="font-weight-medium text-no-wrap">{{ signal.symbol }}</td>
              <td>
                <span class="dir-badge" :class="`dir-badge--${directionTone(signal.direction).key}`">
                  <v-icon>{{ directionTone(signal.direction).icon }}</v-icon>
                  {{ directionTone(signal.direction).label }}
                </span>
              </td>
              <td class="text-no-wrap">{{ strategyLabel(signal.strategy) }}</td>
              <td class="text-no-wrap text-medium-emphasis">{{ signal.timeframe }}</td>
              <td class="text-right num text-no-wrap">{{ formatPrice(signal.price) }}</td>
              <td class="text-right num text-caption text-no-wrap" :class="volumeClass(signal)">
                {{ volumeLabel(signal) }}
              </td>
              <td class="text-no-wrap text-caption">
                <span :class="fwdClass(signal)">{{ fwdLabel(signal) }}</span>
              </td>
              <td class="signal-title">
                <div class="text-body-2">{{ signal.title }}</div>
                <div class="text-caption text-medium-emphasis signal-message">
                  {{ plainMessage(signal.message) }}
                </div>
              </td>
            </tr>
          </tbody>
        </v-table>
      </div>
    </template>

    <EmptyState
      v-else
      icon="mdi-radar"
      title="还没有信号"
      description="启用扫描后，命中的技术指标信号会显示在这里；也可以先手动触发一次扫描看看结果。"
      action-text="立即扫描一次"
      action-icon="mdi-magnify-scan"
      :action-loading="scanning"
      @action="emit('scan')"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { SignalRecord } from '@/models/types'
import EmptyState from '@/components/EmptyState.vue'
import { directionTone } from '@/utils/tone'
import { formatIsoTime as formatTime, formatSignedPercent } from '@/utils/format'

const props = withDefaults(
  defineProps<{
    /** 已按方向过滤后的信号 */
    signals: SignalRecord[]
    /** 过滤前的总数 */
    total: number
    direction: string
    /** 前视统计口径（T+4 / T+12 …） */
    forwardBars: number[]
    /** 非静态币的推送量能门槛 */
    volumeThreshold: number
    staticSymbols: string[]
    strategyLabels: Record<string, string>
    scanning?: boolean
    clearing?: boolean
    loading?: boolean
  }>(),
  { scanning: false, clearing: false, loading: false },
)

const emit = defineEmits<{
  (e: 'update:direction', value: string): void
  (e: 'scan'): void
  (e: 'clear'): void
  (e: 'refresh'): void
}>()

// ---- xs 卡片展开状态 ----
const expandedIds = ref<string[]>([])
const isExpanded = (id: string): boolean => expandedIds.value.includes(id)
const toggleExpand = (id: string): void => {
  expandedIds.value = isExpanded(id)
    ? expandedIds.value.filter((item) => item !== id)
    : [...expandedIds.value, id]
}

const onDirectionChange = (value: unknown): void => {
  emit('update:direction', typeof value === 'string' ? value : 'all')
}

const strategyLabel = (strategy: string): string => props.strategyLabels[strategy] ?? strategy

const formatPrice = (value: number): string => {
  const num = Number(value)
  if (!Number.isFinite(num)) return '—'
  if (num >= 1000) return num.toLocaleString('en-US', { maximumFractionDigits: 2 })
  return num.toLocaleString('en-US', { maximumFractionDigits: 6 })
}

const volumeLabel = (signal: SignalRecord): string =>
  signal.volume_ratio == null ? '—' : `${signal.volume_ratio.toFixed(1)}x`

// 量能只做提示，不拦截：达标标绿，未达标保持中性灰
const volumeOk = (signal: SignalRecord): boolean => {
  if (signal.volume_ratio == null) return false
  const threshold = props.volumeThreshold || 2
  return signal.volume_ratio >= threshold || props.staticSymbols.includes(signal.symbol)
}

const volumeClass = (signal: SignalRecord): string =>
  volumeOk(signal) ? 'text-long font-weight-medium' : 'text-medium-emphasis'

const fwdLabel = (signal: SignalRecord): string => {
  if (!signal.fwd) return '—'
  const parts = props.forwardBars
    .map((bar) =>
      signal.fwd && signal.fwd[String(bar)] !== undefined
        ? `T+${bar} ${formatSignedPercent(signal.fwd[String(bar)])}`
        : '',
    )
    .filter((part) => part.length > 0)
  return parts.length > 0 ? parts.join(' / ') : '—'
}

// 前视收益：用首个周期决定颜色，避免一格里同时出现红绿
const fwdClass = (signal: SignalRecord): string => {
  if (!signal.fwd) return 'text-medium-emphasis'
  const first = props.forwardBars.map((bar) => signal.fwd?.[String(bar)]).find((v) => v !== undefined)
  const num = Number(first)
  if (!Number.isFinite(num) || num === 0) return 'text-medium-emphasis'
  return num > 0 ? 'text-up' : 'text-down'
}

const plainMessage = (value: string): string =>
  value
    .replace(/^#+\s*/gm, '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/^>\s*/gm, '')
    .replace(/^---+$/gm, '')
    .replace(/\n{2,}/g, '\n')
    .trim()
</script>

<style scoped>
/* ---- xs 卡片 ---- */
.signal-card {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
  padding: 10px 12px;
  background: rgb(var(--v-theme-surface));
}
.signal-card + .signal-card {
  margin-top: 8px;
}
.signal-card__head {
  display: block;
  width: 100%;
  padding: 0;
  border: none;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.signal-card__symbol {
  font-size: 14px;
  font-weight: 600;
}
.signal-card__meta {
  margin-top: 2px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.72);
}
.signal-card__vol {
  margin-top: 4px;
}
.vol-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(var(--v-theme-on-surface), 0.34);
  flex: 0 0 auto;
}
.vol-dot--on {
  background: rgb(var(--v-theme-long));
}
.signal-card__body {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed rgba(var(--v-border-color), var(--v-border-opacity));
}
.signal-card__message {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), 0.72);
  white-space: pre-line;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ---- sm+ 表格 ---- */
.signal-table-wrap {
  overflow-x: auto;
}
.signal-table :deep(th) {
  white-space: nowrap;
  font-size: 11px;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.6);
}
.signal-table :deep(td) {
  vertical-align: top;
}
.signal-table :deep(tbody tr:hover) {
  background: rgba(var(--v-theme-on-surface), 0.03);
}
/* 首列 sticky：横滚时时间列保持可见 */
.signal-table :deep(th:first-child),
.signal-table :deep(td:first-child) {
  position: sticky;
  left: 0;
  z-index: 1;
  background: rgb(var(--v-theme-surface));
}
.signal-title {
  max-width: 420px;
  word-break: break-word;
}
.signal-message {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  white-space: pre-line;
}
.dir-toggle :deep(.v-btn) {
  text-transform: none;
  letter-spacing: 0;
}
</style>
