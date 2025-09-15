<!-- frontend/src/views/TradingView.vue (最终修复版) -->
<template>
  <div :style="{ paddingBottom: $vuetify.display.smAndDown ? '128px' : '80px' }">
    <v-container fluid>
      <v-row>
        <v-col cols="12">
          <ControlPanel
            v-model="activeTab"
            @generate-rebalance-plan="handleGenerateRebalancePlan"
          />
        </v-col>
      </v-row>
    </v-container>
  </div>

  <v-footer
    style="position: fixed; bottom: 0; right: 0; z-index: 1000; border-top: 1px solid rgba(255, 255, 255, 0.12);"
    class="pa-0"
    :style="footerStyle"
  >
    <v-card flat tile class="d-flex align-center px-4 w-100" height="64px">
      <template v-if="activeTab === 'general'">
        <v-btn color="info" variant="tonal" @click="handleSyncSlTp" :disabled="uiStore.isRunning" class="mr-3">
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
      </template>

      <template v-if="activeTab === 'rebalance'">
        <v-spacer></v-spacer>
        <v-btn
          color="primary"
          variant="tonal"
          @click="onGenerateRebalancePlan"
          :loading="isGeneratingPlan"
          :disabled="uiStore.isRunning || isGeneratingPlan"
        >
          生成再平衡计划
        </v-btn>
      </template>
    </v-card>
  </v-footer>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useDisplay } from 'vuetify'; // <-- 只导入 useDisplay
import { useUiStore } from '@/stores/uiStore';
import { usePositionStore } from '@/stores/positionStore';
import { useSettingsStore } from '@/stores/settingsStore';
import ControlPanel from '@/components/ControlPanel.vue';
import apiClient from '@/services/api';
import type { UserSettings, RebalanceCriteria } from '@/models/types';

const uiStore = useUiStore();
const positionStore = usePositionStore();
const settingsStore = useSettingsStore();

// --- 核心修改在这里：正确使用 Vuetify 的 useDisplay ---
const vuetifyDisplay = useDisplay();

const footerStyle = computed(() => {
  const styles: { bottom: string, left: string } = {
    bottom: vuetifyDisplay.smAndDown.value ? '56px' : '0px',
    left: '0px' // 默认 left 为 0
  };

  // 安全地访问 application 属性
  if (vuetifyDisplay.mdAndUp.value && vuetifyDisplay.application) {
    styles.left = `${vuetifyDisplay.application.left}px`;
  }

  return styles;
});
// --- 修改结束 ---

const activeTab = ref('general');
const isGeneratingPlan = ref(false);

const fireAndForgetApiCall = (endpoint: string, payload: any, taskName: string, totalTasks: number = 1) => {
  if (uiStore.isRunning) return;
  const requestId = `req-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  const payloadWithId = { ...payload, request_id: requestId };
  uiStore.setStatus(`正在提交: ${taskName}...`, true);
  uiStore.updateProgress({ success_count: 0, failed_count: 0, total: totalTasks, task_name: taskName, is_final: false });
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
    fireAndForgetApiCall('/api/trading/start', settingsStore.settings, '自动开仓',
      (settingsStore.settings.enable_long_trades ? settingsStore.settings.long_coin_list.length : 0) +
      (settingsStore.settings.enable_short_trades ? settingsStore.settings.short_coin_list.length : 0)
    );
  }
};

const handleSyncSlTp = () => {
  if (settingsStore.settings) {
    fireAndForgetApiCall('/api/trading/sync-sltp', settingsStore.settings, '同步SL/TP', positionStore.positions.length);
  }
};

const onGenerateRebalancePlan = () => {
  if (settingsStore.settings) {
    const criteria = {
      method: settingsStore.settings.rebalance_method,
      top_n: settingsStore.settings.rebalance_top_n,
      min_volume_usd: settingsStore.settings.rebalance_min_volume_usd,
      abs_momentum_days: settingsStore.settings.rebalance_abs_momentum_days,
      rel_strength_days: settingsStore.settings.rebalance_rel_strength_days,
      foam_days: settingsStore.settings.rebalance_foam_days,
    };
    handleGenerateRebalancePlan(criteria);
  }
};

const handleGenerateRebalancePlan = async (criteria: RebalanceCriteria) => {
  if (uiStore.isRunning || isGeneratingPlan.value) return;
  isGeneratingPlan.value = true;
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
  } finally {
    isGeneratingPlan.value = false;
  }
};

onMounted(() => {
  if (positionStore.positions.length === 0) {
    positionStore.fetchPositions();
  }
});
</script>
