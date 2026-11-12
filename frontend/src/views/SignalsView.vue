<!-- frontend/src/views/SignalsView.vue (信号监控) -->
<template>
  <div>
    <!-- 卡 1：信号扫描 -->
    <PageCard icon="mdi-radar" title="信号扫描" :error="status.last_error">
      <template #badges>
        <v-chip size="small" variant="tonal" :color="status.running ? 'warning' : 'success'">
          {{ status.running ? '扫描中' : '空闲' }}
        </v-chip>
        <v-chip size="small" variant="tonal" :color="status.enabled ? 'success' : 'grey'">
          {{ status.enabled ? '扫描已启用' : '扫描已停用' }}
        </v-chip>
      </template>

      <v-row dense align="center">
        <v-col cols="12" sm="6" md="3">
          <v-switch
            :model-value="status.enabled"
            :loading="savingScan"
            label="启用信号扫描"
            color="primary"
            inset
            hide-details
            @update:model-value="onToggleScan"
          ></v-switch>
        </v-col>
        <v-col cols="12" md="9">
          <div class="d-flex flex-wrap ga-2 align-center">
            <v-chip size="small" variant="tonal" prepend-icon="mdi-clock-outline">
              上次扫描: {{ formatTime(status.last_scan_at) }}
            </v-chip>
            <v-chip size="small" variant="tonal" prepend-icon="mdi-timer-outline">
              下次扫描: {{ formatTime(status.next_scan_at) }}
            </v-chip>
            <v-chip size="small" variant="tonal" prepend-icon="mdi-format-list-bulleted">
              已扫描币种: {{ status.scanned_symbols }}
            </v-chip>
            <v-chip size="small" variant="tonal" prepend-icon="mdi-signal">
              累计信号: {{ status.emitted_count }}
            </v-chip>
            <v-chip
              size="small"
              variant="tonal"
              prepend-icon="mdi-robot"
              :color="status.auto_trade_enabled ? 'success' : 'grey'"
            >
              自动开仓: {{ status.auto_trade_enabled ? '已启用' : '已停用' }}
            </v-chip>
            <v-chip
              size="small"
              variant="tonal"
              :color="status.error_count > 0 ? 'error' : undefined"
              prepend-icon="mdi-alert-circle-outline"
            >
              错误数: {{ status.error_count }}
            </v-chip>
          </div>
        </v-col>
      </v-row>

      <div class="d-flex flex-wrap align-center ga-2 mt-3">
        <v-btn
          color="primary"
          variant="tonal"
          prepend-icon="mdi-magnify-scan"
          :loading="scanning"
          :disabled="scanning"
          @click="scanNow"
        >
          立即扫描
        </v-btn>
        <v-btn
          color="warning"
          variant="tonal"
          prepend-icon="mdi-broom"
          :loading="clearing"
          :disabled="clearing || signals.length === 0"
          @click="clearSignals"
        >
          清空信号
        </v-btn>
        <v-spacer></v-spacer>
        <span class="text-caption text-grey">每 10 秒自动刷新</span>
        <v-btn variant="text" prepend-icon="mdi-refresh" :loading="loading" @click="refresh">
          刷新
        </v-btn>
      </div>

      <v-divider class="my-4"></v-divider>

      <!-- 扫描范围：静态币 + Top N + 周期 -->
      <div class="d-flex align-center flex-wrap ga-2 mb-3">
        <v-icon size="18" color="primary">mdi-format-list-checks</v-icon>
        <span class="text-subtitle-1 font-weight-medium">扫描范围</span>
        <span class="text-caption text-grey">
          静态币始终扫描并在钉钉实时推送，其余按成交额补足 Top N
        </span>
      </div>

      <v-row dense>
        <v-col cols="12" md="5">
          <div class="text-caption text-grey mb-1">静态币种（{{ scanStaticSymbols.length }} 个）</div>
          <div class="d-flex flex-wrap align-center ga-1 mb-2 static-symbol-chips">
            <v-chip
              v-for="symbol in scanStaticSymbols"
              :key="symbol"
              size="small"
              variant="tonal"
              closable
              @click:close="removeStaticSymbol(symbol)"
            >
              {{ symbol }}
            </v-chip>
            <span v-if="scanStaticSymbols.length === 0" class="text-caption text-grey">
              未设置，仅按成交额 Top N 扫描
            </span>
          </div>
          <div class="d-flex ga-2">
            <v-text-field
              v-model="staticSymbolInput"
              density="compact"
              variant="outlined"
              hide-details
              placeholder="输入币种（如 SOL），回车添加"
              @keydown.enter.prevent="addStaticSymbol"
            ></v-text-field>
            <v-btn
              color="primary"
              variant="tonal"
              height="40"
              :disabled="!staticSymbolInput.trim()"
              @click="addStaticSymbol"
            >
              添加
            </v-btn>
          </div>
        </v-col>
        <v-col cols="12" sm="6" md="2">
          <v-text-field
            v-model.number="scopeTopN"
            label="Top N 补足"
            type="number"
            min="1"
            max="500"
            density="compact"
            variant="outlined"
            hide-details
            hint="按成交额排名补足"
            persistent-hint
            @update:model-value="scopeDirty = true"
          ></v-text-field>
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <SmartSelect
            v-model="scopeTimeframes"
            :items="timeframeOptions"
            label="扫描周期"
            multiple
            @update:model-value="scopeDirty = true"
          ></SmartSelect>
        </v-col>
        <v-col cols="12" md="2" class="d-flex justify-end align-center">
          <v-btn
            color="primary"
            variant="tonal"
            prepend-icon="mdi-content-save"
            :loading="savingScope"
            :disabled="!scopeValid || savingScope"
            @click="saveScanScope"
          >
            保存范围
          </v-btn>
        </v-col>
      </v-row>
    </PageCard>

    <!-- 卡 2：推送与开仓（统一编排：先推送后开仓） -->
    <PageCard icon="mdi-bell-ring-outline" title="推送与开仓" spaced>
      <template #badges>
        <v-chip size="small" variant="tonal" :color="autoTradeEnabled ? 'success' : 'grey'">
      {{ autoTradeEnabled ? '自动开仓已启用' : '自动开仓已停用' }}
        </v-chip>
      </template>

        <!-- A. 钉钉推送 -->
        <div class="d-flex align-center flex-wrap ga-2 mb-3">
          <v-icon size="18" color="primary">mdi-bell-ring-outline</v-icon>
          <span class="text-subtitle-1 font-weight-medium">钉钉推送</span>
          <v-chip
            size="x-small"
            variant="tonal"
            :color="pushStatus.dingtalk_configured ? 'success' : 'warning'"
          >
            {{ pushStatus.dingtalk_configured ? 'Webhook 已配置' : '未配置 DINGTALK_WEBHOOK_URL' }}
          </v-chip>
        </div>

        <v-row dense align="center">
          <v-col cols="12" sm="6" md="3">
            <v-switch
              :model-value="pushStatus.signal_dingtalk_enabled"
              :loading="savingDingtalkPush"
              :disabled="!pushStatus.dingtalk_configured || !pushStatus.dingtalk_enabled"
              label="币种信号推送"
              color="primary"
              inset
              hide-details
              @update:model-value="onToggleDingtalkPush"
            ></v-switch>
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-text-field
              v-model.number="pushVolumeInput"
              label="非静态币推送量能倍数"
              type="number"
              min="0"
              max="100"
              step="0.5"
              hint="当前量/动态基准 ≥ 该倍数才推送；0 = 不过滤"
              persistent-hint
              @update:model-value="pushVolumeDirty = true"
            ></v-text-field>
          </v-col>
          <v-col cols="12" sm="6" md="2" class="d-flex justify-end">
            <v-btn
              color="primary"
              variant="tonal"
              prepend-icon="mdi-content-save"
              :loading="savingPushConfig"
              @click="savePushVolume"
            >
              保存
            </v-btn>
          </v-col>
          <v-col cols="12" md="4">
            <div class="text-caption text-grey">
              静态币（{{ pushStatus.static_symbols.join(' / ') || '无' }}）始终实时推送；
              其它币种需放量达标。此门槛只作用于推送，不影响信号列表与自动开仓。
            </div>
          </v-col>
        </v-row>

        <v-divider class="my-4"></v-divider>

        <!-- B. 自动开仓 -->
        <div class="d-flex align-center flex-wrap ga-2 mb-3">
          <v-icon size="18" color="primary">mdi-robot</v-icon>
          <span class="text-subtitle-1 font-weight-medium">信号自动开仓</span>
          <span class="text-caption text-grey">最近自动开仓: {{ lastAutoOpenText }}</span>
        </div>

        <v-alert type="warning" variant="tonal" density="compact" class="mb-4 text-caption">
          <div>· 信号为技术指标信号，不构成收益保证；自动开仓使用限价 post-only 单。</div>
          <div>· 扫描与自动开仓默认关闭，开启后才会请求交易所行情并可能自动开仓（开仓后按现有 SL/TP 设置挂单）。</div>
        </v-alert>

        <v-row dense align="center" class="mb-1">
          <v-col cols="12" sm="6" md="3">
            <v-switch
              :model-value="autoTradeEnabled"
              :loading="savingAutoTrade"
              label="启用自动开仓"
              color="primary"
              inset
              hide-details
              @update:model-value="onToggleAutoTrade"
            ></v-switch>
          </v-col>
        </v-row>

        <v-row dense>
          <v-col cols="12" md="6">
            <SmartSelect
              v-model="autoForm.directions"
              :items="directionOptions"
              item-title="title"
              item-value="value"
              label="允许方向"
              multiple
              @update:model-value="markAutoFormDirty"
            ></SmartSelect>
          </v-col>
          <v-col cols="12" md="6">
            <SmartSelect
              v-model="autoForm.timeframes"
              :items="timeframeOptions"
              label="允许周期"
              multiple
              @update:model-value="markAutoFormDirty"
            ></SmartSelect>
          </v-col>
          <v-col cols="12">
            <SmartSelect
              v-model="autoForm.strategies"
              :items="strategyOptions"
              item-title="title"
              item-value="value"
              label="策略白名单（观望类策略不会自动开仓）"
              multiple
              @update:model-value="markAutoFormDirty"
            ></SmartSelect>
          </v-col>
        </v-row>

        <v-row dense class="mt-1">
          <v-col cols="12" sm="6" md="4">
            <v-text-field
              v-model.number="autoForm.confirmations"
              label="确认数"
              type="number"
              min="1"
              density="compact"
              variant="outlined"
              hide-details
              hint="同方向不同信号族数达到该值才开仓"
              persistent-hint
              @update:model-value="markAutoFormDirty"
            ></v-text-field>
          </v-col>
          <v-col cols="12" sm="6" md="4">
            <v-text-field
              v-model.number="autoForm.confirmationWindowSeconds"
              label="确认窗口 (秒)"
              type="number"
              min="1"
              density="compact"
              variant="outlined"
              hide-details
              hint="统计确认数的回溯窗口"
              persistent-hint
              @update:model-value="markAutoFormDirty"
            ></v-text-field>
          </v-col>
          <v-col cols="12" sm="6" md="4">
            <v-text-field
              v-model.number="autoForm.cooldownSeconds"
              label="冷却时间 (秒)"
              type="number"
              min="0"
              density="compact"
              variant="outlined"
              hide-details
              hint="同币种自动开仓最小间隔"
              persistent-hint
              @update:model-value="markAutoFormDirty"
            ></v-text-field>
          </v-col>
          <v-col cols="12" sm="6" md="4">
            <v-text-field
              v-model.number="autoForm.valueUsd"
              label="单笔金额 (USD)"
              type="number"
              min="1"
              density="compact"
              variant="outlined"
              hide-details
              hint="每次自动开仓的目标名义价值"
              persistent-hint
              @update:model-value="markAutoFormDirty"
            ></v-text-field>
          </v-col>
          <v-col cols="12" sm="6" md="4">
            <v-text-field
              v-model.number="autoForm.maxPositions"
              label="最大持仓数"
              type="number"
              min="1"
              density="compact"
              variant="outlined"
              hide-details
              hint="当前持仓达到该值后不再自动开仓"
              persistent-hint
              @update:model-value="markAutoFormDirty"
            ></v-text-field>
          </v-col>
        </v-row>

        <div class="d-flex align-center mt-4">
          <span v-if="!autoFormValid" class="text-caption text-error">
            请检查：方向/策略/周期至少各选一项，数字参数需大于 0。
          </span>
          <v-spacer></v-spacer>
          <v-btn
            color="primary"
            variant="tonal"
            prepend-icon="mdi-content-save"
            :loading="savingAuto"
            :disabled="!autoFormValid || savingAuto"
            @click="saveAutoConfig"
          >
            保存自动开仓配置
          </v-btn>
        </div>
    </PageCard>

    <!-- 卡 3：纸面跟踪与结果（只记录不下单，为调参提供反馈闭环） -->
    <PageCard icon="mdi-chart-timeline-variant" title="纸面跟踪与结果" spaced>
      <template #badges>
        <v-chip size="small" variant="tonal" :color="paperEnabled ? 'success' : 'grey'">
          {{ paperEnabled ? '纸面跟踪中' : '未启用' }}
        </v-chip>
        <v-chip v-if="tracking.paper_stats.total > 0" size="small" variant="tonal" color="info">
          已平仓 {{ tracking.paper_stats.total }} 笔 / 胜率 {{ tracking.paper_stats.win_rate }}%
        </v-chip>
      </template>

        <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-caption">
          纸面跟踪复用自动开仓的过滤链（方向/策略/周期/确认数/冷却/持仓上限），<b>只记录不下单</b>，
          出场按 ATR 止损 / R 倍数止盈 / 超时平仓模拟。用来在不冒资金风险的前提下，
          验证「这套信号真的能不能赚」。
        </v-alert>

        <v-row dense align="center">
          <v-col cols="12" sm="6" md="3">
            <v-switch
              :model-value="paperEnabled"
              :loading="savingPaperToggle"
              label="启用纸面跟踪"
              color="primary"
              inset
              hide-details
              @update:model-value="onTogglePaper"
            ></v-switch>
          </v-col>
          <v-col cols="12" sm="4" md="2">
            <v-text-field
              v-model.number="paperForm.slAtr"
              label="止损 (ATR 倍数)"
              type="number"
              min="0.2"
              max="10"
              step="0.1"
              density="compact"
              variant="outlined"
              hide-details
              @update:model-value="paperDirty = true"
            ></v-text-field>
          </v-col>
          <v-col cols="12" sm="4" md="2">
            <v-text-field
              v-model.number="paperForm.tpR"
              label="止盈 (R 倍数)"
              type="number"
              min="0.5"
              max="10"
              step="0.5"
              density="compact"
              variant="outlined"
              hide-details
              @update:model-value="paperDirty = true"
            ></v-text-field>
          </v-col>
          <v-col cols="12" sm="4" md="2">
            <v-text-field
              v-model.number="paperForm.maxBars"
              label="最大持有 (根)"
              type="number"
              min="1"
              max="100"
              density="compact"
              variant="outlined"
              hide-details
              @update:model-value="paperDirty = true"
            ></v-text-field>
          </v-col>
          <v-col cols="12" md="3" class="d-flex justify-end">
            <v-btn
              color="primary"
              variant="tonal"
              prepend-icon="mdi-content-save"
              :loading="savingPaperConfig"
              :disabled="!paperFormValid || savingPaperConfig"
              @click="savePaperConfig"
            >
              保存参数
            </v-btn>
          </v-col>
        </v-row>

        <v-row dense class="mt-3">
          <v-col cols="12" md="7">
            <div class="text-subtitle-2 mb-1">纸面持仓（{{ tracking.open_positions.length }}）</div>
            <v-table v-if="tracking.open_positions.length > 0" density="compact">
              <thead>
                <tr>
                  <th class="text-left">币种</th>
                  <th class="text-left">方向</th>
                  <th class="text-left">周期</th>
                  <th class="text-left">入场</th>
                  <th class="text-left">止损</th>
                  <th class="text-left">止盈</th>
                  <th class="text-left">开仓时间</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="position in tracking.open_positions" :key="position.id">
                  <td class="font-weight-medium">{{ position.symbol }}</td>
                  <td>
                    <v-chip size="x-small" variant="tonal" :color="directionColor(position.direction)">
                      {{ directionLabel(position.direction) }}
                    </v-chip>
                  </td>
                  <td>{{ position.timeframe }}</td>
                  <td>${{ formatPrice(position.entry_price) }}</td>
                  <td class="text-error">${{ formatPrice(position.stop_loss) }}</td>
                  <td class="text-success">${{ formatPrice(position.take_profit) }}</td>
                  <td class="text-caption text-grey">{{ formatTime(position.opened_at) }}</td>
                </tr>
              </tbody>
            </v-table>
            <v-alert v-else type="info" variant="text" density="compact" class="text-caption">
              暂无纸面持仓。启用后，通过过滤链的信号会在这里模拟建仓。
            </v-alert>
          </v-col>
          <v-col cols="12" md="5">
            <div class="text-subtitle-2 mb-1">已平仓统计</div>
            <div v-if="tracking.paper_stats.total > 0" class="d-flex flex-wrap ga-2 mb-2">
              <v-chip size="small" variant="tonal">样本 {{ tracking.paper_stats.total }}</v-chip>
              <v-chip size="small" variant="tonal">胜率 {{ tracking.paper_stats.win_rate }}%</v-chip>
              <v-chip size="small" variant="tonal">
                均收益 {{ formatPct(tracking.paper_stats.avg_pnl_pct) }}
              </v-chip>
              <v-chip size="small" variant="tonal">累计 {{ formatPct(tracking.paper_stats.sum_pnl_pct) }}</v-chip>
              <v-chip size="small" variant="tonal">均持有 {{ tracking.paper_stats.avg_bars }} 根</v-chip>
            </div>
            <div v-if="tracking.trades.length > 0" class="text-caption text-grey">
              最近：
              <span v-for="trade in tracking.trades.slice(0, 5)" :key="trade.id" class="mr-2">
                {{ trade.symbol }}{{ directionLabel(trade.direction) }}
                <span :class="trade.pnl_pct >= 0 ? 'text-success' : 'text-error'">
                  {{ formatPct(trade.pnl_pct) }}
                </span>
                ({{ exitReasonLabel(trade.reason) }})
              </span>
            </div>
            <div v-else class="text-caption text-grey">还没有平仓记录。</div>
          </v-col>
        </v-row>

        <div class="text-subtitle-2 mt-4 mb-1">
          信号前视收益（按周期 × 策略，扣成本前）
        </div>
        <v-table v-if="tracking.forward_stats.length > 0" density="compact">
          <thead>
            <tr>
              <th class="text-left">周期</th>
              <th class="text-left">策略</th>
              <th class="text-left">样本</th>
              <th v-for="bar in tracking.params.forward_bars" :key="bar" class="text-left">
                T+{{ bar }}
              </th>
              <th class="text-left">胜率</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in tracking.forward_stats" :key="`${row.timeframe}-${row.strategy}`">
              <td>{{ row.timeframe }}</td>
              <td>{{ strategyLabel(row.strategy) }}</td>
              <td>{{ row.samples }}</td>
              <td v-for="bar in tracking.params.forward_bars" :key="bar">
                <span :class="pctClass(row[`h${bar}`])">{{ formatPct(row[`h${bar}`]) }}</span>
              </td>
              <td>{{ row.h4_win ?? '—' }}%</td>
            </tr>
          </tbody>
        </v-table>
        <v-alert v-else type="info" variant="text" density="compact" class="text-caption">
          还没有前视结果。信号产生后需要再走满 {{ tracking.params.forward_bars.join(' / ') }} 根 K 线才会回填。
        </v-alert>
    </PageCard>

    <!-- 卡 4：信号列表 -->
    <PageCard title="信号列表" spaced>
      <template #badges>
        <v-chip size="small" variant="tonal">
      显示 {{ filteredSignals.length }} / 共 {{ signals.length }} 条
        </v-chip>
        <v-btn-toggle
      :model-value="directionFilter"
      mandatory
      density="compact"
      variant="outlined"
      divided
      @update:model-value="onDirectionFilterChange"
        >
      <v-btn value="all" size="small">全部</v-btn>
      <v-btn value="long" size="small">做多</v-btn>
      <v-btn value="short" size="small">做空</v-btn>
      <v-btn value="neutral" size="small">观望</v-btn>
        </v-btn-toggle>
      </template>

        <v-table v-if="filteredSignals.length > 0" density="compact" class="signal-table">
          <thead>
            <tr>
              <th class="text-left">时间</th>
              <th class="text-left">币种</th>
              <th class="text-left">方向</th>
              <th class="text-left">策略</th>
              <th class="text-left">周期</th>
              <th class="text-left">价格</th>
              <th class="text-left">量能</th>
              <th class="text-left">前视</th>
              <th class="text-left">标题 / 说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="signal in filteredSignals" :key="signal.id">
              <td class="text-caption text-no-wrap">{{ formatTime(signal.created_at) }}</td>
              <td class="font-weight-medium text-no-wrap">{{ signal.symbol }}</td>
              <td>
                <v-chip
                  size="small"
                  variant="tonal"
                  :color="directionColor(signal.direction)"
                >
                  {{ directionLabel(signal.direction) }}
                </v-chip>
              </td>
              <td class="text-no-wrap">{{ strategyLabel(signal.strategy) }}</td>
              <td class="text-no-wrap">{{ signal.timeframe }}</td>
              <td class="text-no-wrap">${{ formatPrice(signal.price) }}</td>
              <td class="text-no-wrap text-caption" :class="volumeClass(signal)">{{ volumeLabel(signal) }}</td>
              <td class="text-no-wrap text-caption">{{ fwdLabel(signal) }}</td>
              <td class="signal-title">
                <div class="text-body-2">{{ signal.title }}</div>
                <div class="text-caption text-grey signal-message">{{ plainMessage(signal.message) }}</div>
              </td>
            </tr>
          </tbody>
        </v-table>
        <v-alert v-else type="info" variant="text" density="compact" class="text-caption">
          暂无信号。启用扫描后，命中的技术指标信号会显示在这里；也可点击「立即扫描」手动触发一次。
        </v-alert>
    </PageCard>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import api from '@/services/api'
