<!-- frontend/src/views/TradingView.vue -->
<!-- 首屏职责：盯仓 / 开仓 / 平仓（规格 §1.2）。
     区块顺序：盈亏条 → 多空持仓表（lg 双列 6:6）→ 开仓记录；
     64 个开仓参数控件整体移入共享的 ConfigDrawer，dock 只留三个动作按钮。 -->
<template>
  <div>
    <!-- 未配置提示：多空币种列表均为空时引导先去抽屉里配置（可关闭，本次会话不再出现） -->
    <v-alert
      v-if="showSetupHint"
      type="info"
      variant="tonal"
      density="compact"
      class="mb-3"
      closable
      @click:close="setupHintDismissed = true"
    >
      <span
        class="setup-hint-link"
        role="button"
        tabindex="0"
        @click="openConfig"
        @keydown.enter.prevent="openConfig"
      >
        还没配置开仓参数，先设置币种与金额 →
      </span>
    </v-alert>

    <!-- 盈亏条 -->
    <PnlSummary />

    <!-- 多空持仓：lg 双列 6:6，<lg 纵向。反手 / 平仓都在每张表的行上操作 -->
    <v-row>
      <v-col cols="12" lg="6">
        <PositionsTable
          title="▲ 多头仓位"
          side="long"
          :positions="positionStore.longPositions"
          :loading="positionStore.loading"
          @refresh="positionStore.fetchPositions()"
        />
      </v-col>
      <v-col cols="12" lg="6">
        <PositionsTable
          title="▼ 空头仓位"
          side="short"
          :positions="positionStore.shortPositions"
          :loading="positionStore.loading"
          @refresh="positionStore.fetchPositions()"
        />
      </v-col>
    </v-row>

    <!-- 开仓记录：选币快照 + 每笔开仓结果（自动/信号/手动/再平衡共用台账） -->
    <v-row>
      <v-col cols="12">
        <OpenHistoryPanel />
      </v-col>
    </v-row>
  </div>

  <!-- 固定操作条：开仓设置打开抽屉；校准与开始开仓语义不变 -->
  <AppDockFooter>
    <v-btn
      size="small"
      color="info"
      variant="tonal"
      prepend-icon="mdi-tune-vertical"
      @click="openConfig"
    >
      开仓设置
    </v-btn>
    <v-btn
      size="small"
      color="info"
      variant="tonal"
      :disabled="uiStore.isRunning"
      @click="handleSyncSlTp"
    >
      校准 SL/TP
    </v-btn>
    <v-btn
      size="small"
      color="success"
      variant="tonal"
      prepend-icon="mdi-play"
      :loading="uiStore.isRunning"
      :disabled="uiStore.isRunning"
      @click="handleStartTrading"
    >
      开始开仓
    </v-btn>
  </AppDockFooter>

  <!-- 共享参数抽屉（与信号页复用同一个 ConfigDrawer，禁止各写一套） -->
  <ConfigDrawer v-model="configOpen" title="开仓设置" icon="mdi-tune-vertical" :tabs="configTabs">
    <template #general>
      <ControlPanel section="general" />
    </template>
    <template #rebalance>
      <ControlPanel
        section="rebalance"
        :is-generating-plan="isGeneratingPlan"
        @generate-rebalance="onGenerateRebalancePlan"
      />
    </template>
  </ConfigDrawer>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useUiStore } from '@/stores/uiStore'
import { usePositionStore } from '@/stores/positionStore'
import { useSettingsStore } from '@/stores/settingsStore'
import ControlPanel from '@/components/ControlPanel.vue'
import PositionsTable from '@/components/PositionsTable.vue'
import PnlSummary from '@/components/PnlSummary.vue'
import OpenHistoryPanel from '@/components/OpenHistoryPanel.vue'
import AppDockFooter from '@/components/AppDockFooter.vue'
import ConfigDrawer from '@/components/ConfigDrawer.vue'
import apiClient from '@/services/api'
import type { RebalanceCriteria } from '@/models/types'
import { getErrorMessage } from '@/utils/errors'

const configTabs = [
  { key: 'general', title: '通用开仓设置', icon: 'mdi-tune-vertical' },
  { key: 'rebalance', title: '智能再平衡', icon: 'mdi-calendar-refresh' },
]

const uiStore = useUiStore()
const positionStore = usePositionStore()
const settingsStore = useSettingsStore()

const configOpen = ref(false)
const isGeneratingPlan = ref(false)

const openConfig = () => {
  configOpen.value = true
}

// 首次进入且多空币种列表都为空时提示去配置；关闭后本次会话不再打扰
const setupHintDismissed = ref(false)
const showSetupHint = computed(
  () =>
    !setupHintDismissed.value &&
    !!settingsStore.settings &&
    settingsStore.settings.long_coin_list.length === 0 &&
    settingsStore.settings.short_coin_list.length === 0,
)

