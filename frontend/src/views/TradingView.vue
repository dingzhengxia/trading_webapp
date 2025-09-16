<!-- frontend/src/views/TradingView.vue -->
<template>
  <!-- 占位div，为悬浮的footer和手机底部导航留出空间 -->
  <div :style="{ paddingBottom: $vuetify.display.smAndDown ? '128px' : '80px' }">
    <v-container fluid>
      <v-row>
        <v-col cols="12">
          <!-- 使用 v-model 将本页面的 activeTab 与子组件的 tab 状态双向绑定 -->
          <ControlPanel
            v-model="activeTab"
            @generate-rebalance-plan="handleGenerateRebalancePlan"
          />
        </v-col>
      </v-row>
    </v-container>
  </div>

  <!-- 固定在页面底部的悬浮操作栏 -->
  <v-footer
    style="position: fixed; bottom: 0; right: 0; z-index: 1000; border-top: 1px solid rgba(255, 255, 255, 0.12);"
    class="pa-0"
    :style="footerStyle"
  >
    <v-card flat tile class="d-flex align-center px-4 w-100" height="64px">
      <v-spacer></v-spacer>

      <!-- 当 tab 是 'general' 时显示 -->
      <template v-if="activeTab === 'general'">
        <v-btn color="info" variant="tonal" @click="handleSyncSlTp" :disabled="uiStore.isRunning" class="mr-3">
          校准 SL/TP
        </v-btn>
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

      <!-- 当 tab 是 'rebalance' 时显示 -->
      <template v-if="activeTab === 'rebalance'">
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
import { ref, computed, onMounted } from 'vue';
import { useDisplay } from 'vuetify';
import { useUiStore } from '@/stores/uiStore';
import { usePositionStore } from '@/stores/positionStore';
import { useSettingsStore } from '@/stores/settingsStore';
import ControlPanel from '@/components/ControlPanel.vue';
import apiClient from '@/services/api';
import type { UserSettings, RebalanceCriteria } from '@/models/types';

const uiStore = useUiStore();
const positionStore = usePositionStore();
const settingsStore = useSettingsStore();

const vuetifyDisplay = useDisplay();
const footerStyle = computed(() => {
  const styles: { bottom: string, left: string } = {
    bottom: vuetifyDisplay.smAndDown.value ? '56px' : '0px',
    left: '0px'
  };
  if (vuetifyDisplay.mdAndUp.value && vuetifyDisplay.application) {
    styles.left = `${vuetifyDisplay.application.left}px`;
  }
  return styles;
});

const activeTab = ref('general');
const isGeneratingPlan = ref(false);

// 统一的、健壮的API调用函数
const fireAndForgetApiCall = (endpoint: string, payload: any, taskName: string, totalTasks: number = 1) => {
  if (uiStore.isRunning) {
    uiStore.logStore.addLog({ message: '已有任务在运行中，请稍后再试。', level: 'warning', timestamp: new Date().toLocaleTimeString() });
    return;
  }
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
    // --- 核心修改：当开仓启用时，使用用户选择的列表 ---
    const plan = {
        ...settingsStore.settings,
        long_coin_list: settingsStore.settings.enable_long_trades ? settingsStore.settings.user_selected_long_coins : [],
        short_coin_list: settingsStore.settings.enable_short_trades ? settingsStore.settings.user_selected_short_coins : [],
    };
    // --- 核心修改结束 ---

    const total = (plan.enable_long_trades ? plan.long_coin_list.length : 0) +
                  (plan.enable_short_trades ? plan.short_coin_list.length : 0);
    fireAndForgetApiCall('/api/trading/start', plan, '自动开仓', total);
  }
};

const handleSyncSlTp = () => {
  if (settingsStore.settings) {
    // --- 核心修改：同步 SL/TP 时，也应该使用用户选择的列表 ---
    // `sync_all_sltp` 任务会重新从后端加载配置，所以此处传递 `settingsStore.settings` 即可
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
      rel_strength_days: settingsStore.settings.rel_strength_days, // 确保这里和后端命名一致
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
  // 确保在组件挂载时也获取一次持仓，以防初始状态下没有数据
  if (positionStore.positions.length === 0) {
    positionStore.fetchPositions();
  }
});
</script>
