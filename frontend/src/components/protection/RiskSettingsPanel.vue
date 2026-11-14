<!-- frontend/src/components/protection/RiskSettingsPanel.vue -->
<!-- 守卫中的仓位（xs 卡片化 / sm+ 表格）与最近保护动作（T11 自 ProtectionView 拆出） -->
<template>
  <div>
    <!-- 守卫中的仓位 -->
    <PageCard icon="mdi-shield-account" title="守卫中的仓位" spaced>
      <template #badges>
        <v-chip size="small" variant="tonal">{{ status.positions.length }} 个</v-chip>
        <HelpTip :text="HELP.protection.guardCard" />
        <v-btn size="small" variant="text" prepend-icon="mdi-refresh" @click="fetchStatus">
          刷新
        </v-btn>
        <HelpTip :text="HELP.protection.refreshBtn" />
      </template>
      <v-alert
        v-if="!status.enabled"
        type="warning"
        variant="tonal"
        density="compact"
        class="text-caption"
      >
        仓位保护当前未启用：打开上方开关后，引擎才会开始轮询持仓并挂保护单。
      </v-alert>

      <!-- xs：卡片化。TP1/TP2/躺平 合并成 chip 组（chip 显示触发态），点开看具体价格 -->
      <div v-else-if="isXs && status.positions.length > 0" class="d-flex flex-column ga-2">
        <div
          v-for="row in status.positions"
          :key="`${row.symbol}-${row.side}`"
          class="guard-card"
          @click="toggleGuardRow(row)"
        >
          <div class="d-flex align-center ga-2">
            <span class="guard-card__symbol">{{ row.symbol }}</span>
            <span class="dir-badge" :class="`dir-badge--${directionTone(row.side).key}`">
              <v-icon>{{ directionTone(row.side).icon }}</v-icon
              >{{ directionTone(row.side).label }}
            </span>
            <v-spacer></v-spacer>
            <v-icon size="18" class="text-medium-emphasis">
              {{ isGuardRowExpanded(row) ? 'mdi-chevron-up' : 'mdi-chevron-down' }}
            </v-icon>
          </div>
          <div class="guard-card__grid text-caption">
            <span>数量 <span class="num">{{ formatNumber(row.contracts, 4) }}</span></span>
            <span>标记价 <span class="num">{{ formatNumber(row.mark_price) }}</span></span>
            <span>保护止损 <span class="num">{{ stopText(row) }}</span></span>
          </div>
          <div class="d-flex flex-wrap align-center ga-1 mt-1" @click.stop="toggleGuardRow(row)">
            <v-chip size="x-small" :variant="row.tp1_done ? 'tonal' : 'outlined'" color="info">TP1</v-chip>
            <v-chip size="x-small" :variant="row.tp2_done ? 'tonal' : 'outlined'" color="info">TP2</v-chip>
            <v-chip size="x-small" :variant="row.tp3_done ? 'tonal' : 'outlined'" color="info">躺平</v-chip>
            <v-chip v-if="row.t1_done" size="x-small" variant="tonal" color="warning">T1</v-chip>
            <v-chip v-if="row.t2_done" size="x-small" variant="tonal" color="warning">T2</v-chip>
            <v-chip v-if="row.t3_done" size="x-small" variant="tonal" color="warning">T3</v-chip>
            <v-chip v-if="row.t4_done" size="x-small" variant="tonal" color="error">T4</v-chip>
            <span v-if="!hasTriggered(row)" class="text-caption text-medium-emphasis">等待触发</span>
          </div>
          <div v-if="isGuardRowExpanded(row)" class="text-caption text-medium-emphasis mt-2">
            <div>
              开仓价 <span class="num">{{ formatNumber(row.entry_price) }}</span>
              · TP1 <span class="num">{{ formatNumber(row.tp1_price) }}</span>
              / TP2 <span class="num">{{ formatNumber(row.tp2_price) }}</span>
              / 躺平 <span class="num">{{ formatNumber(row.tp3_price) }}</span>
            </div>
            <div v-if="isV2" class="mt-1">
              四档减仓线 <span class="num">{{ tierText(row) }}</span>
              · 灾难线
              <span class="num">
                <template v-if="row.disaster_stop">{{ formatNumber(row.disaster_stop) }}</template>
                <template v-else>—</template>
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- sm+：表格。md（及 sm）隐藏「开仓价」列避免横滚，lg+ 全列 -->
      <v-table v-else-if="status.positions.length > 0" density="compact">
        <thead>
          <tr>
            <th class="text-left">币种</th>
            <th class="text-left">方向</th>
            <th class="text-right">数量</th>
            <th v-if="lgAndUp" class="text-right">开仓价</th>
            <th class="text-right">标记价</th>
            <th class="text-right">保护止损</th>
            <th class="text-right">TP1 / TP2 / 躺平</th>
            <th v-if="isV2" class="text-right">四档减仓线</th>
            <th v-if="isV2" class="text-right">灾难线</th>
            <th class="text-left">已触发</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in status.positions" :key="`${row.symbol}-${row.side}`">
            <td class="font-weight-medium">{{ row.symbol }}</td>
            <td>
              <span class="dir-badge" :class="`dir-badge--${directionTone(row.side).key}`">
                <v-icon>{{ directionTone(row.side).icon }}</v-icon
                >{{ directionTone(row.side).label }}
              </span>
            </td>
            <td class="text-right">{{ formatNumber(row.contracts, 4) }}</td>
            <td v-if="lgAndUp" class="text-right">{{ formatNumber(row.entry_price) }}</td>
            <td class="text-right">{{ formatNumber(row.mark_price) }}</td>
            <td class="text-right">
              <span v-if="row.protected_stop">{{ formatNumber(row.protected_stop) }}</span>
              <span v-else-if="row.stop_price">{{ formatNumber(row.stop_price) }}</span>
              <span v-else class="text-medium-emphasis">—</span>
            </td>
            <td class="text-right text-caption">
              {{ formatNumber(row.tp1_price) }} / {{ formatNumber(row.tp2_price) }} /
              {{ formatNumber(row.tp3_price) }}
            </td>
            <td v-if="isV2" class="text-right text-caption">
              <span v-if="row.tier_levels?.length">
                {{ row.tier_levels.map((v) => formatNumber(v)).join(' / ') }}
              </span>
              <span v-else class="text-medium-emphasis">—</span>
            </td>
            <td v-if="isV2" class="text-right text-caption">
              <span v-if="row.disaster_stop">{{ formatNumber(row.disaster_stop) }}</span>
              <span v-else class="text-medium-emphasis">—</span>
            </td>
            <td>
              <div class="d-flex flex-wrap ga-1">
                <v-chip v-if="row.tp1_done" size="x-small" variant="tonal" color="info">TP1</v-chip>
                <v-chip v-if="row.tp2_done" size="x-small" variant="tonal" color="info">TP2</v-chip>
                <v-chip v-if="row.tp3_done" size="x-small" variant="tonal" color="info">躺平</v-chip>
                <v-chip v-if="row.t1_done" size="x-small" variant="tonal" color="warning">T1</v-chip>
                <v-chip v-if="row.t2_done" size="x-small" variant="tonal" color="warning">T2</v-chip>
                <v-chip v-if="row.t3_done" size="x-small" variant="tonal" color="warning">T3</v-chip>
                <v-chip v-if="row.t4_done" size="x-small" variant="tonal" color="error">T4</v-chip>
                <span
                  v-if="!hasTriggered(row)"
                  class="text-caption text-medium-emphasis"
                >等待触发</span>
              </div>
            </td>
          </tr>
        </tbody>
      </v-table>
      <EmptyState
        v-else
        icon="mdi-shield-outline"
        title="当前没有持仓"
        description="引擎处于待机巡检状态；有持仓后这里会显示每个仓位已挂的保护线与减仓进度。"
      />
    </PageCard>

    <!-- v2 保护事件：什么时候、因为哪条线、减了多少、最后为什么没了 -->
    <PageCard v-if="isV2" icon="mdi-history" title="最近保护事件" spaced>
      <template #badges>
        <v-chip size="small" variant="tonal">
          第 {{ status.v2?.cycle_count ?? 0 }} 轮
        </v-chip>
        <HelpTip :text="HELP.protection.actionLog" />
      </template>
      <div v-if="events.length === 0" class="text-caption text-medium-emphasis">
        还没有保护事件。开仓后这里会依次出现「建立风险周期 → 止损上移到哪 → 减仓 → 为什么平仓」；
        这份记录存在数据库里，引擎重启也不会丢。
      </div>
      <div v-else class="event-log">
        <div v-for="(item, idx) in events" :key="`${item.ts}-${idx}`" class="event-log__row">
          <span class="event-log__time">{{ formatEventTime(item.ts) }}</span>
          <v-chip
            size="x-small"
            variant="tonal"
            :color="kindMeta(item).color"
            class="event-log__kind"
          >
            {{ kindMeta(item).label }}
          </v-chip>
          <span class="event-log__symbol text-caption">{{ shortSymbol(item.symbol) }}</span>
          <span
            class="event-log__msg text-caption"
            :class="{ 'event-log__msg--alert': item.triggered_stop }"
          >
            {{ item.message }}
          </span>
        </div>
      </div>
    </PageCard>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDisplay } from 'vuetify'
