<!-- frontend/src/components/RebalanceDialog.vue -->
<template>
  <v-dialog v-model="uiStore.showRebalanceDialog" max-width="800px" persistent>
    <v-card v-if="uiStore.rebalancePlan">
      <v-card-title class="text-h5">
        再平衡计划
        <v-text-field
          v-model.number="editableTargetRatio"
          type="number"
          step="0.1"
          suffix="%"
          density="compact"
          variant="outlined"
          hide-details
          style="width: 120px; display: inline-block; margin-left: 10px;"
          @update:model-value="onTargetRatioChange"
        ></v-text-field>
      </v-card-title>
      <v-card-text>
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
        <v-alert type="warning" variant="tonal" class="mt-4 text-caption">
          警告：此操作将自动执行交易！
        </v-alert>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="blue-darken-1" variant="text" @click="close">取消</v-btn>
        <v-btn
          color="red-darken-1"
          variant="tonal"
          @click="executePlan"
          :disabled="uiStore.isRunning"
        >
          执行计划
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useUiStore } from '@/stores/uiStore'
import apiClient from '@/services/api'

const uiStore = useUiStore()
const editableTargetRatio = ref(uiStore.rebalancePlan?.target_ratio_perc || 50)

// 监听 rebalancePlan 的变化，同步 editableTargetRatio
watch(
  () => uiStore.rebalancePlan,
  (newPlan) => {
    if (newPlan) {
      editableTargetRatio.value = newPlan.target_ratio_perc
    }
  },
  { immediate: true }
)

const onTargetRatioChange = (newValue: number | undefined) => {
  if (!uiStore.rebalancePlan || newValue === undefined) return
  // 只更新显示的目标比例，不改变实际的开仓/平仓计划
  uiStore.rebalancePlan.target_ratio_perc = newValue
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

  uiStore.logStore.addLog({
    message: `[前端] 正在准备提交 '${taskName}' 任务...`,
    level: 'info',
    timestamp: new Date().toLocaleTimeString(),
  })
  uiStore.setStatus(`正在提交: ${taskName}...`, true)
  uiStore.updateProgress({
    success_count: 0,
    failed_count: 0,
    total: totalTasks,
    task_name: taskName,
    is_final: false,
  })

  try {
    const response = await apiClient.post('/api/rebalance/execute', { orders: executionOrders })
    uiStore.logStore.addLog({
      message: `[后端] ✅ 已确认接收任务: ${response.data.message}`,
      level: 'success',
      timestamp: new Date().toLocaleTimeString(),
    })
  } catch (e: any) {
    const errorMsg = e.response?.data?.detail || e.message
    uiStore.logStore.addLog({
      message: `[后端] ❌ 提交再平衡计划失败: ${errorMsg}`,
      level: 'error',
      timestamp: new Date().toLocaleTimeString(),
    })
    uiStore.setStatus('任务启动失败', false)
  }
}

const close = () => {
  uiStore.showRebalanceDialog = false
}
</script>