import { useSnackbarStore } from '@/stores/snackbar'
import { useUiStore } from '@/stores/uiStore'
import type {
  SignalConfig,
  SignalDirection,
  SignalPushStatus,
  SignalRecord,
  SignalsResponse,
  SignalStatus,
  SignalTracking,
} from '@/models/types'
import { getErrorMessage, getErrorStatus } from '@/utils/errors'
import { formatIsoTime as formatTime } from '@/utils/format'
import SmartSelect from '@/components/SmartSelect.vue'
import PageCard from '@/components/PageCard.vue'

const POLL_INTERVAL_MS = 10000

interface AutoTradeForm {
  directions: string[]
  strategies: string[]
  timeframes: string[]
  confirmations: number
  confirmationWindowSeconds: number
  cooldownSeconds: number
  valueUsd: number
  maxPositions: number
}

const directionOptions = [
  { title: '做多', value: 'long' },
  { title: '做空', value: 'short' },
]

const timeframeOptions = ['15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d']

const strategyOptions = [
  { value: 'ema_cross', title: 'EMA 交叉' },
  { value: 'ma_breakout', title: '均线突破' },
  { value: 'kdj_cross', title: 'KDJ 交叉' },
  { value: 'level_breakout', title: '关键位突破 (BOS)' },
  { value: 'rsi_divergence', title: 'RSI 背离' },
  { value: 'trend_channel_breakout', title: '趋势通道突破' },
  { value: 'ob_luxalgo', title: '订单块 (LuxAlgo)' },
  { value: 'ob_fluxcharts', title: '订单块 (FluxCharts)' },
  { value: 'volatility_breakout', title: '波动率突破（观望，不开仓）' },
  { value: 'consecutive_candles', title: '连续 K 线警示（观望，不开仓）' },
]