import { useProtectionConfig } from '@/composables/useProtectionConfig'
import { formatEventTime, formatNumberOrDash as formatNumber } from '@/utils/format'
import { directionTone } from '@/utils/tone'
import PageCard from '@/components/PageCard.vue'
import EmptyState from '@/components/EmptyState.vue'
import HelpTip from '@/components/HelpTip.vue'
import { HELP } from '@/config/help'
import type { ProtectionEventRow, ProtectionPositionRow } from '@/models/types'

const { status, events, isV2, fetchStatus } = useProtectionConfig()

/** 事件类型 → 徽章（kind 由后端 ledger.log_event 写入） */
const EVENT_KINDS: Record<string, { label: string; color: string }> = {
  cycle_new: { label: '新周期', color: 'info' },
  reduce: { label: '减仓', color: 'warning' },
  stop: { label: '止损', color: 'info' },
  exit: { label: '全平', color: 'error' },
  flat: { label: '已平仓', color: 'success' },
  replan: { label: '重估', color: 'info' },
  replan_dry: { label: '重估·演练', color: 'info' },
  error: { label: '异常', color: 'error' },
}

const kindMeta = (item: ProtectionEventRow): { label: string; color: string } => {
  // 「仓位消失」里判定为兜底止损触发的，用 error 提级：这是最需要用户知道的一条
  if (item.kind === 'flat' && item.triggered_stop) return { label: '止损触发', color: 'error' }
  return EVENT_KINDS[item.kind] ?? { label: item.kind || '事件', color: 'default' }
}

