<!-- frontend/src/components/signals/PaperTrackingPanel.vue -->
<!-- 纸面跟踪明细（查看类，规格 A10 拆分）：实盘已登记 / 纸面持仓 / 已平仓统计 / 前视收益。
     放在信号页的折叠区，只读；参数部分见 ExitParamsPanel（在抽屉里） -->
<template>
  <div>
    <template v-if="liveExit.positions.length > 0">
      <SectionHeader icon="mdi-shield-half-full" title="实盘已登记" :description="`${liveExit.positions.length} 个`" />
      <v-table density="compact">
        <thead>
          <tr>
            <th class="text-left">币种</th>
            <th class="text-left">方向</th>
            <th class="text-left">周期</th>
            <th class="text-right">已持有</th>
            <th class="text-right">上限</th>
            <th class="text-left">策略</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in liveExit.positions" :key="row.full_symbol || row.symbol">
            <td class="font-weight-medium">{{ row.symbol }}</td>
            <td>
              <span class="dir-badge" :class="`dir-badge--${directionTone(row.side).key}`">
                <v-icon>{{ directionTone(row.side).icon }}</v-icon>{{ directionTone(row.side).label }}
              </span>
            </td>
            <td class="text-medium-emphasis">{{ row.timeframe || '—' }}</td>
            <td class="text-right num">{{ row.bars_held ?? '—' }} 根</td>
            <td class="text-right num text-medium-emphasis">{{ row.max_bars }} 根</td>
            <td class="text-medium-emphasis">{{ row.strategy || '—' }}</td>
          </tr>
        </tbody>
      </v-table>
    </template>

    <v-row dense class="mt-2">
      <v-col cols="12" md="7">
        <SectionHeader icon="mdi-flask-outline" title="纸面持仓" :description="`${tracking.open_positions.length} 个`" />
        <v-table v-if="tracking.open_positions.length > 0" density="compact">
          <thead>
            <tr>
              <th class="text-left">币种</th>
              <th class="text-left">方向</th>
              <th class="text-left">周期</th>
              <th class="text-right">入场</th>
              <th class="text-right">止损</th>
              <th class="text-right">止盈</th>
              <th class="text-left">开仓时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="position in tracking.open_positions" :key="position.id">
              <td class="font-weight-medium">{{ position.symbol }}</td>
              <td>
                <span class="dir-badge" :class="`dir-badge--${directionTone(position.direction).key}`">
                  <v-icon>{{ directionTone(position.direction).icon }}</v-icon
                  >{{ directionTone(position.direction).label }}
                </span>
              </td>
              <td class="text-medium-emphasis">{{ position.timeframe }}</td>
              <td class="text-right num">{{ formatPrice(position.entry_price) }}</td>
              <td class="text-right num text-short">{{ formatPrice(position.stop_loss) }}</td>
              <td class="text-right num text-long">{{ formatPrice(position.take_profit) }}</td>
              <td class="text-caption text-medium-emphasis">{{ formatTime(position.opened_at) }}</td>
            </tr>
          </tbody>
        </v-table>
        <EmptyState
          v-else
          icon="mdi-flask-empty-outline"
          title="暂无纸面持仓"
          description="启用纸面跟踪后，通过过滤链的信号会在这里模拟建仓（只记录，不下单）。"
        />
      </v-col>

      <v-col cols="12" md="5">
        <SectionHeader icon="mdi-chart-box-outline" title="已平仓统计" />
        <template v-if="tracking.paper_stats.total > 0">
          <v-row dense class="mb-2">
            <v-col cols="6">
              <MetricCard label="样本数" :value="tracking.paper_stats.total" />
            </v-col>
            <v-col cols="6">
              <MetricCard
                label="胜率"
                :value="`${tracking.paper_stats.win_rate ?? '—'}%`"
                :tone="(tracking.paper_stats.win_rate ?? 0) >= 50 ? 'up' : 'down'"
              />
            </v-col>
            <v-col cols="6">
              <MetricCard
                label="均收益"
                :value="formatSignedPercent(tracking.paper_stats.avg_pnl_pct)"
                :tone="toneOf(tracking.paper_stats.avg_pnl_pct)"
              />
            </v-col>
            <v-col cols="6">
              <MetricCard
                label="累计"
                :value="formatSignedPercent(tracking.paper_stats.sum_pnl_pct)"
                :tone="toneOf(tracking.paper_stats.sum_pnl_pct)"
              />
            </v-col>
          </v-row>
        </template>
        <div v-else class="text-caption text-medium-emphasis">
          还没有平仓记录，样本攒够后这里会显示胜率与平均收益。
        </div>

        <div v-if="tracking.trades.length > 0" class="text-caption text-medium-emphasis mt-2">
          最近：
          <span v-for="trade in tracking.trades.slice(0, 5)" :key="trade.id" class="mr-2 text-no-wrap">
            {{ trade.symbol }}{{ directionTone(trade.direction).label }}
            <span :class="pnlClass(trade.pnl_pct)">{{ formatSignedPercent(trade.pnl_pct) }}</span>
            <span class="text-medium-emphasis">({{ exitReasonLabel(trade.reason) }})</span>
          </span>
        </div>
      </v-col>
    </v-row>

    <SectionHeader
      icon="mdi-chart-timeline"
      title="信号前视收益"
      description="按周期 × 策略，扣成本前"
      spaced
    />
    <v-table v-if="tracking.forward_stats.length > 0" density="compact">
      <thead>
        <tr>
          <th class="text-left">周期</th>
          <th class="text-left">策略</th>
          <th class="text-right">样本</th>
          <th v-for="bar in tracking.params.forward_bars" :key="bar" class="text-right">
            T+{{ bar }}
          </th>
          <th class="text-right">胜率</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in tracking.forward_stats" :key="`${row.timeframe}-${row.strategy}`">
          <td>{{ row.timeframe }}</td>
          <td>{{ strategyLabel(row.strategy) }}</td>
          <td class="text-right num">{{ row.samples }}</td>
          <td v-for="bar in tracking.params.forward_bars" :key="bar" class="text-right num">
            <span :class="pnlClass(Number(row[`h${bar}`]))">{{
              formatSignedPercent(Number(row[`h${bar}`]))
            }}</span>
          </td>
          <td class="text-right num">{{ row.h4_win ?? '—' }}%</td>
        </tr>
      </tbody>
    </v-table>
    <EmptyState
      v-else
      icon="mdi-chart-timeline"
      title="还没有前视结果"
      description="信号产生后需要再走满 4 / 12 根 K 线才会回填，稍后再看。"
    />
  </div>
</template>

<script setup lang="ts">
import SectionHeader from '@/components/SectionHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import MetricCard from '@/components/MetricCard.vue'
import type { LiveExitStatus, SignalTracking } from '@/models/types'
import { directionTone, pnlClass, pnlTone } from '@/utils/tone'
import { formatAutoPrecision, formatIsoTime as formatTime, formatSignedPercent } from '@/utils/format'

const props = defineProps<{
  tracking: SignalTracking
  liveExit: LiveExitStatus
  strategyLabels: Record<string, string>
}>()

const strategyLabel = (strategy: string): string => props.strategyLabels[strategy] ?? strategy

const formatPrice = (value: number): string => formatAutoPrecision(value)

const toneOf = (value: unknown): 'up' | 'down' | 'neutral' => {
  const num = Number(value)
  const tone = pnlTone(Number.isFinite(num) ? num : null).color
  return tone === 'up' || tone === 'down' ? tone : 'neutral'
}

const exitReasonLabel = (reason: string): string => {
  const labels: Record<string, string> = { stop: '止损', target: '止盈', time: '超时' }
  return labels[reason] ?? reason
}
</script>
