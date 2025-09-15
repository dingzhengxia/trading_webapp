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

/**
 * 统一处理启动后台任务的API调用
 * @param endpoint API端点
 * @param payload 请求载荷
 * @param taskName 任务的显示名称
 * @param totalTasks 预估的任务总数
 */
const handleTaskApiCall = async (endpoint: string, payload: any, taskName: string, totalTasks: number = 1) => {
  if (uiStore.isRunning) {
    uiStore.logStore.addLog({ message: '已有任务在运行中，请稍后再试。', level: 'warning', timestamp: new Date().toLocaleTimeString() });
    return;
  }

  // 1. 立即更新UI，进入加载状态
  uiStore.setStatus(`正在提交: ${taskName}...`, true);
  uiStore.updateProgress({
    success_count: 0, failed_count: 0, total: totalTasks,
    task_name: taskName, is_final: false
  });

  // 2. 发送API请求
  try {
    const response = await apiClient.post(endpoint, payload);
    // 只有当API请求成功返回200 OK时，才记录“已开始”的日志
    // 此时，UI的控制权正式交给后端的WebSocket
    uiStore.logStore.addLog({ message: response.data.message || `${taskName} 已成功开始执行。`, level: 'info', timestamp: new Date().toLocaleTimeString() });
  } catch (error: any) {
    // 如果API请求本身就失败了（例如400, 500错误或网络问题）
    const errorMsg = error.response?.data?.detail || error.message;
    uiStore.logStore.addLog({ message: `任务启动失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
    // 立即重置UI状态，让用户可以重新尝试
    uiStore.setStatus("任务启动失败", false);
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
  if (uiStore.isRunning) {
    uiStore.logStore.addLog({ message: '已有任务在运行中，无法生成计划', level: 'warning', timestamp: new Date().toLocaleTimeString() });
    return;
  }
  uiStore.logStore.addLog({ message: '正在生成再平衡计划...', level: 'info', timestamp: new Date().toLocaleTimeString() });
  try {
    const response = await apiClient.post('/api/rebalance/plan', criteria);
    const planData = response.data;
    if (planData.error) {
      uiStore.logStore.addLog({ message: `生成计划失败: ${planData.error}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
    } else {
      uiStore.rebalancePlan = planData;
      uiStore.showRebalanceDialog = true;
    }
  } catch (error: any) {
     const errorMsg = error.response?.data?.detail || error.message;
    uiStore.logStore.addLog({ message: `生成计划时发生错误: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
  }
};

onMounted(() => {
  if (positionStore.positions.length === 0) {
    positionStore.fetchPositions();
  }
});
</script>
