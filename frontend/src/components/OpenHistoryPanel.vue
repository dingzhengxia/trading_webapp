<!-- frontend/src/components/OpenHistoryPanel.vue (完整代码) -->
<!-- 开仓记录：展示每次开仓任务落库的「选币快照 + 每笔结果」（自动/信号/手动/再平衡共用台账）。 -->
<template>
  <v-card variant="outlined">
    <v-card-title class="text-subtitle-1 d-flex align-center">
      开仓记录
      <v-spacer></v-spacer>
      <v-chip v-if="records.length" size="small" variant="tonal" color="info" class="mr-2">
        最近 {{ records.length }} 批
      </v-chip>
      <v-btn size="small" variant="tonal" color="info" :loading="loading" @click="fetchHistory">
        <v-icon start>mdi-refresh</v-icon>
        刷新
      </v-btn>
    </v-card-title>

    <v-card-text>
      <EmptyState
        v-if="!records.length && !loading"
        icon="mdi-clipboard-text-clock-outline"
        title="暂无开仓记录"
        description="每次「开始开仓 / 手动交易 / 再平衡 / 信号自动开仓」启动时会落一条记录，这里保留当时的选币快照与每笔结果。"
      />

      <v-expansion-panels v-else v-model="openedPanel">
        <v-expansion-panel v-for="rec in records" :key="rec.id">
          <v-expansion-panel-title>
            <div class="d-flex flex-wrap align-center ga-3" style="min-width: 0; width: 100%">
              <span class="text-no-wrap text-caption">{{ formatTime(rec.ts) }}</span>
              <v-chip size="x-small" :color="sourceColor(rec.source)" class="text-no-wrap">
                {{ sourceLabel(rec.source) }}
              </v-chip>
              <v-chip
                size="x-small"
                :color="summaryColor(rec)"
                variant="tonal"
                class="text-no-wrap"
              >
                {{ summaryText(rec) }}
              </v-chip>
              <span class="text-caption text-medium-emphasis text-truncate">
                {{ snapshotText(rec) }}
              </span>
            </div>
          </v-expansion-panel-title>

          <v-expansion-panel-text>
            <!-- 选币概要（明细看下方表格，摘要不再铺全部币名） -->
            <div v-if="snapshotDetail(rec)" class="text-caption mb-2 text-medium-emphasis">
              <v-icon size="14" class="mr-1">mdi-clipboard-list-outline</v-icon>
              {{ snapshotDetail(rec) }}
            </div>

            <!-- 每笔结果（5 列 ≤ 降级判据，xs 保留横滚 + 首列 sticky） -->
            <div class="open-history-scroll">
              <v-table density="compact" class="open-history-table">
                <thead>
                  <tr>
                    <th class="text-left">币种</th>
                    <th class="text-left">方向</th>
                    <th class="text-right">目标价值 (USD)</th>
                    <th class="text-left">结果</th>
                    <th class="text-left">说明</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(item, idx) in rec.items" :key="idx">
                    <td>{{ item.coin || '—' }}</td>
                    <td>
                      <span :class="sideToneClass(item.side)">{{ sideLabel(item) }}</span>
                    </td>
                    <td class="text-right">
                      {{ item.target_value != null ? formatValue(item.target_value) : '—' }}
                    </td>
                    <td>
                      <v-chip
                        size="x-small"
                        variant="tonal"
                        :color="resultColor(item)"
                      >
                        {{ resultLabel(item) }}
                      </v-chip>
                    </td>
                    <td class="text-caption text-medium-emphasis">
                      {{ itemNote(item) }}
                    </td>
                  </tr>
                </tbody>
              </v-table>
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import apiClient from '@/services/api'
import { ENDPOINTS } from '@/services/endpoints'
import { formatMillis, formatUsdLoose } from '@/utils/format'
import { useUiStore } from '@/stores/uiStore'
import { getErrorMessage } from '@/utils/errors'
import { positionSideTone } from '@/utils/tone'
import EmptyState from '@/components/EmptyState.vue'

interface OpenHistoryItem {
  coin?: string
  side?: string
  target_value?: number | null
  success?: boolean | null
  error?: string | null
  skip_reason?: string | null
  strategy?: string | null
  close_ratio?: number | null
}

interface OpenHistoryRecord {
  id: string
  ts: number
  source: string
  trigger?: string
  snapshot?: Record<string, unknown>
  allocations?: Record<string, unknown>
  items: OpenHistoryItem[]
  summary?: { total?: number; success?: number; failed?: number; pending?: number }
}

const uiStore = useUiStore()
const records = ref<OpenHistoryRecord[]>([])
const loading = ref(false)
const openedPanel = ref<number | null>(0)

const fetchHistory = async () => {
  loading.value = true
  try {
    const response = await apiClient.get(ENDPOINTS.tradingOpenHistory, { params: { limit: 50 } })
    records.value = Array.isArray(response.data?.records) ? response.data.records : []
  } catch (error: unknown) {
    uiStore.logStore.addLog({
      message: `[后端] ❌ 读取开仓记录失败: ${getErrorMessage(error)}`,
      level: 'error',
      timestamp: new Date().toLocaleTimeString(),
    })
  } finally {
    loading.value = false
  }
}

