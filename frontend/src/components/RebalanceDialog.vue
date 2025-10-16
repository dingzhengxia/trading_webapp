<!-- frontend/src/components/RebalanceDialog.vue (可交互的最终版) -->
<template>
  <v-dialog v-model="uiStore.showRebalanceDialog" max-width="600px" persistent>
    <v-card v-if="uiStore.rebalancePlan">
      <v-card-title class="text-h5">
        再平衡计划
        <!-- 核心修改：标题中的比例现在是可变的 -->
        (目标比例: {{ manualRatio.toFixed(1) }}%)
      </v-card-title>
      <v-card-text>
        <!-- 核心修改：新增滑块和输入框用于手动调整 -->
        <div class="mb-6">
          <v-slider
            v-model="manualRatio"
            :step="0.5"
            color="primary"
            label="手动调整目标比例"
            class="my-4 align-center"
            hide-details
            min="0"
            max="150"
          >
            <template v-slot:thumb-label="{ modelValue }">
              <span class="font-weight-bold">{{ modelValue.toFixed(1) }}%</span>
            </template>
          </v-slider>
        </div>

        <!-- 计划展示区域 -->
        <div v-if="isRecalculating" class="text-center">
          <v-progress-circular indeterminate color="primary"></v-progress-circular>
          <p class="text-caption mt-2">正在重新计算计划...</p>
        </div>
        <div v-else>
          <div v-if="uiStore.rebalancePlan.positions_to_close.length">
            <p class="font-weight-bold">将要平仓/减仓:</p>
            <v-list density="compact">
              <v-list-item v-for="p in uiStore.rebalancePlan.positions_to_close" :key="p.symbol">
                {{ p.symbol }} (-${{ p.close_value.toFixed(2) }},
                {{ p.close_ratio_perc.toFixed(0) }}%)
              </v-list-item>
            </v-list>
          </div>
          <div v-if="uiStore.rebalancePlan.positions_to_open.length" class="mt-4">
            <p class="font-weight-bold">将要开仓/加仓:</p>
            <v-list density="compact">
              <v-list-item v-for="p in uiStore.rebalancePlan.positions_to_open" :key="p.symbol">
                {{ p.symbol }} (+${{ p.open_value.toFixed(2) }}, {{ p.percentage.toFixed(0) }}%)
              </v-list-item>
            </v-list>
          </div>
        </div>

        <v-alert type="warning" variant="tonal" class="mt-4 text-caption">
          警告：此操作将自动执行交易！
        </v-alert>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="blue-darken-1" variant="text" @click="close">取消</v-btn>
        <v-btn color="primary" variant="text" @click="applyList">应用列表到配置</v-btn>
        <v-btn
          color="red-darken-1"
          variant="tonal"
          @click="executePlan"
          :disabled="uiStore.isRunning || isRecalculating"
          >确认执行</v-btn
        >
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useUiStore } from '@/stores/uiStore'
import { useSettingsStore } from '@/stores/settingsStore'
import apiClient from '@/services/api'
import { debounce } from 'lodash-es'

const uiStore = useUiStore()
const settingsStore = useSettingsStore()

// --- 核心修改：新增状态 ---
const manualRatio = ref(0)
const isRecalculating = ref(false)

// 当对话框打开时，用后端建议的比例初始化滑块
watch(
  () => uiStore.rebalancePlan,
  (newPlan) => {
    if (newPlan) {
      manualRatio.value = newPlan.target_ratio_perc
    }
  },
)

// 创建一个带防抖的函数，避免用户拖动滑块时频繁请求后端
const debouncedRecalculatePlan = debounce(async () => {
  if (!settingsStore.settings) return
  isRecalculating.value = true
  try {
    // 复用 TradingView 中用于生成计划的所有参数
    const criteria = {
        method: settingsStore.settings.rebalance_method,
        top_n: settingsStore.settings.rebalance_top_n,
        min_volume_usd: settingsStore.settings.rebalance_min_volume_usd,
        abs_momentum_days: settingsStore.settings.rebalance_abs_momentum_days,
        rel_strength_days: settingsStore.settings.rebalance_rel_strength_days,
        foam_days: settingsStore.settings.rebalance_foam_days,
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
        // 关键：带上用户手动修改的比例
        manual_target_ratio_perc: manualRatio.value
    };
    const response = await apiClient.post('/api/rebalance/plan', criteria)
    // 更新 UI store 中的计划，界面会自动响应变化
    uiStore.rebalancePlan = response.data
  } catch (error: any) {
     const errorMsg = error.response?.data?.detail || error.message;
     uiStore.logStore.addLog({
        message: `重新计算计划失败: ${errorMsg}`,
        level: 'error',
        timestamp: new Date().toLocaleTimeString(),
      })
  } finally {
    isRecalculating.value = false
  }
}, 500) // 500毫秒的延迟，用户停止拖动后才会触发

// 监听滑块值的变化，并调用防抖函数
watch(manualRatio, (newValue, oldValue) => {
  // 仅在值真正改变时才触发，避免初始化时就调用
  if (newValue !== oldValue) {
    debouncedRecalculatePlan()
  }
})
// --- 修改结束 ---

const close = () => {
  uiStore.showRebalanceDialog = false
}

const applyList = () => {
  if (!uiStore.rebalancePlan || !settingsStore.settings) return
  const openSymbols = new Set(uiStore.rebalancePlan.positions_to_open.map((p) => p.symbol))
  const symbolsToKeep = new Set(
    uiStore.rebalancePlan.positions_to_close
      .filter((p) => p.close_ratio_perc < 100)
      .map((p) => p.symbol),
  )
  const newShortList = Array.from(new Set([...openSymbols, ...symbolsToKeep])).sort()
  settingsStore.settings.short_coin_list = newShortList
  uiStore.logStore.addLog({
    message: `空头币种列表已更新为 ${newShortList.length} 个币种并自动保存。`,
    level: 'success',
    timestamp: new Date().toLocaleTimeString(),
  })
  close()
}

const executePlan = async () => {
  if (!uiStore.rebalancePlan || uiStore.isRunning) return

  const executionOrders = []
  for (const item of uiStore.rebalancePlan.positions_to_close) {
    executionOrders.push({
      symbol: item.symbol,
      action: 'CLOSE',
      side: 'buy',
      close_ratio: item.close_ratio_perc / 100,
    })
  }
  for (const item of uiStore.rebalancePlan.positions_to_open) {
    executionOrders.push({
      symbol: item.symbol,
      action: 'OPEN',
      side: 'sell',
      value_to_trade: item.open_value,
    })
  }

  close()

  const taskName = '执行再平衡'
  const totalTasks = executionOrders.length

  uiStore.launchTask('/api/rebalance/execute', { orders: executionOrders }, taskName, totalTasks)
}
</script>
