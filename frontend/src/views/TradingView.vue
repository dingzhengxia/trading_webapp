<!-- frontend/src/views/TradingView.vue (最终优化版) -->
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


// --- 核心修改：重构 API 调用逻辑 ---

const handleStartTrading = async (plan: UserSettings) => {
  if (uiStore.isRunning) return;

  // 1. 立即更新UI状态
  uiStore.setStatus("正在提交开仓任务...", true);
  const total = (plan.enable_long_trades ? plan.long_coin_list.length : 0) +
                (plan.enable_short_trades ? plan.short_coin_list.length : 0);
  uiStore.updateProgress({
    success_count: 0,
    failed_count: 0,
    total: total,
    task_name: '自动开仓',
    is_final: false
  });

  // 2. 然后再发送API请求
  try {
    await apiClient.post('/api/trading/start', plan);
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message;
    uiStore.logStore.addLog({ message: `开仓任务启动失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
    // 如果API调用本身就失败了，则重置状态
    uiStore.setStatus("任务启动失败", false);
  }
};

const handleSyncSlTp = async (settings: any) => {
  if (uiStore.isRunning) return;

  // 1. 立即更新UI状态 (预估总数)
  uiStore.setStatus("正在提交SL/TP校准...", true);
  uiStore.updateProgress({
    success_count: 0,
    failed_count: 0,
    total: positionStore.positions.length, // 使用当前持仓数作为预估总数
    task_name: '同步SL/TP',
    is_final: false
  });

  // 2. 然后再发送API请求
  try {
    await apiClient.post('/api/trading/sync-sltp', settings);
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message;
    uiStore.logStore.addLog({ message: `SL/TP校准任务启动失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
    uiStore.setStatus("任务启动失败", false);
  }
};

const handleGenerateRebalancePlan = async (criteria: RebalanceCriteria) => {
  if (uiStore.isRunning) return;
  // 对于快速操作，可以不显示全局进度条，只记录日志
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