const strategyTitleMap = new Map(strategyOptions.map((option) => [option.value, option.title]))

const defaultSignalStatus: SignalStatus = {
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
}

const defaultSignalConfig: SignalConfig = {
  signal_scan_enabled: false,
  signal_scan_interval_seconds: 300,
  signal_scan_static_symbols: [],
  signal_scan_top_n: 20,
  signal_scan_timeframes: ['1h', '4h'],
  signal_auto_trade_enabled: false,
  signal_auto_trade_directions: ['long', 'short'],
  signal_auto_trade_strategies: [
    'ema_cross',
    'ma_breakout',
    'kdj_cross',
    'level_breakout',
    'rsi_divergence',
    'trend_channel_breakout',
    'ob_luxalgo',
    'ob_fluxcharts',
  ],
  signal_auto_trade_timeframes: ['1h', '4h'],
  signal_auto_trade_confirmations: 1,
  signal_auto_trade_confirmation_window_seconds: 300,
  signal_auto_trade_cooldown_seconds: 3600,
  signal_auto_trade_max_positions: 5,
  signal_auto_trade_value_usd: 100,
  signal_ticker_cache_seconds: 30,
  signal_ohlcv_cache_seconds: 300,
  signal_dingtalk_enabled: true,
  signal_paper_enabled: false,
  signal_paper_sl_atr: 1.5,
  signal_paper_tp_r: 2,
  signal_paper_max_bars: 6,
  signal_forward_bars: [4, 12],
}

