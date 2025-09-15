<!-- frontend/src/components/RebalanceDialog.vue (完整代码) -->
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
        <v-btn color="blue-darken-1" variant="text" @click="close">取消</v-btn>
        <v-btn color="primary" variant="text" @click="applyList">应用列表到配置</v-btn>
        <v-btn color="red-darken-1" variant="tonal" @click="executePlan">确认执行</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useUiStore } from '@/stores/uiStore';
import { useSettingsStore } from '@/stores/settingsStore';
import api from '@/services/api';

const uiStore = useUiStore();
const settingsStore = useSettingsStore();

const close = () => {
  uiStore.showRebalanceDialog = false;
};

const applyList = () => {
  if (!uiStore.rebalancePlan || !settingsStore.settings) return;

  const openSymbols = new Set(uiStore.rebalancePlan.positions_to_open.map(p => p.symbol));
  const symbolsToKeep = new Set(
    uiStore.rebalancePlan.positions_to_close
      .filter(p => p.close_ratio_perc < 100)
      .map(p => p.symbol)
  );
  const newShortList = Array.from(new Set([...openSymbols, ...symbolsToKeep])).sort();

  settingsStore.settings.short_coin_list = newShortList;

  uiStore.logStore.addLog({
    message: `空头币种列表已更新为 ${newShortList.length} 个币种并自动保存。`,
    level: 'success',
    timestamp: new Date().toLocaleTimeString()
  });
  close();
};

const executePlan = async () => {
  if (!uiStore.rebalancePlan) return;

  const executionOrders = [];
  for (const item of uiStore.rebalancePlan.positions_to_close) {
    executionOrders.push({
      symbol: item.symbol,
      action: 'CLOSE',
      side: 'buy',
      close_ratio: item.close_ratio_perc / 100,
    });
  }
  for (const item of uiStore.rebalancePlan.positions_to_open) {
    executionOrders.push({
      symbol: item.symbol,
      action: 'OPEN',
      side: 'sell',
      value_to_trade: item.open_value,
    });
  }

  // 立即关闭弹窗并更新UI
  close();
  uiStore.setStatus("正在提交再平衡任务...", true);
  uiStore.updateProgress({
    success_count: 0,
    failed_count: 0,
    total: executionOrders.length,
    task_name: '执行再平衡',
    is_final: false
  });

  // 在后台发送API请求
  try {
    await api.post('/api/rebalance/execute', { orders: executionOrders });
  } catch (e: any) {
    const errorMsg = e.response?.data?.detail || e.message;
    uiStore.logStore.addLog({ message: `提交再平衡计划失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
    uiStore.setStatus("任务启动失败", false);
  }
};
</script>
