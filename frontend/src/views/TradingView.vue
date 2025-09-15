<!-- frontend/src/views/TradingView.vue (最终完整版) -->
<template>
  <v-container fluid>
    <v-row>
      <v-col cols="12" md="7">
        <ControlPanel
          :is-running="uiStore.isRunning"
          @start-trading="handleStartTrading"
          @sync-sltp="handleSyncSlTp"
          @generate-rebalance-plan="handleGenerateRebalancePlan"
        />
      </v-col>
      <v-col cols="12" md="5">
        <!-- 日志区占位 -->
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
import { useUiStore } from '@/stores/uiStore';
import { usePositionStore } from '@/stores/positionStore';
import ControlPanel from '@/components/ControlPanel.vue';
import apiClient from '@/services/api';
import type { UserSettings, RebalanceCriteria } from '@/models/types';

const uiStore = useUiStore();
const positionStore = usePositionStore();

const handleTaskApiCall = async (endpoint: string, payload: any, taskName: string, totalTasks: number = 1) => {
  if (uiStore.isRunning) {
    uiStore.logStore.addLog({ message: '已有任务在运行中，请稍后再试。', level: 'warning', timestamp: new Date().toLocaleTimeString() });
    return;
  }

  uiStore.logStore.addLog({ message: `[前端] 正在准备提交 '${taskName}' 任务...`, level: 'info', timestamp: new Date().toLocaleTimeString() });
  uiStore.setStatus(`正在提交: ${taskName}...`, true);
  uiStore.updateProgress({
    success_count: 0, failed_count: 0, total: totalTasks,
    task_name: taskName, is_final: false
  });

  try {
    const response = await apiClient.post(endpoint, payload);
    uiStore.logStore.addLog({ message: `[后端] ✅ 已确认接收任务: ${response.data.message}`, level: 'success', timestamp: new Date().toLocaleTimeString() });
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message;
    uiStore.logStore.addLog({ message: `[后端] ❌ 任务提交失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
    uiStore.setStatus("任务提交失败", false);
  }
};

const handleStartTrading = (plan: UserSettings) => {
  const total = (plan.enable_long_trades ? plan.long_coin_list.length : 0) +
                (plan.enable_short_trades ? plan.short_coin_list.length : 0);
  handleTaskApiCall('/api/trading/start', plan, '自动开仓', total);
};

const handleSyncSlTp = (settings: any) => {
  handleTaskApiCall('/api/trading/sync-sltp', settings, '同步SL/TP', positionStore.positions.length);
};

const handleGenerateRebalancePlan = async (criteria: RebalanceCriteria) => {
  if (uiStore.isRunning) return;
  uiStore.logStore.addLog({ message: '[前端] 正在生成再平衡计划...', level: 'info', timestamp: new Date().toLocaleTimeString() });
  try {
    const response = await apiClient.post('/api/rebalance/plan', criteria);
    uiStore.logStore.addLog({ message: '[后端] ✅ 再平衡计划已成功生成。', level: 'success', timestamp: new Date().toLocaleTimeString() });
    const planData = response.data;
    if (planData.error) {
      uiStore.logStore.addLog({ message: `计划生成逻辑错误: ${planData.error}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
    } else {
      uiStore.rebalancePlan = planData;
      uiStore.showRebalanceDialog = true;
    }
  } catch (error: any) {
     const errorMsg = error.response?.data?.detail || error.message;
    uiStore.logStore.addLog({ message: `[后端] ❌ 生成计划请求失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
  }
};

onMounted(() => {
  if (positionStore.positions.length === 0) {
    positionStore.fetchPositions();
  }
});
</script>
