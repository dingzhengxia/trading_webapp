<!-- frontend/src/components/RebalanceDialog.vue (支持比例微调) -->
<template>
  <v-dialog v-model="uiStore.showRebalanceDialog" max-width="600px" persistent>
    <v-card v-if="originalPlan">
      <v-card-title class="text-h5 d-flex align-center">
        <span>再平衡计划</span>
        <v-spacer></v-spacer>
        <!-- 核心修改：可编辑的目标比例输入框 -->
        <div class="d-flex align-center" style="width: 220px">
          <span class="text-subtitle-2 mr-2">目标空头比例:</span>
          <v-text-field
            v-model.number="editableTargetRatioPerc"
            variant="outlined"
            density="compact"
            hide-details
            suffix="%"
            type="number"
            style="width: 100px"
          ></v-text-field>
        </div>
      </v-card-title>
      <v-card-text>
        <div class="text-caption text-center mb-4">
            目标空头总价值: ${{ finalTargetShortValue.toFixed(2) }}
        </div>

        <div v-if="recalculatedPlan.positions_to_close.length">
          <p class="font-weight-bold">将要平仓/减仓:</p>
          <v-list density="compact">
            <v-list-item v-for="p in recalculatedPlan.positions_to_close" :key="p.symbol">
              {{ p.symbol }} (-${{ p.close_value.toFixed(2) }},
              {{ p.close_ratio_perc.toFixed(0) }}%)
            </v-list-item>
          </v-list>
        </div>
        <div v-if="recalculatedPlan.positions_to_open.length" class="mt-4">
          <p class="font-weight-bold">将要开仓/加仓:</p>
          <v-list density="compact">
            <v-list-item v-for="p in recalculatedPlan.positions_to_open" :key="p.symbol">
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
        <v-btn color="primary" variant="text" @click="applyList">应用列表到配置</v-btn>
        <v-btn
          color="red-darken-1"
          variant="tonal"
          @click="executePlan"
          :disabled="uiStore.isRunning"
          >确认执行</v-btn
        >
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useUiStore } from '@/stores/uiStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { usePositionStore } from '@/stores/positionStore'
import apiClient from '@/services/api'
import type { RebalancePlan } from '@/models/types'

const uiStore = useUiStore()
const settingsStore = useSettingsStore()
const positionStore = usePositionStore()

// --- 核心修改：引入新状态和计算逻辑 ---
const originalPlan = ref<RebalancePlan | null>(null)
const editableTargetRatioPerc = ref(0)

// 监听对话框打开，初始化数据
watch(() => uiStore.rebalancePlan, (newPlan) => {
    if (newPlan) {
        originalPlan.value = JSON.parse(JSON.stringify(newPlan)); // 深拷贝原始计划
        editableTargetRatioPerc.value = newPlan.target_ratio_perc;
    }
}, { immediate: true });

// 计算最终的目标空头价值
const finalTargetShortValue = computed(() => {
    const longValue = positionStore.longNotional
    const ratio = editableTargetRatioPerc.value / 100
    return longValue * ratio
})

// 根据用户修改的比例，实时重新计算交易计划
const recalculatedPlan = computed(() => {
    if (!originalPlan.value) {
        return { positions_to_close: [], positions_to_open: [] };
    }

    const currentShortPositions = positionStore.shortPositions;
    const targetCoinList = originalPlan.value.positions_to_open.map(p => p.symbol)
        .concat(originalPlan.value.positions_to_close.filter(p => p.close_ratio < 1).map(p => p.symbol));

    // 调用一个本地的 generate_rebalance_plan 逻辑
    return generateRebalancePlanLogic(currentShortPositions, Array.from(new Set(targetCoinList)), finalTargetShortValue.value);
})

// 这是 rebalance_logic.py 中 generate_rebalance_plan 的 TypeScript 实现
function generateRebalancePlanLogic(currentShortPositions: any[], targetCoinList: string[], targetShortValue: number) {
    const currentPositionsMap = new Map(currentShortPositions.map(p => [p.symbol, p]));
    const currentSymbols = new Set(currentPositionsMap.keys());
    const targetSymbols = new Set(targetCoinList);

    const close_plan = [];
    const open_plan = new Map<string, number>();

    if (targetSymbols.size === 0) {
        for (const position of currentShortPositions) {
            close_plan.push({
                symbol: position.symbol,
                notional: position.notional,
                close_value: position.notional,
                close_ratio_perc: 100,
                close_ratio: 1.0
            });
        }
        return { positions_to_close: close_plan, positions_to_open: [] };
    }

    const valuePerCoinIdeal = targetShortValue / targetSymbols.size;

    for (const [symbol, position] of currentPositionsMap.entries()) {
        if (!targetSymbols.has(symbol)) {
            close_plan.push({
                symbol: position.symbol,
                notional: position.notional,
                close_value: position.notional,
                close_ratio_perc: 100,
                close_ratio: 1.0
            });
        } else {
            const delta = valuePerCoinIdeal - position.notional;
            if (delta < -10) { // 需要减仓
                const closeRatio = Math.min(Math.abs(delta) / position.notional, 1.0);
                close_plan.push({
                    symbol: position.symbol,
                    notional: position.notional,
                    close_value: position.notional * closeRatio,
                    close_ratio_perc: closeRatio * 100,
                    close_ratio: closeRatio
                });
            } else if (delta > 10) { // 需要加仓
                open_plan.set(symbol, delta);
            }
        }
    }

    const symbolsToOpenNew = [...targetSymbols].filter(s => !currentSymbols.has(s));
    for (const symbol of symbolsToOpenNew) {
        open_plan.set(symbol, valuePerCoinIdeal);
    }

    const open_plan_formatted = [];
    for (const [symbol, value] of open_plan.entries()) {
        const percentage = valuePerCoinIdeal > 0.01 ? (value / valuePerCoinIdeal) * 100 : 100;
        open_plan_formatted.push({
            symbol: symbol,
            open_value: value,
            percentage: percentage
        });
    }

    return { positions_to_close: close_plan, positions_to_open: open_plan_formatted };
}
// --- 修改结束 ---


const close = () => {
  uiStore.showRebalanceDialog = false
  originalPlan.value = null; // 清理状态
}

const applyList = () => {
  if (!recalculatedPlan.value || !settingsStore.settings) return
  const openSymbols = new Set(recalculatedPlan.value.positions_to_open.map((p) => p.symbol))
  const symbolsToKeep = new Set(
    recalculatedPlan.value.positions_to_close
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
  if (!recalculatedPlan.value || uiStore.isRunning) return

  const executionOrders = []
  for (const item of recalculatedPlan.value.positions_to_close) {
    if (item.close_value > 1) { // 只有平仓价值大于1才执行
        executionOrders.push({
            symbol: item.symbol,
            action: 'CLOSE',
            side: 'buy',
            close_ratio: item.close_ratio,
        })
    }
  }
  for (const item of recalculatedPlan.value.positions_to_open) {
    if (item.open_value > 1) { // 只有开仓价值大于1才执行
        executionOrders.push({
            symbol: item.symbol,
            action: 'OPEN',
            side: 'sell',
            value_to_trade: item.open_value,
        })
    }
  }

  close()

  const taskName = '执行再平衡'
  const totalTasks = executionOrders.length

  if (totalTasks === 0) {
      uiStore.logStore.addLog({
          message: `[前端] 再平衡计划无需执行任何操作。`,
          level: 'info',
          timestamp: new Date().toLocaleTimeString(),
      })
      return;
  }

  uiStore.launchTask('/api/rebalance/execute', { orders: executionOrders }, taskName, totalTasks);
}
</script>
