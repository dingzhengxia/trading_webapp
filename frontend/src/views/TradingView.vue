<!-- frontend/src/views/TradingView.vue (最终修复版) -->
<template>
  <div :style="{ paddingBottom: $vuetify.display.smAndDown ? '128px' : '80px' }">
    <v-container fluid>
      <v-row>
        <v-col cols="12">
          <ControlPanel @generate-rebalance-plan="handleGenerateRebalancePlan" />
        </v-col>
      </v-row>
    </v-container>
  </div>

  <v-footer
    style="position: fixed; bottom: 0; left: 0; right: 0; z-index: 1000; border-top: 1px solid rgba(255, 255, 255, 0.12);"
    class="pa-0"
    :style="{ bottom: $vuetify.display.smAndDown ? '56px' : '0px' }"
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
import { useSettingsStore } from '@/stores/settingsStore';
import ControlPanel from '@/components/ControlPanel.vue';
import apiClient from '@/services/api';
// --- 核心修改在这里：移除了不存在的 SyncSltpRequest 类型 ---
import type { UserSettings, RebalanceCriteria } from '@/models/types';
// --- 修改结束 ---

const uiStore = useUiStore();
const positionStore = usePositionStore();
const settingsStore = useSettingsStore();

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
    // --- 核心修改在这里：直接传递完整的 settings 对象 ---
    // 后端 /api/trading/sync-sltp 端点被定义为接收一个通用字典 (dict)
    // 所以我们可以安全地传递整个 settings 对象
    fireAndForgetApiCall('/api/trading/sync-sltp', settingsStore.settings, '同步SL/TP', positionStore.positions.length);
    // --- 修改结束 ---
  }
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