const DIRECTION_FILTERS = ['all', 'long', 'short', 'neutral'] as const
type DirectionFilter = (typeof DIRECTION_FILTERS)[number]

const snackbarStore = useSnackbarStore()
const uiStore = useUiStore()

const status = ref<SignalStatus>({ ...defaultSignalStatus })
const signals = ref<SignalRecord[]>([])
const config = ref<SignalConfig>({ ...defaultSignalConfig })
const loading = ref(false)
const scanning = ref(false)
const clearing = ref(false)
const savingScan = ref(false)
const savingAutoTrade = ref(false)
const savingAuto = ref(false)
const directionFilter = ref<DirectionFilter>('all')
const savingDingtalkPush = ref(false)
const pushStatus = ref<SignalPushStatus>({
  dingtalk_configured: false,
  dingtalk_enabled: false,
  signal_dingtalk_enabled: true,
  signal_push_volume_multiplier: 2,
  static_symbols: [],
})
const savingPushConfig = ref(false)
const pushVolumeInput = ref<number>(2)
const pushVolumeDirty = ref(false)

// ------------------------------------------------- 纸面跟踪（只记录不下单）
const emptyTracking = (): SignalTracking => ({
  params: { enabled: false, sl_atr: 1.5, tp_r: 2, max_bars: 6, value_usd: 100, forward_bars: [4, 12] },
  open_positions: [],
  trades: [],
  paper_stats: {
    total: 0,
    win_rate: null,
    avg_pnl_pct: null,
    avg_bars: null,
    sum_pnl_pct: null,
    by_reason: {},
  },
  forward_stats: [],
})
const tracking = ref<SignalTracking>(emptyTracking())
const savingPaperConfig = ref(false)
const savingPaperToggle = ref(false)
const paperDirty = ref(false)
const paperForm = ref({ slAtr: 1.5, tpR: 2, maxBars: 6 })
const paperEnabled = computed(() => tracking.value.params.enabled)
const paperFormValid = computed(
  () =>
    Number(paperForm.value.slAtr) >= 0.2 &&
    Number(paperForm.value.slAtr) <= 10 &&
    Number(paperForm.value.tpR) >= 0.5 &&
    Number(paperForm.value.tpR) <= 10 &&
    Number(paperForm.value.maxBars) >= 1 &&
    Number(paperForm.value.maxBars) <= 100,
)

