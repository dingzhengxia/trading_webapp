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
      <v-alert
        v-if="!records.length && !loading"
        type="info"
        variant="tonal"
        density="compact"
      >
        暂无开仓记录。每次「开始开仓 / 手动交易 / 再平衡 / 信号自动开仓」执行后，
        这里会记录当时的选币快照与每笔开仓结果。
      </v-alert>

      <v-expansion-panels v-else v-model="openedPanel">
        <v-expansion-panel v-for="rec in records" :key="rec.id">
          <v-expansion-panel-title>
            <div class="d-flex align-center ga-3" style="min-width: 0; width: 100%">
              <span class="text-no-wrap text-caption">{{ formatTime(rec.ts) }}</span>
              <v-chip size="x-small" :color="sourceColor(rec.source)" class="text-no-wrap">
                {{ sourceLabel(rec.source) }}
              </v-chip>
              <v-chip
                size="x-small"
                :color="rec.summary?.failed ? 'error' : 'success'"
                variant="tonal"
                class="text-no-wrap"
              >
                {{ rec.summary?.success ?? 0 }} 成功 / {{ rec.summary?.failed ?? 0 }} 失败
              </v-chip>
              <span class="text-caption text-medium-emphasis text-truncate">
                {{ snapshotText(rec) }}
              </span>
            </div>
          </v-expansion-panel-title>

          <v-expansion-panel-text>
            <!-- 选币快照 -->
            <div v-if="snapshotText(rec)" class="text-caption mb-2 text-medium-emphasis">
              <v-icon size="14" class="mr-1">mdi-clipboard-list-outline</v-icon>
              {{ snapshotText(rec) }}
            </div>

            <!-- 每笔结果 -->
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
                    <span :style="{ color: sideColor(item.side) }">{{ sideLabel(item) }}</span>
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
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import apiClient from '@/services/api'
import { useUiStore } from '@/stores/uiStore'
import { getErrorMessage } from '@/utils/errors'

interface OpenHistoryItem {
  coin?: string
  side?: string
  target_value?: number | null
  success?: boolean
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
  summary?: { total?: number; success?: number; failed?: number }
}

const uiStore = useUiStore()
const records = ref<OpenHistoryRecord[]>([])
const loading = ref(false)
const openedPanel = ref<number | null>(0)

const fetchHistory = async () => {
  loading.value = true
  try {
    const response = await apiClient.get('/api/trading/open-history', { params: { limit: 50 } })
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
    if (prev && !running) fetchHistory()
  },
)

onMounted(fetchHistory)

const formatTime = (ts: number) => {
  if (!ts) return '—'
  const d = new Date(ts)
  return d.toLocaleString('zh-CN', { hour12: false })
}

const formatValue = (value: number) => {
  const num = Number(value)
  if (!Number.isFinite(num)) return '—'
  return `¥${num.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`
}

const SOURCE_META: Record<string, { label: string; color: string }> = {
  plan: { label: '自动开仓', color: 'primary' },
  signal: { label: '信号开仓', color: 'teal' },
  manual: { label: '手动交易', color: 'warning' },
  rebalance: { label: '再平衡', color: 'purple' },
}

const sourceLabel = (source: string) => SOURCE_META[source]?.label ?? source ?? '—'
const sourceColor = (source: string) => SOURCE_META[source]?.color ?? 'grey'

const sideLabel = (item: OpenHistoryItem) => {
  const side = String(item.side || '').toLowerCase()
  if (side === 'close') return item.close_ratio != null ? `平仓 ${Math.round(item.close_ratio * 100)}%` : '平仓'
  if (side === 'buy') return '做多'
  if (side === 'sell') return '做空'
  return item.side || '—'
}

const sideColor = (side: string) => {
  // 配色约定：绿涨红跌；平仓用中性灰
  const s = String(side || '').toLowerCase()
  if (s === 'buy') return '#1D9E75'
  if (s === 'sell') return '#E24B4A'
  return '#888780'
}

const resultLabel = (item: OpenHistoryItem) => {
  if (item.skip_reason) return '跳过'
  return item.success ? '成功' : '失败'
}

const resultColor = (item: OpenHistoryItem) => {
  if (item.skip_reason) return 'grey'
  return item.success ? 'success' : 'error'
}

const itemNote = (item: OpenHistoryItem) => {
  const parts: string[] = []
  if (item.strategy) parts.push(`策略 ${item.strategy}`)
  if (item.error) parts.push(item.error)
  if (item.skip_reason) parts.push(item.skip_reason)
  return parts.join(' · ') || '—'
}

const snapshotText = (rec: OpenHistoryRecord) => {
  const snap = rec.snapshot
  if (!snap || typeof snap !== 'object') return ''
  const parts: string[] = []
  const longCoins = Array.isArray(snap.long_coin_list) ? (snap.long_coin_list as string[]) : []
  const shortCoins = Array.isArray(snap.short_coin_list) ? (snap.short_coin_list as string[]) : []
  if (snap.enable_long_trades && longCoins.length) {
    parts.push(`做多 ${longCoins.join('/')}${snap.total_long_position_value ? `（总 ${snap.total_long_position_value} USD）` : ''}`)
  }
  if (snap.enable_short_trades && shortCoins.length) {
    parts.push(`做空 ${shortCoins.join('/')}${snap.total_short_position_value ? `（总 ${snap.total_short_position_value} USD）` : ''}`)
  }
  if (rec.trigger && rec.source !== 'plan') parts.push(rec.trigger)
  return parts.join(' · ')
}
</script>

<style scoped>
.open-history-table {
  border: 0.5px solid rgba(0, 0, 0, 0.12);
  border-radius: 8px;
}
</style>
