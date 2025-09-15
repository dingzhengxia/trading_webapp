<!-- frontend/src/views/TradingView.vue (最终确认版) -->
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
import type { UserSettings, RebalanceCriteria, SyncSltpRequest } from '@/models/types';

const uiStore = useUiStore();
const positionStore = usePositionStore();

const fireAndForgetApiCall = (endpoint: string, payload: any, taskName: string, totalTasks: number = 1) => {
  if (uiStore.isRunning) {
    uiStore.logStore.addLog({ message: '已有任务在运行中，请稍后再试。', level: 'warning', timestamp: new Date().toLocaleTimeString() });
    return;
  }

  const requestId = `req-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  const payloadWithId = { ...payload, request_id: requestId };

  uiStore.setStatus(`正在提交: ${taskName}...`, true);
  uiStore.updateProgress({
    success_count: 0, failed_count: 0, total: totalTasks,
    task_name: taskName, is_final: false
  });
  uiStore.logStore.addLog({ message: `[前端] 已发送 '${taskName}' 启动指令 (ID: ${requestId})。`, level: 'info', timestamp: new Date().toLocaleTimeString() });

  apiClient.post(endpoint, payloadWithId)
    .then(response => {
      console.log('API call successful:', response.data.message);
      // 后端已接收，日志由后端 _start_task 发送
    })
    .catch(error => {
      const errorMsg = error.response?.data?.detail || error.message;
      uiStore.logStore.addLog({ message: `[前端] 任务提交失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
      uiStore.setStatus("任务提交失败", false);
    });
};

const handleStartTrading = (plan: UserSettings) => {
  const total = (plan.enable_long_trades ? plan.long_coin_list.length : 0) +
                (plan.enable_short_trades ? plan.short_coin_list.length : 0);
  fireAndForgetApiCall('/api/trading/start', plan, '自动开仓', total);
};

const handleSyncSlTp = (settings: UserSettings) => {
  const payload: Partial<SyncSltpRequest> = {
      enable_long_sl_tp: settings.enable_long_sl_tp,
      long_stop_loss_percentage: settings.long_stop_loss_percentage,
      long_take_profit_percentage: settings.long_take_profit_percentage,
      enable_short_sl_tp: settings.enable_short_sl_tp,
      short_stop_loss_percentage: settings.short_stop_loss_percentage,
      short_take_profit_percentage: settings.short_take_profit_percentage,
      leverage: settings.leverage
  };
  fireAndForgetApiCall('/api/trading/sync-sltp', payload, '同步SL/TP', positionStore.positions.length);
};

const handleGenerateRebalancePlan = async (criteria: RebalanceCriteria) => {
  if (uiStore.isRunning) return;
  uiStore.logStore.addLog({ message: '[前端] 正在生成再平衡计划...', level: 'info', timestamp: new Date().toLocaleTimeString() });
  try {
    const response = await apiClient.post('/api/rebalance/plan', criteria);
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
