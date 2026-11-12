<!-- frontend/src/components/overview/PositionSideSummary.vue -->
<!-- 总览页多空持仓摘要（spec 2026-11-13 B1）：
     每侧「N 个持仓 · 总价值 · 盈亏合计」+ 最新 3 条紧凑行（合约 / 盈亏%）+「查看全部」跳交易页。
     只读组件：不包含任何平仓/反手操作（操作入口唯一在交易页）。 -->
<template>
  <v-card variant="flat" class="side-card">
    <div class="d-flex align-center flex-wrap ga-2 pa-4 pb-3">
      <span class="dir-badge" :class="`dir-badge--${tone.key}`">
        <v-icon>{{ tone.icon }}</v-icon>{{ tone.label }}
      </span>
      <span class="text-subtitle-1 font-weight-medium">{{ positions.length }} 个持仓</span>
      <v-spacer></v-spacer>
      <span class="text-caption text-medium-emphasis">
        总价值 <span class="num">${{ formatAmount(totalNotional) }}</span>
        · 盈亏 <span class="num" :class="totalPnl.textClass">{{ totalPnl.text }}</span>
      </span>
    </div>

    <v-divider v-if="positions.length > 0"></v-divider>

    <div v-if="positions.length > 0" class="px-4 py-2">
      <div v-for="position in recent" :key="position.full_symbol" class="side-row">
        <span class="side-row__symbol">{{ position.full_symbol }}</span>
        <span class="num text-caption" :class="pnlClass(position.pnl_percentage)">
          {{ formatSignedPercent(position.pnl_percentage) }}
        </span>
      </div>
    </div>
    <div v-else class="pa-4 text-caption text-medium-emphasis">
      该方向暂无持仓。
    </div>

    <v-divider></v-divider>
    <v-card-actions class="justify-end py-1">
      <v-btn variant="text" size="small" append-icon="mdi-arrow-right" to="/trading">
        查看全部
      </v-btn>
    </v-card-actions>
  </v-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Position } from '@/models/types'
import { directionTone, pnlClass, pnlTone } from '@/utils/tone'
import { formatAmount, formatSignedPercent } from '@/utils/format'

const props = defineProps<{
  side: 'long' | 'short'
  positions: Position[]
}>()

const tone = computed(() => directionTone(props.side))
const recent = computed(() => props.positions.slice(0, 3))
const totalNotional = computed(() => props.positions.reduce((sum, p) => sum + p.notional, 0))
const totalPnl = computed(() => pnlTone(props.positions.reduce((sum, p) => sum + p.pnl, 0)))
</script>

<style scoped>
.side-card {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
  height: 100%;
}
.side-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 5px 0;
  min-width: 0;
}
.side-row__symbol {
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