// ------------------------------------------------- 扫描范围（静态币 / TopN / 周期）
const savingScope = ref(false)
const scopeDirty = ref(false)
const staticSymbolInput = ref('')
const scanStaticSymbols = ref<string[]>([...defaultSignalConfig.signal_scan_static_symbols])
const scopeTopN = ref<number>(defaultSignalConfig.signal_scan_top_n)
const scopeTimeframes = ref<string[]>([...defaultSignalConfig.signal_scan_timeframes])

const autoForm = ref<AutoTradeForm>({
  directions: [...defaultSignalConfig.signal_auto_trade_directions],
  strategies: [...defaultSignalConfig.signal_auto_trade_strategies],
  timeframes: [...defaultSignalConfig.signal_auto_trade_timeframes],
  confirmations: defaultSignalConfig.signal_auto_trade_confirmations,
  confirmationWindowSeconds: defaultSignalConfig.signal_auto_trade_confirmation_window_seconds,
  cooldownSeconds: defaultSignalConfig.signal_auto_trade_cooldown_seconds,
  valueUsd: defaultSignalConfig.signal_auto_trade_value_usd,
  maxPositions: defaultSignalConfig.signal_auto_trade_max_positions,
})

const autoFormDirty = ref(false)

let pollTimer: number | undefined

const autoTradeEnabled = computed(() => config.value.signal_auto_trade_enabled)

const scopeValid = computed(
  () =>
    scopeTimeframes.value.length > 0 &&
    Number(scopeTopN.value) >= 1 &&
    Number(scopeTopN.value) <= 500,
)

const autoFormValid = computed(() => {
  const form = autoForm.value
  return (
    form.directions.length > 0 &&
    form.strategies.length > 0 &&
    form.timeframes.length > 0 &&
    Number(form.confirmations) >= 1 &&
    Number(form.confirmationWindowSeconds) > 0 &&
    Number(form.cooldownSeconds) >= 0 &&
    Number(form.valueUsd) > 0 &&
    Number(form.maxPositions) >= 1
  )
})

const filteredSignals = computed(() => {
  const list =
    directionFilter.value === 'all'
      ? signals.value
      : signals.value.filter((signal) => signal.direction === directionFilter.value)
  return list.slice(0, 200)
})

const lastAutoOpenText = computed(() => {
  const value = status.value.last_auto_open
  if (!value) return '—'
  if (typeof value === 'string') return value
  const symbol = typeof value.symbol === 'string' ? value.symbol : ''
  const direction = typeof value.direction === 'string' ? value.direction : ''
  const at = typeof value.at === 'string' ? value.at : ''
  if (symbol) {
    const directionText = direction ? directionLabel(direction) : ''
    const atText = at ? formatTime(at) : ''
    return [symbol, directionText, atText].filter((part) => part.length > 0).join(' ')
  }
  return JSON.stringify(value)
})

const toNumber = (value: unknown, fallback: number): number => {
  const num = Number(value)
  return Number.isFinite(num) ? num : fallback
}

const toStringArray = (value: unknown, fallback: string[]): string[] => {
  if (!Array.isArray(value)) return [...fallback]
  return value.filter((item): item is string => typeof item === 'string')
}

const normalizeDirection = (value: unknown): SignalDirection =>
  value === 'long' || value === 'short' || value === 'neutral' ? value : 'neutral'

const normalizeLastAutoOpen = (value: unknown): string | Record<string, unknown> | null => {
  if (typeof value === 'string') return value
  if (value !== null && typeof value === 'object') return value as Record<string, unknown>
  return null
}

const mergePushStatus = (raw: unknown): SignalPushStatus => {
  if (raw === null || typeof raw !== 'object') {
    return {
      dingtalk_configured: false,
      dingtalk_enabled: false,
      signal_dingtalk_enabled: true,
      signal_push_volume_multiplier: 2,
      static_symbols: [],
    }
  }
  const source = raw as Partial<Record<keyof SignalPushStatus, unknown>>
  return {
    dingtalk_configured: source.dingtalk_configured === true,
    dingtalk_enabled: source.dingtalk_enabled === true,
    signal_dingtalk_enabled: source.signal_dingtalk_enabled !== false,
    signal_push_volume_multiplier: toNumber(source.signal_push_volume_multiplier, 2),
    static_symbols: toStringArray(source.static_symbols, []),
  }
}

const mergeStatus = (raw: unknown): SignalStatus => {
  if (raw === null || typeof raw !== 'object') return { ...defaultSignalStatus }
  const source = raw as Partial<Record<keyof SignalStatus, unknown>>
  return {
    enabled: source.enabled === true,
    running: source.running === true,
    last_scan_at: typeof source.last_scan_at === 'string' ? source.last_scan_at : null,
    next_scan_at: typeof source.next_scan_at === 'string' ? source.next_scan_at : null,
    scanned_symbols: toNumber(source.scanned_symbols, 0),
    emitted_count: toNumber(source.emitted_count, 0),
    error_count: toNumber(source.error_count, 0),
    last_error: typeof source.last_error === 'string' ? source.last_error : null,
    auto_trade_enabled: source.auto_trade_enabled === true,
    last_auto_open: normalizeLastAutoOpen(source.last_auto_open),
  }
}

const mergeConfig = (raw: Partial<SignalConfig> | undefined): SignalConfig => {
  const source = (raw ?? {}) as Partial<Record<keyof SignalConfig, unknown>>
  const fallback = defaultSignalConfig
  return {
    signal_scan_enabled: source.signal_scan_enabled === true,
    signal_scan_interval_seconds: toNumber(
      source.signal_scan_interval_seconds,
      fallback.signal_scan_interval_seconds,
    ),
    signal_scan_static_symbols: toStringArray(
      source.signal_scan_static_symbols,
      fallback.signal_scan_static_symbols,
    ),
    signal_scan_top_n: toNumber(source.signal_scan_top_n, fallback.signal_scan_top_n),
    signal_scan_timeframes: toStringArray(
      source.signal_scan_timeframes,
      fallback.signal_scan_timeframes,
    ),
    signal_auto_trade_enabled: source.signal_auto_trade_enabled === true,
    signal_auto_trade_directions: toStringArray(
      source.signal_auto_trade_directions,
      fallback.signal_auto_trade_directions,
    ),
    signal_auto_trade_strategies: toStringArray(
      source.signal_auto_trade_strategies,
      fallback.signal_auto_trade_strategies,
    ),
    signal_auto_trade_timeframes: toStringArray(
      source.signal_auto_trade_timeframes,
      fallback.signal_auto_trade_timeframes,
    ),
    signal_auto_trade_confirmations: toNumber(
      source.signal_auto_trade_confirmations,
      fallback.signal_auto_trade_confirmations,
    ),
    signal_auto_trade_confirmation_window_seconds: toNumber(
      source.signal_auto_trade_confirmation_window_seconds,
      fallback.signal_auto_trade_confirmation_window_seconds,
    ),
    signal_auto_trade_cooldown_seconds: toNumber(
      source.signal_auto_trade_cooldown_seconds,
      fallback.signal_auto_trade_cooldown_seconds,
    ),
    signal_auto_trade_max_positions: toNumber(
      source.signal_auto_trade_max_positions,
      fallback.signal_auto_trade_max_positions,
    ),
    signal_auto_trade_value_usd: toNumber(
      source.signal_auto_trade_value_usd,
      fallback.signal_auto_trade_value_usd,
    ),
    signal_ticker_cache_seconds: toNumber(
      source.signal_ticker_cache_seconds,
      fallback.signal_ticker_cache_seconds,
    ),
    signal_ohlcv_cache_seconds: toNumber(
      source.signal_ohlcv_cache_seconds,
      fallback.signal_ohlcv_cache_seconds,
    ),
    signal_dingtalk_enabled: source.signal_dingtalk_enabled !== false,
    signal_paper_enabled: source.signal_paper_enabled === true,
    signal_paper_sl_atr: toNumber(source.signal_paper_sl_atr, fallback.signal_paper_sl_atr),
    signal_paper_tp_r: toNumber(source.signal_paper_tp_r, fallback.signal_paper_tp_r),
    signal_paper_max_bars: toNumber(source.signal_paper_max_bars, fallback.signal_paper_max_bars),
    signal_forward_bars: Array.isArray(source.signal_forward_bars)
      ? (source.signal_forward_bars as unknown[]).map((bar) => toNumber(bar, 4))
      : [...fallback.signal_forward_bars],
  }
}

