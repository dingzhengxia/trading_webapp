<template>
  <v-container fluid>
    <v-row>
      <!-- 左侧主控制区 -->
      <v-col cols="12" md="8">
        <v-row>
          <v-col cols="12">
            <!-- 步骤A: 传递 isRunning 状态, 并监听子组件发出的操作事件 -->
            <ControlPanel
              :is-running="isRunning"
              @start-trading="handleStartTrading"
              @sync-sltp="handleSyncSlTp"
              @generate-rebalance-plan="handleGenerateRebalancePlan"
            />
          </v-col>
          <v-col cols="12">
            <PnlSummary />
          </v-col>
          <v-col cols="12">
            <PositionsTable title="多头持仓 (Long Positions)" :positions="longPositions" />
          </v-col>
          <v-col cols="12">
            <PositionsTable title="空头持仓 (Short Positions)" :positions="shortPositions" />
          </v-col>
        </v-row>
      </v-col>

      <!-- 右侧日志区 -->
      <v-col cols="12" md="4">
        <!-- 步骤B: 将日志数据(logs)传递给 LogDrawer -->
        <LogDrawer :logs="logs" @clear-logs="logs = []" />
      </v-col>
    </v-row>

    <!-- 全局组件 -->
    <ProgressBar
      :visible="progress.visible"
      :task-name="progress.task_name"
      :current="progress.current"
      :total="progress.total"
      @stop="handleStopTrading"
    />
    <Snackbar />
    <RebalanceDialog v-model="isRebalanceDialogVisible" :plan="rebalancePlan" />
  </v-container>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, reactive } from 'vue';
import ControlPanel from '@/components/ControlPanel.vue';
import PnlSummary from '@/components/PnlSummary.vue';
import PositionsTable from '@/components/PositionsTable.vue';
import LogDrawer from '@/components/LogDrawer.vue';
import ProgressBar from '@/components/ProgressBar.vue';
import Snackbar from '@/components/Snackbar.vue';
import RebalanceDialog from '@/components/RebalanceDialog.vue';
import { useSnackbarStore } from '@/stores/snackbar';
import apiClient from '@/api/apiClient';
import type { Position } from '@/types/position';
import type { TradePlan, RebalanceCriteria, RebalancePlan } from '@/types/trading';
import type { Log, Progress } from '@/types/ui';

const snackbarStore = useSnackbarStore();

// 1. 在父组件中定义所有需要共享的状态
const isRunning = ref(false);
const logs = ref<Log[]>([]);
const progress = reactive<Progress>({
  visible: false,
  current: 0,
  total: 1,
  task_name: '',
});
const positions = ref<Position[]>([]);
const isRebalanceDialogVisible = ref(false);
const rebalancePlan = ref<RebalancePlan | null>(null);

// 2. WebSocket 逻辑集中在此处
let socket: WebSocket | null = null;
let socketReconnectTimer: number | undefined;

const connectWebSocket = () => {
  const socketUrl = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8000/ws';
  socket = new WebSocket(socketUrl);

  socket.onopen = () => {
    console.log('WebSocket connected');
    snackbarStore.show({ message: '连接成功', color: 'success' });
  };

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    switch (data.type) {
      case 'log':
        // LogDrawer 现在可以收到日志了
        if (data.payload.message !== "--- 加载历史日志 ---") {
          logs.value.unshift(data.payload);
        }
        break;
      case 'status':
        // ControlPanel 现在可以收到状态了
        isRunning.value = data.payload.isRunning;
        if (!isRunning.value) {
          progress.visible = false;
        }
        break;
      case 'progress_update':
        // ProgressBar 现在可以收到进度了
        progress.current = data.payload.current;
        progress.total = data.payload.total;
        progress.task_name = data.payload.task_name;
        if (isRunning.value) {
          progress.visible = true;
        }
        break;
    }
  };

  socket.onclose = () => {
    console.log('WebSocket disconnected. Reconnecting...');
    snackbarStore.show({ message: '连接已断开，3秒后重连...', color: 'warning' });
    clearTimeout(socketReconnectTimer);
    socketReconnectTimer = setTimeout(connectWebSocket, 3000);
  };

  socket.onerror = (error) => {
    console.error('WebSocket error:', error);
    snackbarStore.show({ message: '连接错误', color: 'error' });
    socket?.close();
  };
};

// 3. API 调用逻辑集中在此处
let positionsInterval: number | undefined;
const fetchPositions = async () => {
  try {
    const response = await apiClient.get('/positions');
    positions.value = response.data;
  } catch (error) {
    console.error("Failed to fetch positions:", error);
  }
};

onMounted(() => {
  connectWebSocket();
  fetchPositions();
  positionsInterval = setInterval(fetchPositions, 5000);
});

onUnmounted(() => {
  if (socket) {
    socket.onclose = null; // 防止重连
    socket.close();
  }
  clearInterval(positionsInterval);
  clearTimeout(socketReconnectTimer);
});

const longPositions = computed(() => positions.value.filter(p => p.side === 'long'));
const shortPositions = computed(() => positions.value.filter(p => p.side === 'short'));

// 4. 定义处理子组件事件的函数
const handleStartTrading = async (plan: TradePlan) => {
  if (isRunning.value) {
    snackbarStore.show({ message: '任务正在进行中', color: 'warning' });
    return;
  }
  try {
    // 乐观更新UI
    isRunning.value = true;
    await apiClient.post('/trading/start', plan);
    snackbarStore.show({ message: '开仓任务已启动', color: 'info' });
  } catch (error: any) {
    snackbarStore.show({ message: `启动失败: ${error.response?.data?.detail || error.message}`, color: 'error' });
    isRunning.value = false; // 失败时重置UI
  }
};

const handleStopTrading = async () => {
  if (!isRunning.value) return;
  if (confirm('您确定要停止当前正在执行的任务吗？')) {
    try {
      await apiClient.post('/trading/stop');
      snackbarStore.show({ message: '停止信号已发送', color: 'info' });
    } catch (error: any) {
      snackbarStore.show({ message: `停止失败: ${error.response?.data?.detail || error.message}`, color: 'error' });
    }
  }
};

const handleSyncSlTp = async (settings: any) => {
   if (isRunning.value) {
    snackbarStore.show({ message: '任务正在进行中', color: 'warning' });
    return;
  }
  try {
    isRunning.value = true;
    await apiClient.post('/trading/sync-sltp', settings);
    snackbarStore.show({ message: 'SL/TP 校准任务已启动', color: 'info' });
  } catch (error: any) {
    snackbarStore.show({ message: `同步失败: ${error.response?.data?.detail || error.message}`, color: 'error' });
    isRunning.value = false;
  }
};

const handleGenerateRebalancePlan = async (criteria: RebalanceCriteria) => {
  if (isRunning.value) {
    snackbarStore.show({ message: '任务正在进行中', color: 'warning' });
    return;
  }
  try {
    isRunning.value = true;
    const response = await apiClient.post('/rebalance/plan', criteria);
    const planData = response.data;
    if (planData.error) {
      snackbarStore.show({ message: `生成计划失败: ${planData.error}`, color: 'error' });
    } else {
      rebalancePlan.value = planData;
      isRebalanceDialogVisible.value = true;
    }
  } catch (error: any) {
    snackbarStore.show({ message: `生成计划错误: ${error.response?.data?.detail || error.message}`, color: 'error' });
  } finally {
    isRunning.value = false; // 生成计划是快速操作，完成后重置状态
  }
};
</script>
