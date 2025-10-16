<!-- frontend/src/components/RebalanceDialog.vue (本地实时计算最终版) -->
<template>
  <v-dialog v-model="uiStore.showRebalanceDialog" max-width="600px" persistent>
    <v-card v-if="internalPlan">
      <v-card-title class="text-h5">
        再平衡计划 (目标比例: {{ manualRatio.toFixed(1) }}%)
      </v-card-title>
      <v-card-text>
        <!-- 手动调整滑块 -->
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
        <div>
          <div v-if="internalPlan.positions_to_close.length">
            <p class="font-weight-bold">将要平仓/减仓:</p>
            <v-list density="compact">
              <v-list-item v-for="p in internalPlan.positions_to_close" :key="p.symbol">
                {{ p.symbol }} (-${{ p.close_value.toFixed(2) }},
                {{ p.close_ratio_perc.toFixed(0) }}%)
              </v-list-item>
            </v-list>
          </div>
          <div v-if="internalPlan.positions_to_open.length" class="mt-4">
            <p class="font-weight-bold">将要开仓/加仓:</p>
            <v-list density="compact">
              <v-list-item v-for="p in internalPlan.positions_to_open" :key="p.symbol">
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
        <v-btn color="red-darken-1" variant="tonal" @click="executePlan" :disabled="uiStore.isRunning"
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
import { usePositionStore } from '@/stores/positionStore'
import type { RebalancePlan, Position } from '@/models/types'

const uiStore = useUiStore()
const settingsStore = useSettingsStore()
const positionStore = usePositionStore()

// --- 核心修改：使用内部状态来驱动UI ---
const manualRatio = ref(0)
const internalPlan = ref<RebalancePlan | null>(null)

// 纯前端的计划重新计算函数
const recalculatePlanLocally = () => {
  if (!uiStore.rebalancePlan) return

  const targetRatio = manualRatio.value / 100
  const targetCoinList = uiStore.rebalancePlan.target_coin_list
  const currentShortPositions = positionStore.shortPositions
  const currentLongValue = positionStore.longNotional

  const targetShortValue = currentLongValue * targetRatio

  // --- JS/TS 版本的 rebalance_logic.generate_rebalance_plan ---
  const currentPositionsMap = new Map(currentShortPositions.map((p) => [p.symbol, p]))
  const currentSymbols = new Set(currentPositionsMap.keys())
  const targetSymbols = new Set(targetCoinList)

  const newClosePlan: RebalancePlan['positions_to_close'] = []
  const newOpenPlanData: { [symbol: string]: number } = {}

  if (targetSymbols.size === 0) {
    for (const position of currentShortPositions) {
      newClosePlan.push({
        symbol: position.symbol,
        notional: position.notional,
        close_value: position.notional,
        close_ratio_perc: 100,
        close_ratio: 1.0,
      })
    }
  } else {
    const valuePerCoinIdeal = targetShortValue / targetSymbols.size

    for (const [symbol, position] of currentPositionsMap.entries()) {
      if (!targetSymbols.has(symbol)) {
        newClosePlan.push({
          symbol: position.symbol,
          notional: position.notional,
          close_value: position.notional,
          close_ratio_perc: 100,
          close_ratio: 1.0,
        })
      } else {
        const delta = valuePerCoinIdeal - position.notional
        if (delta < -10) {
          const closeRatio = Math.min(Math.abs(delta) / position.notional, 1.0)
          newClosePlan.push({
            symbol: position.symbol,
            notional: position.notional,
            close_value: position.notional * closeRatio,
            close_ratio_perc: closeRatio * 100,
            close_ratio: closeRatio,
          })
        } else if (delta > 10) {
          newOpenPlanData[symbol] = delta
        }
      }
    }

    const symbolsToOpenNew = [...targetSymbols].filter((s) => !currentSymbols.has(s))
    for (const symbol of symbolsToOpenNew) {
      newOpenPlanData[symbol] = valuePerCoinIdeal
    }
  }

  const newOpenPlan: RebalancePlan['positions_to_open'] = []
  if (targetCoinList.length > 0) {
      const valuePerCoinIdeal = targetShortValue / targetCoinList.length;
      for (const [symbol, value] of Object.entries(newOpenPlanData)) {
          const percentage = valuePerCoinIdeal > 0.01 ? (value / valuePerCoinIdeal) * 100 : 100;
          newOpenPlan.push({ symbol, open_value: value, percentage });
      }
  }
  // --- 计算结束 ---

  // 更新内部的、驱动UI的plan对象
  internalPlan.value = {
    target_ratio_perc: manualRatio.value,
    positions_to_close: newClosePlan,
    positions_to_open: newOpenPlan,
    target_coin_list: targetCoinList,
  }
}

// 监听 uiStore.rebalancePlan，这是从后端来的初始计划
watch(
  () => uiStore.rebalancePlan,
  (newPlan) => {
    // 当初始计划到达时，用它来设置我们的本地状态
    if (newPlan) {
      manualRatio.value = newPlan.target_ratio_perc
      internalPlan.value = newPlan
    } else {
      internalPlan.value = null
    }
  },
)

// 监听手动调整的比例，并触发本地重新计算
watch(manualRatio, () => {
  // 增加一个保护，确保只在dialog打开且有初始计划时才重新计算
  if (uiStore.showRebalanceDialog && uiStore.rebalancePlan) {
    recalculatePlanLocally()
  }
})

const close = () => {
  uiStore.showRebalanceDialog = false
}

const applyList = () => {
  if (!internalPlan.value || !settingsStore.settings) return
  // 使用 internalPlan.value 来获取最新的币种列表
  const openSymbols = new Set(internalPlan.value.positions_to_open.map((p) => p.symbol))
  const symbolsToKeep = new Set(
    internalPlan.value.positions_to_close
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
  if (!internalPlan.value || uiStore.isRunning) return

  // 使用最终确认的 internalPlan.value 来构建执行命令
  const executionOrders = []
  for (const item of internalPlan.value.positions_to_close) {
    executionOrders.push({
      symbol: item.symbol,
      action: 'CLOSE',
      side: 'buy',
      close_ratio: item.close_ratio_perc / 100,
    })
  }
  for (const item of internalPlan.value.positions_to_open) {
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
