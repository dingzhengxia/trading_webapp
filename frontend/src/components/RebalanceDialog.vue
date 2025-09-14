<template>
  <v-dialog v-model="uiStore.showRebalanceDialog" max-width="600px" persistent>
    <v-card v-if="uiStore.rebalancePlan">
      <v-card-title class="text-h5">
        再平衡计划 (目标比例: {{ uiStore.rebalancePlan.target_ratio_perc.toFixed(1) }}%)
      </v-card-title>
      <v-card-text>
        <div v-if="uiStore.rebalancePlan.positions_to_close.length">
          <p class="font-weight-bold">将要平仓/减仓:</p>
          <v-list density="compact">
            <v-list-item v-for="p in uiStore.rebalancePlan.positions_to_close" :key="p.symbol">
              {{ p.symbol }} (-${{ p.close_value.toFixed(2) }}, {{ p.close_ratio_perc.toFixed(0) }}%)
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
        <v-btn color="blue-darken-1" variant="text" @click="uiStore.showRebalanceDialog = false">取消</v-btn>
        <v-btn color="red-darken-1" variant="tonal" @click="executePlan" :loading="isExecuting">确认执行</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useUiStore } from '@/stores/uiStore';
import api from '@/services/api';

const uiStore = useUiStore();
const isExecuting = ref(false);

const executePlan = async () => {
  if (!uiStore.rebalancePlan) return;

  isExecuting.value = true;

  const executionOrders = [];

  // 格式化平仓订单
  for (const item of uiStore.rebalancePlan.positions_to_close) {
    executionOrders.push({
      symbol: item.symbol,
      action: 'CLOSE',
      side: 'buy', // 假设再平衡只针对空头
      close_ratio: item.close_ratio_perc / 100,
    });
  }

  // 格式化开仓订单
  for (const item of uiStore.rebalancePlan.positions_to_open) {
    executionOrders.push({
      symbol: item.symbol,
      action: 'OPEN',
      side: 'sell', // 假设再平衡只针对空头
      value_to_trade: item.open_value,
    });
  }

  try {
    uiStore.logStore.addLog({ message: "正在提交再平衡执行计划...", level: 'info', timestamp: new Date().toLocaleTimeString() });
    await api.post('/api/rebalance/execute', { orders: executionOrders });
  } catch (e: any) {
    const errorMsg = e.response?.data?.detail || e.message;
    uiStore.logStore.addLog({ message: `提交执行计划失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
  } finally {
    isExecuting.value = false;
    uiStore.showRebalanceDialog = false;
  }
};
</script>
