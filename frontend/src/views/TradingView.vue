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
      <v-spacer></v-spacer>

      <template v-if="activeTab === 'general'">
        <v-btn
          color="warning"
          variant="flat"
          @click="startStopTrading"
          :disabled="uiStore.isRunning"
          :loading="uiStore.isRunning"
        >
          <v-icon left>mdi-play</v-icon>
          开启交易
        </v-btn>
        <v-btn
          color="error"
          variant="flat"
          @click="startStopTrading"
          :disabled="!uiStore.isRunning"
          class="ml-2"
        >
          <v-icon left>mdi-stop</v-icon>
          停止交易
        </v-btn>
        <v-btn
          color="success"
          variant="flat"
          @click="settingsStore.saveSelectedCoinPools()"
          class="ml-2"
        >
          <v-icon left>mdi-content-save</v-icon>
          保存实时币种
        </v-btn>
      </template>

      <template v-if="activeTab === 'rebalance'">
        <v-btn
          color="primary"
          variant="flat"
          @click="triggerGenerateRebalancePlan"
          :disabled="isGeneratingPlan"
          :loading="isGeneratingPlan"
        >
          <v-icon left>mdi-chart-line</v-icon>
          生成再平衡计划
        </v-btn>
      </template>

      <v-btn
        color="info"
        variant="tonal"
        @click="showTerminalLog = !showTerminalLog"
        class="ml-2"
      >
        <v-icon left>mdi-text-box-outline</v-icon>
        日志
      </v-btn>
    </v-card>
  </v-footer>

  <RebalancePlanDialog v-if="uiStore.rebalancePlan" v-model="uiStore.showRebalanceDialog" :plan="uiStore.rebalancePlan" @execute-plan="handleExecuteRebalancePlan" />

</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUiStore } from '@/stores/uiStore';
import ControlPanel from '@/components/ControlPanel.vue';
import apiClient from '@/services/api';
import type { RebalanceCriteria, RebalancePlan } from '@/models/types';

const settingsStore = useSettingsStore();
const uiStore = useUiStore();
const activeTab = ref('general');
const isGeneratingPlan = ref(false);

const footerStyle = computed(() => {
  const isMobile = uiStore.isMobile;
  return {
    width: `calc(100% - ${isMobile ? '0px' : '260px'})`, // 260px 是左侧导航栏的宽度
    left: isMobile ? '0' : '260px'
  };
});

const startStopTrading = async () => {
  const action = uiStore.isRunning ? 'stop' : 'start';
  try {
    const response = await apiClient.post(`/api/bot/${action}`);
    uiStore.isRunning = response.data.status === 'running';
    uiStore.logStore.addLog({
      message: `交易机器人已${uiStore.isRunning ? '启动' : '停止'}。`,
      level: 'info',
      timestamp: new Date().toLocaleTimeString()
    });
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message;
    uiStore.logStore.addLog({
      message: `控制交易机器人失败: ${errorMsg}`,
      level: 'error',
      timestamp: new Date().toLocaleTimeString()
    });
  }
};

const triggerGenerateRebalancePlan = () => {
  if (settingsStore.settings) {
    const criteria: RebalanceCriteria = {
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

const handleExecuteRebalancePlan = async (plan: RebalancePlan) => {
  uiStore.logStore.addLog({ message: '[前端] 正在执行再平衡计划...', level: 'info', timestamp: new Date().toLocaleTimeString() });
  try {
    const response = await apiClient.post('/api/rebalance/execute', plan);
    if (response.data.error) {
      uiStore.logStore.addLog({ message: `执行计划逻辑错误: ${response.data.error}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
    } else {
      uiStore.logStore.addLog({ message: '再平衡计划已成功执行。', level: 'success', timestamp: new Date().toLocaleTimeString() });
    }
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message;
    uiStore.logStore.addLog({ message: `[后端] ❌ 执行计划请求失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
  }
};
</script>

<style scoped>
/* Vuetify fix: 确保菜单不在 `v-tabs-item` 下被遮挡 */
.v-container {
  overflow: visible;
}
</style>
