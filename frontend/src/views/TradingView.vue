<!-- frontend/src/views/TradingView.vue (最终修正版) -->
<template>
  <div :style="{ paddingBottom: $vuetify.display.smAndDown ? '128px' : '80px' }">
    <v-container fluid>
      <v-row>
        <v-col cols="12">
          <ControlPanel v-model="activeTab" />
        </v-col>
      </v-row>
    </v-container>
  </div>

  <v-footer
    style="
      position: fixed;
      bottom: 0;
      right: 0;
      z-index: 1000;
      border-top: 1px solid rgba(255, 255, 255, 0.12);
    "
    class="pa-0"
    :style="footerStyle"
  >
    <v-card flat tile class="d-flex align-center px-4 w-100" height="64px">
      <v-spacer></v-spacer>

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
    </v-card>
  </v-footer>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useDisplay } from 'vuetify'
import { useUiStore } from '@/stores/uiStore'
import { usePositionStore } from '@/stores/positionStore'
import { useSettingsStore } from '@/stores/settingsStore'
import ControlPanel from '@/components/ControlPanel.vue'
import apiClient from '@/services/api'
import type { RebalanceCriteria } from '@/models/types'

const uiStore = useUiStore()
const positionStore = usePositionStore()
const settingsStore = useSettingsStore()
const vuetifyDisplay = useDisplay()

const activeTab = ref('general')
const isGeneratingPlan = ref(false)

const footerStyle = computed(() => {
  const styles: { bottom: string; left: string } = {
    bottom: vuetifyDisplay.smAndDown.value ? '56px' : '0px',
    left: '0px',
  }
  if (vuetifyDisplay.mdAndUp.value && vuetifyDisplay.application) {
    styles.left = `${vuetifyDisplay.application.left}px`
  }
  return styles
})

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
      leverage,
    } = settingsStore.settings

    const payload = {
      enable_long_sl_tp,
      long_stop_loss_percentage,
      long_take_profit_percentage,
      enable_short_sl_tp,
      short_stop_loss_percentage,
      short_take_profit_percentage,
      leverage,
    }

    uiStore.launchTask(
      '/api/trading/sync-sltp',
      payload,
      '同步SL/TP',
      positionStore.positions.length,
    )
  }
}

// --- 核心修改在这里 ---
const onGenerateRebalancePlan = () => {
  if (settingsStore.settings) {
    // 创建一个完整的 criteria 对象，包含所有在UI上配置的参数
    const criteria: RebalanceCriteria = {
      method: settingsStore.settings.rebalance_method,
      top_n: settingsStore.settings.rebalance_top_n,
      min_volume_usd: settingsStore.settings.rebalance_min_volume_usd,
      abs_momentum_days: settingsStore.settings.rebalance_abs_momentum_days,
      rel_strength_days: settingsStore.settings.rebalance_rel_strength_days,
      foam_days: settingsStore.settings.rebalance_foam_days,
      rebalance_volume_ma_days: settingsStore.settings.rebalance_volume_ma_days,
      rebalance_volume_spike_ratio: settingsStore.settings.rebalance_volume_spike_ratio,

      // --- 新增：添加所有缺失的参数 ---
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
    // 使用这个完整的对象去调用处理函数
    handleGenerateRebalancePlan(criteria)
  }
}
// --- 修改结束 ---

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
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message
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