const handleStartTrading = () => {
  if (settingsStore.settings) {
    const plan = settingsStore.settings
    const total =
      (plan.enable_long_trades ? plan.long_coin_list.length : 0) +
      (plan.enable_short_trades ? plan.short_coin_list.length : 0)
    uiStore.launchTask('/api/trading/start', plan, '自动开仓', total)
  }
}

const handleSyncSlTp = () => {
  if (settingsStore.settings) {
    const {
      enable_long_sl_tp,
      long_stop_loss_percentage,
      long_take_profit_percentage,
      enable_short_sl_tp,
      short_stop_loss_percentage,
      short_take_profit_percentage,

      // --- 新增: 提取移动止盈参数 ---
      enable_long_trailing_stop,
      long_trailing_stop_callback_rate,
      enable_short_trailing_stop,
      short_trailing_stop_callback_rate,
      // --------------------------

      leverage,
    } = settingsStore.settings

    const payload = {
      enable_long_sl_tp,
      long_stop_loss_percentage,
      long_take_profit_percentage,
      enable_short_sl_tp,
      short_stop_loss_percentage,
      short_take_profit_percentage,

      // --- 新增: 传递参数到后端 ---
      enable_long_trailing_stop,
      long_trailing_stop_callback_rate,
      enable_short_trailing_stop,
      short_trailing_stop_callback_rate,
      // ------------------------

      leverage,
    }

    uiStore.launchTask(
      '/api/trading/sync-sltp',
      payload,
      '同步SL/TP/移动止盈',
      positionStore.positions.length,
    )
  }
}

const onGenerateRebalancePlan = () => {
  if (settingsStore.settings) {
    const criteria: RebalanceCriteria = {
      method: settingsStore.settings.rebalance_method,
      top_n: settingsStore.settings.rebalance_top_n,
      min_volume_usd: settingsStore.settings.rebalance_min_volume_usd,
      abs_momentum_days: settingsStore.settings.rebalance_abs_momentum_days,
      rel_strength_days: settingsStore.settings.rebalance_rel_strength_days,
      rebalance_volume_ma_days: settingsStore.settings.rebalance_volume_ma_days,
      rebalance_volume_spike_ratio: settingsStore.settings.rebalance_volume_spike_ratio,
      rebalance_benchmark_coin: settingsStore.settings.rebalance_benchmark_coin,
      enable_rebalance_filters: settingsStore.settings.enable_rebalance_filters,
      rebalance_rsi_period: settingsStore.settings.rebalance_rsi_period,
      rebalance_rsi_threshold: settingsStore.settings.rebalance_rsi_threshold,
      rebalance_short_term_momentum_days: settingsStore.settings.rebalance_short_term_momentum_days,
      rebalance_short_term_momentum_threshold: settingsStore.settings.rebalance_short_term_momentum_threshold,
      rebalance_bollinger_period: settingsStore.settings.rebalance_bollinger_period,
      rebalance_bollinger_std_dev: settingsStore.settings.rebalance_bollinger_std_dev,
      rebalance_bollinger_width_spike_ratio: settingsStore.settings.rebalance_bollinger_width_spike_ratio,
    }
    handleGenerateRebalancePlan(criteria)
  }
}

const handleGenerateRebalancePlan = async (criteria: RebalanceCriteria) => {
  if (uiStore.isRunning || isGeneratingPlan.value) return
  isGeneratingPlan.value = true
  uiStore.logStore.addLog({
    message: '[前端] 正在生成再平衡计划...',
    level: 'info',
    timestamp: new Date().toLocaleTimeString(),
  })
  try {
    const response = await apiClient.post('/api/rebalance/plan', criteria)
    const planData = response.data
    if (planData.error) {
      uiStore.logStore.addLog({
        message: `计划生成逻辑错误: ${planData.error}`,
        level: 'error',
        timestamp: new Date().toLocaleTimeString(),
      })
    } else {
      uiStore.rebalancePlan = planData
      uiStore.showRebalanceDialog = true
    }
  } catch (error: unknown) {
    const errorMsg = getErrorMessage(error)
    uiStore.logStore.addLog({
      message: `[后端] ❌ 生成计划请求失败: ${errorMsg}`,
      level: 'error',
      timestamp: new Date().toLocaleTimeString(),
    })
  } finally {
    isGeneratingPlan.value = false
  }
}

onMounted(() => {
  if (positionStore.positions.length === 0) {
    positionStore.fetchPositions()
  }
})
</script>

<style scoped>
.setup-hint-link {
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
}
</style>
