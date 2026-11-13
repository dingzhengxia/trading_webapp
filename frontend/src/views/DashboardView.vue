<!-- frontend/src/views/DashboardView.vue（总览：只读聚合巡检页） -->
<!--
  重设计（redesign-spec 2026-11-13 · B1）：
  旧版是 26 行空壳（PnlSummary + 可操作 PositionsPanel），与交易页重复。
  新版按「巡检：账务 + 系统健康度」职责组织：
    KPI 行 → 系统状态条 → 多空持仓摘要（lg 6:6）→ 最新信号 Top3 → 风控最近动作 Top3。
  只读聚合：平仓 / 反手等操作入口只保留在交易页（spec「必须移除 PositionsPanel」）。
  路由：页面本身挂在 /overview（由 WP-A 修改 router，本文件不涉及路由）。
-->
<template>
  <div>
    <!-- 1. KPI 行（xs 两列） -->
    <v-row dense>
      <v-col cols="6" sm="3">
        <MetricCard
          label="总浮动盈亏"
          :value="totalPnlTone.text"
          :tone="totalPnlKpiTone"
          icon="mdi-swap-horizontal-bold"
          hint="全部持仓未实现盈亏"
        />
      </v-col>
      <v-col cols="6" sm="3">
        <MetricCard
          label="持仓数"
          :value="positionStore.positions.length"
          :hint="`${positionStore.longPositions.length} 多 / ${positionStore.shortPositions.length} 空`"
          icon="mdi-format-list-bulleted"
        />
      </v-col>
      <v-col cols="6" sm="3">
        <MetricCard
          label="总名义价值"
          :value="`$${formatAmount(totalNotional)}`"
          hint="多空合计"
          icon="mdi-cash-multiple"
        />
      </v-col>
      <v-col cols="6" sm="3">
        <!-- 今日已实现盈亏：后端暂无对应接口（/api/positions、/api/signals、/api/protection 均不含 realized pnl），先显示「—」占位 -->
        <MetricCard
          label="今日已实现"
          value="—"
          icon="mdi-chart-line-variant"
          hint="暂无数据接口"
        />
      </v-col>
    </v-row>

    <!-- 2. 系统状态条（扫描 / 自动开仓 / 风控 / 连接，异常 error 描边，点击跳对应页） -->
    <SystemStatusStrip
      class="mt-3"
      :scan-enabled="signalStatus.enabled"
      :scan-running="signalStatus.running"
      :last-scan-at="signalStatus.last_scan_at"
      :auto-trade-enabled="signalStatus.auto_trade_enabled"
      :protection-enabled="protectionStatus?.enabled ?? false"
      :protection-running="protectionStatus?.running ?? false"
      :guarded-count="protectionStatus?.positions.length ?? 0"
      :connection-text="uiStore.statusMessage"
      :connection-ok="connectionOk"
    />

    <!-- 3. 多空持仓摘要（lg 6:6 双列，<lg 纵向） -->
    <v-row class="mt-1">
      <v-col cols="12" lg="6">
        <PositionSideSummary side="long" :positions="positionStore.longPositions" />
      </v-col>
      <v-col cols="12" lg="6">
        <PositionSideSummary side="short" :positions="positionStore.shortPositions" />
      </v-col>
    </v-row>

    <!-- 4. 最新信号 Top 3（点击跳信号页） -->
    <v-card variant="flat" class="overview-card mt-2">
      <div class="d-flex align-center flex-wrap ga-2 pa-4 pb-2">
        <v-icon size="16" color="primary">mdi-radar</v-icon>
        <span class="text-subtitle-1 font-weight-medium">最新信号</span>
        <v-spacer></v-spacer>
        <v-btn variant="text" size="small" append-icon="mdi-arrow-right" to="/signals">
          信号页
        </v-btn>
      </div>
      <v-divider></v-divider>
      <v-list v-if="recentSignals.length" density="compact" class="py-0">
        <v-list-item v-for="signal in recentSignals" :key="signal.id" to="/signals">
          <template #prepend>
            <span class="dir-badge" :class="`dir-badge--${directionTone(signal.direction).key}`">
              <v-icon>{{ directionTone(signal.direction).icon }}</v-icon
              >{{ directionTone(signal.direction).label }}
            </span>
          </template>
          <span class="text-body-2 font-weight-medium">{{ signal.symbol }}</span>
          <span class="text-caption text-medium-emphasis ml-2">
            {{ signal.timeframe }} · <span class="num">{{ signal.price }}</span>
          </span>
          <template #append>
            <span class="text-caption text-medium-emphasis">{{ formatIsoTime(signal.created_at) }}</span>
          </template>
        </v-list-item>
      </v-list>
      <div v-else class="pa-4 text-caption text-medium-emphasis">
        还没有信号记录，去信号页手动扫描或等待周期扫描。
      </div>
    </v-card>

    <!-- 5. 风控最近动作 Top 3（复用 /api/protection 的 v2 recent_actions，点击跳风控页） -->
    <v-card variant="flat" class="overview-card mt-2">
      <div class="d-flex align-center flex-wrap ga-2 pa-4 pb-2">
        <v-icon size="16" color="primary">mdi-shield-alert-outline</v-icon>
        <span class="text-subtitle-1 font-weight-medium">风控最近动作</span>
        <v-spacer></v-spacer>
        <v-btn variant="text" size="small" append-icon="mdi-arrow-right" to="/protection">
          去风控
        </v-btn>
      </div>
      <v-divider></v-divider>
      <v-list v-if="recentActions.length" density="compact" class="py-0">
        <v-list-item v-for="(item, idx) in recentActions" :key="`${item.ts}-${idx}`" to="/protection">
          <template #prepend>
            <v-icon
              size="16"
              :color="item.level === 'error' ? 'error' : item.level === 'warning' ? 'warning' : 'success'"
            >
              mdi-shield-alert-outline
            </v-icon>
          </template>
          <span class="text-caption">
            {{ new Date(item.ts * 1000).toLocaleTimeString() }} · {{ item.symbol }} · {{ item.text }}
          </span>
        </v-list-item>
      </v-list>
      <div v-else-if="!protectionStatus" class="pa-4 text-caption text-medium-emphasis">
        风控状态获取失败或加载中，请检查后端服务。
      </div>
      <div v-else class="pa-4 text-caption text-medium-emphasis">
        最近没有触发减仓 / 止盈，引擎只在上移止损时保持安静。
      </div>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import api from '@/services/api'