// 任务跑完自动刷新一次，避免手动点刷新
watch(
  () => uiStore.isRunning,
  (running, prev) => {
    if (prev && !running) {
      fetchHistory()
      return
    }
    if (running && !pollTimer) {
      // 长任务运行期间每 10 秒刷新，让「进行中」记录的进度可见
      pollTimer = window.setInterval(fetchHistory, 10000)
    }
  },
)

let pollTimer: number | null = null
onMounted(() => {
  fetchHistory()
  if (uiStore.isRunning && !pollTimer) {
    pollTimer = window.setInterval(fetchHistory, 10000)
  }
})
onUnmounted(() => {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
})

const formatTime = (ts: number) => formatMillis(ts)

const formatValue = (value: number) => formatUsdLoose(value)

const SOURCE_META: Record<string, { label: string; color: string }> = {
  plan: { label: '自动开仓', color: 'primary' },
  signal: { label: '信号开仓', color: 'teal' },
  manual: { label: '手动交易', color: 'warning' },
  rebalance: { label: '再平衡', color: 'purple' },
}

const sourceLabel = (source?: string) => SOURCE_META[source ?? '']?.label ?? source ?? '—'
const sourceColor = (source?: string) => SOURCE_META[source ?? '']?.color ?? 'grey'

const sideLabel = (item: OpenHistoryItem) => {
  const side = String(item.side || '').toLowerCase()
  if (side === 'close') return item.close_ratio != null ? `平仓 ${Math.round(item.close_ratio * 100)}%` : '平仓'
  if (side === 'buy') return '做多'
  if (side === 'sell') return '做空'
  return item.side || '—'
}

// 统一走 directionTone：buy/sell 归一化为做多/做空，平仓用中性灰
const sideToneClass = (side?: string) => {
  const tone = positionSideTone(side)
  return tone.isClose ? 'text-medium-emphasis' : tone.textClass
}

const resultLabel = (item: OpenHistoryItem) => {
  if (item.skip_reason) return '跳过'
  if (item.success == null) return '进行中'
  return item.success ? '成功' : '失败'
}

const resultColor = (item: OpenHistoryItem) => {
  if (item.skip_reason) return 'grey'
  if (item.success == null) return 'info'
  return item.success ? 'success' : 'error'
}

// 汇总 chip：进行中条数单独展示
const summaryText = (rec: OpenHistoryRecord) => {
  const s = rec.summary ?? {}
  const base = `${s.success ?? 0} 成功 / ${s.failed ?? 0} 失败`
  return (s.pending ?? 0) > 0 ? `${base} / ${s.pending} 进行中` : base
}
const summaryColor = (rec: OpenHistoryRecord) => {
  const s = rec.summary ?? {}
  if ((s.pending ?? 0) > 0) return 'info'
  return (s.failed ?? 0) > 0 ? 'error' : 'success'
}

const itemNote = (item: OpenHistoryItem) => {
  const parts: string[] = []
  if (item.strategy) parts.push(`策略 ${item.strategy}`)
  if (item.error) parts.push(item.error)
  if (item.skip_reason) parts.push(item.skip_reason)
  return parts.join(' · ') || '—'
}

const sideParts = (rec: OpenHistoryRecord) => {
  const snap = rec.snapshot ?? {}
  const longCoins = Array.isArray(snap.long_coin_list) ? (snap.long_coin_list as string[]) : []
  const shortCoins = Array.isArray(snap.short_coin_list) ? (snap.short_coin_list as string[]) : []
  return { snap, longCoins, shortCoins }
}

// 标题行摘要：只给「做多 N 币 · 总额」这类紧凑信息，54 个币名不再刷成一面墙
const snapshotText = (rec: OpenHistoryRecord) => {
  const { snap, longCoins, shortCoins } = sideParts(rec)
  const parts: string[] = []
  if (snap.enable_long_trades) {
    parts.push(`做多 ${longCoins.length} 币${snap.total_long_position_value ? ` · 总 ${snap.total_long_position_value} USD` : ''}`)
  }
  if (snap.enable_short_trades) {
    parts.push(`做空 ${shortCoins.length} 币${snap.total_short_position_value ? ` · 总 ${snap.total_short_position_value} USD` : ''}`)
  }
  if (rec.trigger && rec.source !== 'plan') parts.push(rec.trigger)
  return parts.join(' · ')
}

// 展开区：币名最多列 12 个，其余「等 N 个」；完整明细看下方表格（含每笔目标金额）
const snapshotDetail = (rec: OpenHistoryRecord) => {
  const { longCoins, shortCoins } = sideParts(rec)
  const fmt = (coins: string[]) => {
    if (!coins.length) return ''
    const shown = coins.slice(0, 12).join(' / ')
    return coins.length > 12 ? `${shown} 等 ${coins.length} 个` : shown
  }
  const parts: string[] = []
  const longText = fmt(longCoins)
  const shortText = fmt(shortCoins)
  if (longText) parts.push(`做多：${longText}`)
  if (shortText) parts.push(`做空：${shortText}`)
  return parts.join('　|　')
}
</script>

<style scoped>
.open-history-table {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
}
/* 列数判定：每笔结果表 5 列（币种/方向/目标价值/结果/说明）≤ 5，
   按规格走「横滚 + 首列 sticky」，不做卡片化 */
.open-history-scroll {
  overflow-x: auto;
}
.open-history-table :is(th, td):first-child {
  position: sticky;
  left: 0;
  background: rgb(var(--v-theme-surface));
  z-index: 1;
}
</style>
