<!-- frontend/src/views/TradingView.vue (完整代码) -->
<template>
  <div :style="{ paddingBottom: '80px' }">
    <v-container fluid>
      <v-row>
        <v-col cols="12">
          <ControlPanel v-model="activeTab" />
        </v-col>
      </v-row>

      <!-- 当前持仓：反手 / 平仓都在这里的每一行上操作 -->
      <v-row>
        <v-col cols="12">
          <PnlSummary />
        </v-col>
      </v-row>

      <!-- 多空仓位（共享面板）：反手 / 平仓都在这里的每一行上操作 -->
      <PositionsPanel />
    </v-container>
  </div>

  <AppDockFooter>
    <template v-if="activeTab === 'general'">
      <v-btn
        color="info"
        variant="tonal"
        @click="handleSyncSlTp"
        :disabled="uiStore.isRunning"
        class="mr-3"
      >
        校准 SL/TP
      </v-btn>
      <v-btn
        color="success"
        variant="tonal"
        prepend-icon="mdi-play"
        @click="handleStartTrading"
        :loading="uiStore.isRunning"
        :disabled="uiStore.isRunning"
      >
        开始开仓
      </v-btn>
    </template>

    <template v-if="activeTab === 'rebalance'">
      <v-btn
        color="primary"
        variant="tonal"
        @click="onGenerateRebalancePlan"
        :loading="isGeneratingPlan"
        :disabled="uiStore.isRunning || isGeneratingPlan"
      >
        生成再平衡计划
      </v-btn>
    </template>
  </AppDockFooter>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useUiStore } from '@/stores/uiStore'
import { usePositionStore } from '@/stores/positionStore'
import { useSettingsStore } from '@/stores/settingsStore'
import ControlPanel from '@/components/ControlPanel.vue'
import PositionsPanel from '@/components/PositionsPanel.vue'
import PnlSummary from '@/components/PnlSummary.vue'
import AppDockFooter from '@/components/AppDockFooter.vue'
import apiClient from '@/services/api'
import type { RebalanceCriteria } from '@/models/types'
import { getErrorMessage } from '@/utils/errors'

const uiStore = useUiStore()
const positionStore = usePositionStore()
const settingsStore = useSettingsStore()

const activeTab = ref('general')
const isGeneratingPlan = ref(false)

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
.v-container {
  overflow: visible;
}
</style>