import { ENDPOINTS } from '@/services/endpoints'
import MetricCard from '@/components/MetricCard.vue'
import SystemStatusStrip from '@/components/overview/SystemStatusStrip.vue'
import PositionSideSummary from '@/components/overview/PositionSideSummary.vue'
import { usePositionStore } from '@/stores/positionStore'
import { useUiStore } from '@/stores/uiStore'
import { directionTone, pnlTone } from '@/utils/tone'
import { formatAmount, formatIsoTime } from '@/utils/format'
import type {
  ProtectionActionRow,
  ProtectionStatus,
  SignalRecord,
  SignalStatus,
  SignalsResponse,
} from '@/models/types'

const POLL_INTERVAL_MS = 15000

const positionStore = usePositionStore()
const uiStore = useUiStore()

// ---- 只读数据源：复用信号页 / 风控页的既有接口，不新增后端调用 ----
const signalStatus = ref<SignalStatus>({
  enabled: false,
  running: false,
  last_scan_at: null,
  next_scan_at: null,
  scanned_symbols: 0,
  emitted_count: 0,
  error_count: 0,
  last_error: null,
  auto_trade_enabled: false,
  last_auto_open: null,
})
const recentSignals = ref<SignalRecord[]>([])
const protectionStatus = ref<ProtectionStatus | null>(null)

const totalPnlTone = computed(() => pnlTone(positionStore.totalPnl))
const totalPnlKpiTone = computed<'up' | 'down' | 'neutral'>(() => {
  if (totalPnlTone.value.sign > 0) return 'up'
  if (totalPnlTone.value.sign < 0) return 'down'
  return 'neutral'
})
const totalNotional = computed(() => positionStore.longNotional + positionStore.shortNotional)

// 连接健康度直接复用 uiStore 的既有状态色推导（已连接 / 准备就绪 / 任务运行中均视为正常）
const connectionOk = computed(() => uiStore.statusColor !== 'error')

const recentActions = computed<ProtectionActionRow[]>(
  () => protectionStatus.value?.v2?.recent_actions?.slice(0, 3) ?? [],
)

const fetchOverview = async (): Promise<void> => {
  try {
    const response = await api.get<SignalsResponse>(ENDPOINTS.signals)
    if (response.data?.status) {
      signalStatus.value = response.data.status
    }
    recentSignals.value = Array.isArray(response.data?.signals)
      ? response.data.signals.slice(0, 3)
      : []
  } catch (error: unknown) {
    console.warn('总览页获取信号状态失败:', error)
  }
  try {
    const response = await api.get<ProtectionStatus>(ENDPOINTS.protection)
    protectionStatus.value = response.data
  } catch (error: unknown) {
    console.warn('总览页获取风控状态失败:', error)
  }
}

let pollTimer: number | undefined

onMounted(() => {
  // 复用 positionStore 既有 action，不新增接口
  void positionStore.fetchPositions()
  void fetchOverview()
  pollTimer = window.setInterval(() => {
    if (document.visibilityState === 'visible') {
      void positionStore.fetchPositions()
      void fetchOverview()
    }
  }, POLL_INTERVAL_MS)
})

onUnmounted(() => {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
})
</script>

<style scoped>
.overview-card {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
}
</style>
