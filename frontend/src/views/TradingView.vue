<!-- 文件路径: frontend/src/views/TradingView.vue (精简版) -->
<template>
  <v-container fluid>
    <v-row>
      <!-- 左侧主控制区 (7/12 宽度) -->
      <v-col cols="12" md="7">
        <!-- 只保留 ControlPanel，它是此页面的核心 -->
        <ControlPanel
          :is-running="uiStore.isRunning"
          @start-trading="handleStartTrading"
          @sync-sltp="handleSyncSlTp"
          @generate-rebalance-plan="handleGenerateRebalancePlan"
        />
      </v-col>

      <!-- 右侧日志区 (5/12 宽度) -->
      <v-col cols="12" md="5">
        <!-- LogDrawer 现在由 App.vue 控制显隐，这里不再需要直接管理它 -->
        <!-- 这个 v-col 只是为了布局占位 -->
      </v-col>
    </v-row>

    <!-- 全局组件保持不变 -->
    <RebalanceDialog />
    <ProgressBar />
    <Snackbar />

  </v-container>
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
import { useUiStore } from '@/stores/uiStore';
import { usePositionStore } from '@/stores/positionStore'; // 仍然需要 positionStore 来更新仓位
import ControlPanel from '@/components/ControlPanel.vue';
import ProgressBar from '@/components/ProgressBar.vue';
import Snackbar from '@/components/Snackbar.vue';
import RebalanceDialog from '@/components/RebalanceDialog.vue';
import apiClient from '@/services/api';
import type { TradePlan, RebalanceCriteria } from '@/models/types';

const uiStore = useUiStore();
const positionStore = usePositionStore();

// API 调用逻辑集中在此处
const handleApiCall = async (endpoint: string, payload: any, startMsg: string, successMsg: string) => {
  if (uiStore.isRunning) {
    uiStore.logStore.addLog({ message: '任务正在进行中，请勿重复操作', level: 'warning', timestamp: new Date().toLocaleTimeString() });
    return;
  }
  uiStore.logStore.addLog({ message: startMsg, level: 'info', timestamp: new Date().toLocaleTimeString() });
  try {
    await apiClient.post(endpoint, payload);
    // 成功后不需要显示 snackbar, 因为 websocket 会更新状态
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message;
    uiStore.logStore.addLog({ message: `${successMsg}失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
  }
};

const handleStartTrading = (plan: TradePlan) => {
  handleApiCall('/api/trading/start', plan, '正在提交开仓任务...', '开仓任务启动');
};

const handleSyncSlTp = (settings: any) => {
  handleApiCall('/api/trading/sync-sltp', settings, '正在提交SL/TP校准任务...', 'SL/TP校准任务启动');
};

const handleGenerateRebalancePlan = async (criteria: RebalanceCriteria) => {
  if (uiStore.isRunning) {
    uiStore.logStore.addLog({ message: '任务正在进行中，无法生成计划', level: 'warning', timestamp: new Date().toLocaleTimeString() });
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

// 页面加载时依然需要获取一次持仓数据，因为再平衡计划需要基于当前持仓来计算
onMounted(() => {
  if (positionStore.positions.length === 0) {
    positionStore.fetchPositions();
  }
});

</script>