const normalizeSignals = (raw: unknown): SignalRecord[] => {
  if (!Array.isArray(raw)) return []
  const result: SignalRecord[] = []
  for (const item of raw) {
    if (item === null || typeof item !== 'object') continue
    const record = item as Partial<Record<keyof SignalRecord, unknown>>
    if (typeof record.symbol !== 'string') continue
    result.push({
      id:
        typeof record.id === 'string'
          ? record.id
          : String(record.symbol) + '-' + String(record.created_at ?? result.length),
      created_at: typeof record.created_at === 'string' ? record.created_at : null,
      symbol: record.symbol,
      full_symbol: typeof record.full_symbol === 'string' ? record.full_symbol : null,
      timeframe: typeof record.timeframe === 'string' ? record.timeframe : '',
      strategy: typeof record.strategy === 'string' ? record.strategy : '',
      strategy_index: toNumber(record.strategy_index, 0),
      direction: normalizeDirection(record.direction),
      price: toNumber(record.price, 0),
      volume_ratio:
        typeof record.volume_ratio === 'number' && Number.isFinite(record.volume_ratio)
          ? record.volume_ratio
          : null,
      fwd:
        record.fwd !== null && typeof record.fwd === 'object'
          ? Object.fromEntries(
              Object.entries(record.fwd as Record<string, unknown>)
                .map(([key, value]) => [key, Number(value)])
                .filter(([, value]) => Number.isFinite(value as number)),
            )
          : null,
      title: typeof record.title === 'string' ? record.title : '',
      message: typeof record.message === 'string' ? record.message : '',
    })
  }
  return result
}

const mergeTracking = (raw: unknown): SignalTracking => {
  const base = emptyTracking()
  if (raw === null || typeof raw !== 'object') return base
  const data = raw as Record<string, unknown>
  const params = (data.params ?? {}) as Record<string, unknown>
  return {
    params: {
      enabled: params.enabled === true,
      sl_atr: toNumber(params.sl_atr, base.params.sl_atr),
      tp_r: toNumber(params.tp_r, base.params.tp_r),
      max_bars: toNumber(params.max_bars, base.params.max_bars),
      value_usd: toNumber(params.value_usd, base.params.value_usd),
      forward_bars: Array.isArray(params.forward_bars)
        ? (params.forward_bars as number[]).map((bar) => toNumber(bar, 4))
        : base.params.forward_bars,
    },
    open_positions: Array.isArray(data.open_positions)
      ? (data.open_positions as SignalTracking['open_positions'])
      : [],
    trades: Array.isArray(data.trades) ? (data.trades as SignalTracking['trades']) : [],
    paper_stats: {
      ...base.paper_stats,
      ...((data.paper_stats ?? {}) as Partial<SignalTracking['paper_stats']>),
    },
    forward_stats: Array.isArray(data.forward_stats)
      ? (data.forward_stats as SignalTracking['forward_stats'])
      : [],
  }
}

const syncPaperForm = (next: SignalTracking): void => {
  if (paperDirty.value) return
  paperForm.value = {
    slAtr: next.params.sl_atr,
    tpR: next.params.tp_r,
    maxBars: next.params.max_bars,
  }
}

const syncAutoForm = (nextConfig: SignalConfig): void => {
  if (autoFormDirty.value) return
  autoForm.value = {
    directions: [...nextConfig.signal_auto_trade_directions],
    strategies: [...nextConfig.signal_auto_trade_strategies],
    timeframes: [...nextConfig.signal_auto_trade_timeframes],
    confirmations: nextConfig.signal_auto_trade_confirmations,
    confirmationWindowSeconds: nextConfig.signal_auto_trade_confirmation_window_seconds,
    cooldownSeconds: nextConfig.signal_auto_trade_cooldown_seconds,
    valueUsd: nextConfig.signal_auto_trade_value_usd,
    maxPositions: nextConfig.signal_auto_trade_max_positions,
  }
}

const markAutoFormDirty = (): void => {
  autoFormDirty.value = true
}

const fetchSignals = async (silent: boolean): Promise<void> => {
  if (!silent) loading.value = true
  try {
    const response = await api.get<SignalsResponse>('/api/signals')
    const data = response.data
    status.value = mergeStatus(data.status)
    signals.value = normalizeSignals(data.signals)
    const nextConfig = mergeConfig(data.config)
    config.value = nextConfig
    pushStatus.value = mergePushStatus(data.push)
    if (!pushVolumeDirty.value) pushVolumeInput.value = pushStatus.value.signal_push_volume_multiplier
    tracking.value = mergeTracking(data.tracking)
    syncPaperForm(tracking.value)
    syncScopeForm(nextConfig)
    syncAutoForm(nextConfig)
  } catch (error: unknown) {
    if (!silent) {
      snackbarStore.show({
        message: '获取信号数据失败: ' + getErrorMessage(error),
        color: 'error',
      })
    }
  } finally {
    if (!silent) loading.value = false
  }
}

const refresh = (): void => {
  void fetchSignals(false)
}

const formatPrice = (value: number): string => {
  const num = Number(value)
  if (!Number.isFinite(num)) return '0'
  if (num >= 1000) return num.toLocaleString('en-US', { maximumFractionDigits: 2 })
  return num.toLocaleString('en-US', { maximumFractionDigits: 6 })
}

const directionLabel = (direction: string): string => {
  const labels: Record<string, string> = { long: '做多', short: '做空', neutral: '观望' }
  return labels[direction] ?? direction
}

const directionColor = (direction: string): string => {
  // 用户偏好：红跌绿涨（做多绿、做空红）
  if (direction === 'long') return 'green'
  if (direction === 'short') return 'red'
  return 'grey'
}

const strategyLabel = (strategy: string): string => strategyTitleMap.get(strategy) ?? strategy

