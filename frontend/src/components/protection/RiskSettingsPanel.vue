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

    <!-- v2 动作轨迹：什么时候、因为哪条线、减了多少 -->
    <PageCard v-if="isV2" icon="mdi-history" title="最近保护动作" spaced>
      <template #badges>
        <v-chip size="small" variant="tonal">
          第 {{ status.v2?.cycle_count ?? 0 }} 轮
        </v-chip>
        <HelpTip :text="HELP.protection.actionLog" />
      </template>
      <div v-if="(status.v2?.recent_actions?.length ?? 0) === 0" class="text-caption text-medium-emphasis">
        最近没有触发减仓/止盈，引擎只在上移止损时保持安静。
      </div>
      <v-list v-else density="compact" lines="one">
        <v-list-item
          v-for="(item, idx) in status.v2?.recent_actions ?? []"
          :key="`${item.ts}-${idx}`"
        >
          <template #prepend>
            <v-icon
              size="16"
              :color="item.level === 'error' ? 'error' : item.level === 'warning' ? 'warning' : 'success'"
            >
              mdi-shield-alert-outline
            </v-icon>
          </template>
          <v-list-item-title class="text-caption">
            {{ formatClock(item.ts) }} · {{ item.symbol }} · {{ item.text }}
          </v-list-item-title>        </v-list-item>
      </v-list>
    </PageCard>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDisplay } from 'vuetify'
import { useProtectionConfig } from '@/composables/useProtectionConfig'
import { formatNumberOrDash as formatNumber } from '@/utils/format'
import { directionTone } from '@/utils/tone'
import PageCard from '@/components/PageCard.vue'
import EmptyState from '@/components/EmptyState.vue'
import HelpTip from '@/components/HelpTip.vue'
import { HELP } from '@/config/help'
import type { ProtectionPositionRow } from '@/models/types'

const { status, isV2, fetchStatus } = useProtectionConfig()

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

const formatClock = (ts: number): string => new Date(ts * 1000).toLocaleTimeString()
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
</style>
