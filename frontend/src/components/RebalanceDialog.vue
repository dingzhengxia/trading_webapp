<!-- frontend/src/components/RebalanceDialog.vue -->
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
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="blue-darken-1" variant="text" @click="uiStore.showRebalanceDialog = false">取消</v-btn>
        <v-btn color="red-darken-1" variant="tonal" @click="executePlan">确认执行</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useUiStore } from '@/stores/uiStore';

const uiStore = useUiStore();

const executePlan = () => {
  uiStore.logStore.addLog({ message: "!!! 用户已确认执行再平衡 !!!", level: "warning", timestamp: new Date().toLocaleTimeString() });
  // TODO: 在这里调用一个API来真正执行计划
  // await api.post('/api/rebalance/execute', uiStore.rebalancePlan);
  uiStore.showRebalanceDialog = false;
};
</script>