/** ETH/USDC:USDC → ETH/USDC，省掉重复的结算币后缀，手机上不占位 */
const shortSymbol = (symbol: string): string =>
  symbol.includes(':') ? symbol.split(':')[0] : symbol

// ---- 断点：xs 卡片化 / sm+ 表格 / lg 才显示「开仓价」列 ----
const display = useDisplay()
const isXs = computed(() => display.xs.value)
const lgAndUp = computed(() => display.lgAndUp.value)

// ---- xs 守卫卡片展开态 ----
const expandedGuardRows = ref<Set<string>>(new Set())
const guardRowKey = (row: ProtectionPositionRow): string => `${row.symbol}-${row.side}`
const isGuardRowExpanded = (row: ProtectionPositionRow): boolean =>
  expandedGuardRows.value.has(guardRowKey(row))
const toggleGuardRow = (row: ProtectionPositionRow): void => {
  const key = guardRowKey(row)
  const next = new Set(expandedGuardRows.value)
  if (next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
  }
  expandedGuardRows.value = next
}

const stopText = (row: ProtectionPositionRow): string => {
  if (row.protected_stop) return formatNumber(row.protected_stop)
  if (row.stop_price) return formatNumber(row.stop_price)
  return '—'
}
const tierText = (row: ProtectionPositionRow): string =>
  row.tier_levels?.length ? row.tier_levels.map((v) => formatNumber(v)).join(' / ') : '—'

const hasTriggered = (row: ProtectionPositionRow): boolean =>
  row.tp1_done || row.tp2_done || row.tp3_done ||
  row.t1_done || row.t2_done || row.t3_done || Boolean(row.t4_done)
</script>

<style scoped>
/* xs 守卫卡片：只写结构，配色全部走主题令牌 */
.guard-card {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
  padding: 10px 12px;
  cursor: pointer;
  min-width: 0;
}
.guard-card__symbol {
  font-size: 14px;
  font-weight: 600;
}
.guard-card__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px;
  margin-top: 6px;
  color: rgba(var(--v-theme-on-surface), 0.72);
}

/* 保护事件流：时间 / 类型徽章 / 币种 / 说明，窄屏自动换行 */
.event-log {
  max-height: 340px;
  overflow-y: auto;
  overscroll-behavior: contain;
}
.event-log__row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
  padding: 6px 0;
  border-bottom: 1px solid rgba(var(--v-border-color), 0.5);
}
.event-log__row:last-child {
  border-bottom: none;
}
.event-log__time {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  opacity: 0.65;
  flex: 0 0 auto;
}
.event-log__kind {
  flex: 0 0 auto;
}
.event-log__symbol {
  font-weight: 600;
  flex: 0 0 auto;
}
.event-log__msg {
  flex: 1 1 220px;
  min-width: 0;
  overflow-wrap: anywhere;
}
/* 兜底止损触发：这是「仓位怎么没的」的答案，必须一眼看到 */
.event-log__msg--alert {
  color: rgb(var(--v-theme-error));
  font-weight: 500;
}
</style>
