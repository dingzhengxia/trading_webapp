<!-- frontend/src/components/signals/ExitStatsPanel.vue -->
<!-- 出场与统计：出场规则、纸面跟踪、实盘登记、前视收益。纯「读+调参」，收进 Tab -->
<template>
  <div>
    <SectionHeader
      icon="mdi-chart-timeline-variant"
      title="出场层"
      description="实盘条件单与纸面模拟共用同一份价格计算"
    >
      <v-chip size="x-small" variant="tonal" :color="tracking.params.enabled ? 'success' : 'grey'">
        {{ tracking.params.enabled ? '纸面跟踪中' : '纸面未启用' }}
      </v-chip>
      <v-chip size="x-small" variant="tonal" :color="liveExit.enabled ? 'warning' : 'grey'">
        {{ liveExit.enabled ? '实盘超时平仓' : '实盘不超时' }}
      </v-chip>
    </SectionHeader>

    <v-alert type="info" variant="tonal" density="compact" class="mb-4 text-caption">
      止盈止损价格由 <code>core/exit_rules.py</code> 统一计算：实盘条件单和纸面模拟读同一份实现，
      改一个参数两边同时改。ATR 口径会真实改变实盘挂单（拿不到 ATR 时自动回退百分比）。
    </v-alert>

    <v-btn-toggle
      :model-value="exitMode"
      mandatory
      divided
      density="compact"
      variant="outlined"
      class="mb-2"
      @update:model-value="emit('change-mode', $event)"
    >
      <v-btn value="percent" size="small">百分比（现设）</v-btn>
      <v-btn value="atr" size="small">ATR 止损</v-btn>
    </v-btn-toggle>
    <p class="text-caption text-medium-emphasis mb-4">
      {{
        exitMode === 'percent'
          ? '价格距离 = 设置页的保证金百分比 ÷ 杠杆；实盘条件单与纸面模拟用的是同一套价格。'
          : '止损 = N × ATR，止盈 = R × 止损距离；实盘条件单也按这个挂，拿不到 ATR 时回退百分比。'
      }}
    </p>

    <v-row dense align="center">
      <v-col cols="12" sm="6" md="3">
        <v-switch
          :model-value="tracking.params.enabled"
          :loading="savingPaperToggle"
          label="启用纸面跟踪"
          color="primary"
          hide-details
          @update:model-value="emit('toggle-paper', $event)"
        />
      </v-col>
      <v-col cols="6" sm="3" md="2">
        <v-text-field
          v-model.number="paperForm.slAtr"
          label="止损 (ATR 倍数)"
          type="number"
          min="0.2"
          max="10"
          step="0.1"
          :disabled="exitMode !== 'atr'"
          @update:model-value="emit('dirty')"
        />
      </v-col>
      <v-col cols="6" sm="3" md="2">
        <v-text-field
          v-model.number="paperForm.tpR"
          label="止盈 (R 倍数)"
          type="number"
          min="0.5"
          max="10"
          step="0.5"
          :disabled="exitMode !== 'atr'"
          @update:model-value="emit('dirty')"
        />
      </v-col>
      <v-col cols="6" sm="3" md="2">
        <v-text-field
          v-model.number="paperForm.maxBars"
          label="最大持有 (根)"
          type="number"
          min="1"
          max="100"
          @update:model-value="emit('dirty')"
        />
      </v-col>
      <v-col cols="6" sm="3" md="3">
        <v-btn
          color="primary"
          variant="tonal"
          prepend-icon="mdi-content-save"
          :loading="savingPaperConfig"
          :disabled="!valid || savingPaperConfig"
          block
          @click="emit('save-paper')"
        >
          保存参数
        </v-btn>
      </v-col>
    </v-row>

    <v-divider class="my-4" />

    <v-row dense align="center">
      <v-col cols="12" sm="6" md="3">
        <v-select
          v-model="paperForm.atrTimeframe"
          :items="atrTimeframes"
          label="实盘 ATR 周期"
          :disabled="exitMode !== 'atr'"
          hide-details
          @update:model-value="emit('dirty')"
        />
      </v-col>
      <v-col cols="12" sm="6" md="4">
        <v-switch
          :model-value="liveExit.enabled"
          :loading="savingLiveTimeout"
          label="实盘超时平仓"
          color="warning"
          hide-details
          @update:model-value="emit('toggle-live-timeout', $event)"
        />
      </v-col>
      <v-col cols="12" md="5" class="text-caption text-medium-emphasis">
        持有满「最大持有」根就市价平掉信号自动开的仓；手动仓不动。
      </v-col>

      <v-col cols="12" sm="6" md="4" class="mt-2">
        <v-switch
          :model-value="liveExit.guard_enabled"
          :loading="savingSltpGuard"
          label="止损巡检（缺单自动补挂）"
          color="success"
          hide-details
          @update:model-value="emit('toggle-sltp-guard', $event)"
        />
      </v-col>
      <v-col cols="12" md="8" class="text-caption text-medium-emphasis mt-2">
        每 5 分钟核对所有持仓（手动与自动都算）：没有止损单就按当前口径补挂；只补挂、不平仓。
      </v-col>
    </v-row>

    <template v-if="liveExit.positions.length > 0">
      <SectionHeader icon="mdi-shield-half-full" title="实盘已登记" :description="`${liveExit.positions.length} 个`" spaced />
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

    <v-row dense class="mt-4">
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
import { formatIsoTime as formatTime, formatSignedPercent } from '@/utils/format'

export interface PaperForm {
  slAtr: number
  tpR: number
  maxBars: number
  atrTimeframe: string
}

const props = withDefaults(
  defineProps<{
    exitMode: string
    tracking: SignalTracking
    liveExit: LiveExitStatus
    paperForm: PaperForm
    atrTimeframes: string[]
    strategyLabels: Record<string, string>
    valid: boolean
    savingPaperConfig?: boolean
    savingPaperToggle?: boolean
    savingLiveTimeout?: boolean
    savingSltpGuard?: boolean
  }>(),
  {
    savingPaperConfig: false,
    savingPaperToggle: false,
    savingLiveTimeout: false,
    savingSltpGuard: false,
  },
)

const paperForm = props.paperForm

const emit = defineEmits<{
  (e: 'change-mode', value: unknown): void
  (e: 'toggle-paper', value: unknown): void
  (e: 'save-paper'): void
  (e: 'toggle-live-timeout', value: unknown): void
  (e: 'toggle-sltp-guard', value: unknown): void
  (e: 'dirty'): void
}>()

const strategyLabel = (strategy: string): string => props.strategyLabels[strategy] ?? strategy

const formatPrice = (value: number): string => {
  const num = Number(value)
  if (!Number.isFinite(num)) return '—'
  if (num >= 1000) return num.toLocaleString('en-US', { maximumFractionDigits: 2 })
  return num.toLocaleString('en-US', { maximumFractionDigits: 6 })
}

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