// 量能只记录不拦截：倍数照实展示，是否达到推送门槛用颜色区分（静态币始终推送）
const formatPct = (value: unknown): string => {
  const num = Number(value)
  if (!Number.isFinite(num)) return '—'
  return `${num >= 0 ? '+' : ''}${num.toFixed(2)}%`
}

const pctClass = (value: unknown): string => {
  const num = Number(value)
  if (!Number.isFinite(num)) return 'text-grey'
  // 用户偏好：红跌绿涨
  return num >= 0 ? 'text-success' : 'text-error'
}

const exitReasonLabel = (reason: string): string => {
  const labels: Record<string, string> = { stop: '止损', target: '止盈', time: '超时' }
  return labels[reason] ?? reason
}

const fwdLabel = (signal: SignalRecord): string => {
  if (!signal.fwd) return '—'
  const bars = tracking.value.params.forward_bars
  const parts = bars
    .map((bar) => (signal.fwd && signal.fwd[String(bar)] !== undefined
      ? `T+${bar} ${formatPct(signal.fwd[String(bar)])}`
      : ''))
    .filter((part) => part.length > 0)
  return parts.length > 0 ? parts.join(' / ') : '—'
}

const volumeLabel = (signal: SignalRecord): string =>
  signal.volume_ratio == null ? '—' : `${signal.volume_ratio.toFixed(1)}x`

