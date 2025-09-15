<!-- frontend/src/views/TradingView.vue (最终页面悬浮版) -->
<template>
  <!-- 核心修改：增加一个占位 div，并为其设置 padding-bottom -->
  <div style="padding-bottom: 80px;">
    <v-container fluid>
      <v-row>
        <v-col cols="12">
          <!-- ControlPanel 现在不再需要 props 和 emits -->
          <ControlPanel />
        </v-col>
      </v-row>
    </v-container>
  </div>

  <!-- 核心修改：创建一个新的、固定在底部的 v-footer 作为操作栏 -->
  <!-- 注意：这里没有 'app' 属性，所以它只在此页面生效 -->
  <v-footer
    style="position: fixed; bottom: 0; left: 0; right: 0; z-index: 1000; border-top: 1px solid rgba(255, 255, 255, 0.12);"
    class="pa-0"
  >
    <v-card flat tile class="d-flex align-center px-4 w-100" height="64px">
        <v-btn color="info" variant="tonal" @click="handleSyncSlTp" :disabled="uiStore.isRunning">
          校准 SL/TP
        </v-btn>
        <v-spacer></v-spacer>
        <v-btn
          color="success"
          variant="tonal"
          prepend-icon="mdi-play"
          @click="handleStartTrading"
          :loading="uiStore.isRunning"
          :disabled="uiStore.isRunning"
        >
          开始开仓
        </v-btn>
    </v-card>
  </v-footer>
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
import { useUiStore } from '@/stores/uiStore';
import { usePositionStore } from '@/stores/positionStore';
import { useSettingsStore } from '@/stores/settingsStore'; // 导入 settings store
import ControlPanel from '@/components/ControlPanel.vue';
import apiClient from '@/services/api';
import type { UserSettings, RebalanceCriteria, SyncSltpRequest } from '@/models/types';

const uiStore = useUiStore();
const positionStore = usePositionStore();
const settingsStore = useSettingsStore(); // 获取 settings store 实例

// 这个统一的API调用函数现在也放在这里
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
    .then(response => { console.log('API call successful:', response.data.message); })
    .catch(error => {
      const errorMsg = error.response?.data?.detail || error.message;
      uiStore.logStore.addLog({ message: `[前端] 任务提交失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
      uiStore.setStatus("任务提交失败", false);
    });
};

const handleStartTrading = () => {
  if (settingsStore.settings) {
    const plan = settingsStore.settings;
    const total = (plan.enable_long_trades ? plan.long_coin_list.length : 0) +
                  (plan.enable_short_trades ? plan.short_coin_list.length : 0);
    fireAndForgetApiCall('/api/trading/start', plan, '自动开仓', total);
  }
};

const handleSyncSlTp = () => {
  if (settingsStore.settings) {
    const settings = settingsStore.settings;
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
  }
};

// handleGenerateRebalancePlan 不再需要，因为它在 ControlPanel 内部
// onMounted 保持不变
onMounted(() => {
  if (positionStore.positions.length === 0) {
    positionStore.fetchPositions();
  }
});
</script>