const volumeClass = (signal: SignalRecord): string => {
  if (signal.volume_ratio == null) return 'text-grey'
  const threshold = pushStatus.value.signal_push_volume_multiplier || 2
  const isStatic = pushStatus.value.static_symbols.includes(signal.symbol)
  return signal.volume_ratio >= threshold || isStatic ? 'text-success font-weight-medium' : 'text-grey'
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

const isDirectionFilter = (value: unknown): value is DirectionFilter =>
  typeof value === 'string' && (DIRECTION_FILTERS as readonly string[]).includes(value)

const onDirectionFilterChange = (value: unknown): void => {
  if (isDirectionFilter(value)) {
    directionFilter.value = value
    return
  }
  if (value === null || value === undefined) {
    directionFilter.value = 'all'
  }
}

const pushLog = (message: string, level: 'info' | 'success' | 'warning' | 'error'): void => {
  uiStore.logStore.addLog({
    message,
    level,
    timestamp: new Date().toLocaleTimeString(),
  })
}

const onToggleScan = async (value: unknown): Promise<void> => {
  const enabled = Boolean(value)
  if (savingScan.value || enabled === status.value.enabled) return
  savingScan.value = true
  const previous = status.value.enabled
  status.value.enabled = enabled
  try {
    const response = await api.post<{ config?: Partial<SignalConfig> }>('/api/signals/config', {
      signal_scan_enabled: enabled,
    })
    if (response.data.config) {
      config.value = mergeConfig({ ...config.value, ...response.data.config })
    }
    config.value.signal_scan_enabled = enabled
    snackbarStore.show({
      message: enabled ? '信号扫描已启用。' : '信号扫描已停用。',
      color: 'success',
    })
    pushLog('[前端] 信号扫描已' + (enabled ? '启用' : '停用') + '。', 'info')
    await fetchSignals(true)
  } catch (error: unknown) {
    status.value.enabled = previous
    config.value.signal_scan_enabled = previous
    snackbarStore.show({
      message: '切换扫描开关失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    savingScan.value = false
  }
}

const syncScopeForm = (nextConfig: SignalConfig): void => {
  // 有未保存的编辑时不回填，避免 10 秒轮询覆盖用户输入
  if (scopeDirty.value) return
  scanStaticSymbols.value = [...nextConfig.signal_scan_static_symbols]
  scopeTopN.value = nextConfig.signal_scan_top_n
  scopeTimeframes.value = [...nextConfig.signal_scan_timeframes]
}

const normalizeSymbolInput = (value: string): string =>
  value.trim().toUpperCase().split('/')[0].split(':')[0]

const addStaticSymbol = (): void => {
  const symbol = normalizeSymbolInput(staticSymbolInput.value)
  if (!symbol) return
  if (!scanStaticSymbols.value.includes(symbol)) {
    scanStaticSymbols.value = [...scanStaticSymbols.value, symbol]
    scopeDirty.value = true
  }
  staticSymbolInput.value = ''
}

const removeStaticSymbol = (symbol: string): void => {
  scanStaticSymbols.value = scanStaticSymbols.value.filter((item) => item !== symbol)
  scopeDirty.value = true
}

const saveScanScope = async (): Promise<void> => {
  if (!scopeValid.value || savingScope.value) return
  savingScope.value = true
  try {
    const payload = {
      signal_scan_static_symbols: [...scanStaticSymbols.value],
      signal_scan_top_n: Number(scopeTopN.value),
      signal_scan_timeframes: [...scopeTimeframes.value],
    }
    const response = await api.post<{ config?: Partial<SignalConfig> }>(
      '/api/signals/config',
      payload,
    )
    if (response.data.config) {
      config.value = mergeConfig({ ...config.value, ...response.data.config })
    }
    scopeDirty.value = false
    snackbarStore.show({
      message: `扫描范围已保存（静态币 ${scanStaticSymbols.value.length} 个 / Top ${scopeTopN.value}）。`,
      color: 'success',
    })
    pushLog(
      '[前端] 扫描范围已保存：静态币 ' +
        (scanStaticSymbols.value.join(',') || '无') +
        `；Top ${scopeTopN.value}；周期 ${scopeTimeframes.value.join('/')}`,
      'success',
    )
    await fetchSignals(true)
  } catch (error: unknown) {
    snackbarStore.show({
      message: '保存扫描范围失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    savingScope.value = false
  }
}

const onTogglePaper = async (value: unknown): Promise<void> => {
  const enabled = Boolean(value)
  if (savingPaperToggle.value || enabled === paperEnabled.value) return
  savingPaperToggle.value = true
  const previous = tracking.value.params.enabled
  tracking.value.params.enabled = enabled
  try {
    await api.post('/api/signals/config', { signal_paper_enabled: enabled })
    snackbarStore.show({
      message: enabled ? '纸面跟踪已启用（只记录，不下单）。' : '纸面跟踪已停用。',
      color: 'success',
    })
    pushLog('[前端] 纸面跟踪已' + (enabled ? '启用' : '停用') + '。', 'info')
    await fetchSignals(true)
  } catch (error: unknown) {
    tracking.value.params.enabled = previous
    snackbarStore.show({
      message: '切换纸面跟踪失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    savingPaperToggle.value = false
  }
}

const savePaperConfig = async (): Promise<void> => {
  if (savingPaperConfig.value || !paperFormValid.value) return
  savingPaperConfig.value = true
  const payload = {
    signal_paper_sl_atr: Number(paperForm.value.slAtr),
    signal_paper_tp_r: Number(paperForm.value.tpR),
    signal_paper_max_bars: Number(paperForm.value.maxBars),
  }
  try {
    await api.post('/api/signals/config', payload)
    paperDirty.value = false
    snackbarStore.show({ message: '纸面出场参数已保存。', color: 'success' })
    pushLog(
      `[前端] 纸面出场参数: 止损 ${payload.signal_paper_sl_atr} ATR / 止盈 ${payload.signal_paper_tp_r}R / 最多 ${payload.signal_paper_max_bars} 根`,
      'success',
    )
    await fetchSignals(true)
  } catch (error: unknown) {
    snackbarStore.show({
      message: '保存纸面出场参数失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    savingPaperConfig.value = false
  }
}

const savePushVolume = async (): Promise<void> => {
  if (savingPushConfig.value) return
  const raw = Number(pushVolumeInput.value)
  const value = Number.isFinite(raw) && raw >= 0 ? Math.min(raw, 100) : 0
  savingPushConfig.value = true
  const previous = pushStatus.value.signal_push_volume_multiplier
  try {
    await api.post('/api/signals/config', { signal_push_volume_multiplier: value })
    pushStatus.value.signal_push_volume_multiplier = value
    pushVolumeDirty.value = false
    const label = value > 0 ? `${value}x` : '不过滤'
    snackbarStore.show({ message: `推送量能门槛已保存（${label}）。`, color: 'success' })
    pushLog(`[前端] 推送量能门槛已保存: ${label}`, 'success')
    await fetchSignals(true)
  } catch (error: unknown) {
    pushStatus.value.signal_push_volume_multiplier = previous
    snackbarStore.show({
      message: '保存推送量能门槛失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    savingPushConfig.value = false
  }
}

const onToggleDingtalkPush = async (value: unknown): Promise<void> => {
  const enabled = Boolean(value)
  if (savingDingtalkPush.value || enabled === pushStatus.value.signal_dingtalk_enabled) return
  savingDingtalkPush.value = true
  const previous = pushStatus.value.signal_dingtalk_enabled
  pushStatus.value.signal_dingtalk_enabled = enabled
  config.value.signal_dingtalk_enabled = enabled
  try {
    await api.post('/api/signals/config', { signal_dingtalk_enabled: enabled })
    snackbarStore.show({
      message: enabled ? '币种信号钉钉推送已启用。' : '币种信号钉钉推送已停用。',
      color: 'success',
    })
    pushLog('[前端] 币种信号钉钉推送已' + (enabled ? '启用' : '停用') + '。', 'info')
    await fetchSignals(true)
  } catch (error: unknown) {
    pushStatus.value.signal_dingtalk_enabled = previous
    config.value.signal_dingtalk_enabled = previous
    snackbarStore.show({
      message: '切换钉钉推送开关失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    savingDingtalkPush.value = false
  }
}

const onToggleAutoTrade = async (value: unknown): Promise<void> => {
  const enabled = Boolean(value)
  if (savingAutoTrade.value || enabled === config.value.signal_auto_trade_enabled) return
  savingAutoTrade.value = true
  const previous = config.value.signal_auto_trade_enabled
  config.value.signal_auto_trade_enabled = enabled
  try {
    await api.post('/api/signals/auto-trade', { enabled })
    snackbarStore.show({
      message: enabled ? '自动开仓已启用。' : '自动开仓已停用。',
      color: 'success',
    })
    pushLog('[前端] 信号自动开仓已' + (enabled ? '启用' : '停用') + '。', 'info')
    await fetchSignals(true)
  } catch (error: unknown) {
    config.value.signal_auto_trade_enabled = previous
    snackbarStore.show({
      message: '切换自动开仓开关失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    savingAutoTrade.value = false
  }
}

const buildAutoConfigPayload = (): Record<string, unknown> => ({
  signal_auto_trade_enabled: config.value.signal_auto_trade_enabled,
  signal_auto_trade_directions: [...autoForm.value.directions],
  signal_auto_trade_strategies: [...autoForm.value.strategies],
  signal_auto_trade_timeframes: [...autoForm.value.timeframes],
  signal_auto_trade_confirmations: Number(autoForm.value.confirmations),
  signal_auto_trade_confirmation_window_seconds: Number(
    autoForm.value.confirmationWindowSeconds,
  ),
  signal_auto_trade_cooldown_seconds: Number(autoForm.value.cooldownSeconds),
  signal_auto_trade_value_usd: Number(autoForm.value.valueUsd),
  signal_auto_trade_max_positions: Number(autoForm.value.maxPositions),
})

const saveAutoConfig = async (): Promise<void> => {
  if (!autoFormValid.value || savingAuto.value) return
  savingAuto.value = true
  try {
    const response = await api.post<{ config?: Partial<SignalConfig> }>(
      '/api/signals/config',
      buildAutoConfigPayload(),
    )
    if (response.data.config) {
      config.value = mergeConfig({ ...config.value, ...response.data.config })
    }
    autoFormDirty.value = false
    syncAutoForm(config.value)
    snackbarStore.show({ message: '自动开仓配置已保存。', color: 'success' })
    pushLog('[前端] 信号自动开仓配置已保存。', 'success')
  } catch (error: unknown) {
    snackbarStore.show({
      message: '保存自动开仓配置失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    savingAuto.value = false
  }
}

const scanNow = async (): Promise<void> => {
  if (scanning.value) return
  scanning.value = true
  try {
    const response = await api.post<{ message?: string }>('/api/signals/scan')
    snackbarStore.show({
      message: response.data?.message ?? '扫描任务已提交。',
      color: 'success',
    })
    pushLog('[前端] 已提交信号扫描任务。', 'info')
    await fetchSignals(true)
  } catch (error: unknown) {
    const statusCode = getErrorStatus(error)
    const isConflict = statusCode === 409
    snackbarStore.show({
      message: isConflict
        ? '已有扫描任务正在运行，请稍后再试。'
        : '提交扫描失败: ' + getErrorMessage(error),
      color: isConflict ? 'warning' : 'error',
    })
  } finally {
    scanning.value = false
  }
}

const clearSignals = async (): Promise<void> => {
  if (clearing.value) return
  clearing.value = true
  try {
    await api.post('/api/signals/clear')
    signals.value = []
    snackbarStore.show({ message: '信号已清空。', color: 'success' })
    pushLog('[前端] 已清空信号列表。', 'info')
    await fetchSignals(true)
  } catch (error: unknown) {
    snackbarStore.show({
      message: '清空信号失败: ' + getErrorMessage(error),
      color: 'error',
    })
  } finally {
    clearing.value = false
  }
}

const stopPolling = (): void => {
  if (pollTimer !== undefined) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
}

const startPolling = (): void => {
  stopPolling()
  pollTimer = window.setInterval(() => {
    if (document.visibilityState === 'visible') {
      void fetchSignals(true)
    }
  }, POLL_INTERVAL_MS)
}

const onVisibilityChange = (): void => {
  if (document.visibilityState === 'visible') {
    void fetchSignals(true)
  }
}

onMounted(() => {
  void fetchSignals(true)
  startPolling()
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onUnmounted(() => {
  stopPolling()
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<style scoped>
.signal-table :deep(th) {
  white-space: nowrap;
}
.signal-table :deep(td) {
  vertical-align: top;
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
/* 静态币 chips 区固定最小高度，避免空/非空切换时行高跳动 */
.static-symbol-chips {
  min-height: 26px;
}
</style>
