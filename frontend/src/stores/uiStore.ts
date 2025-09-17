// frontend/src/stores/uiStore.ts (重构版)
import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { useLogStore } from './logStore';
import type { RebalancePlan, Position, ProgressState } from '@/models/types';
import api from '@/services/api';

export type CloseTarget =
  | { type: 'single'; position: Position }
  | { type: 'by_side'; side: 'long' | 'short' | 'all' }
  | { type: 'selected'; positions: Position[] };

export const useUiStore = defineStore('ui', () => {
  const logStore = useLogStore();
  const statusMessage = ref('初始化中...');
  const isRunning = ref(false);
  const isStopping = ref(false);

  const progress = ref<ProgressState>({
    success_count: 0,
    failed_count: 0,
    total: 0,
    task_name: '',
    show: false,
    is_final: false
  });

  const showLogDrawer = ref(false);
  const showRebalanceDialog = ref(false);
  const rebalancePlan = ref<RebalancePlan | null>(null);
  const showCloseDialog = ref(false);
  const closeTarget = ref<CloseTarget | null>(null);
  const showWeightDialog = ref(false);

  let progressResetTimer: number;

  const statusColor = computed(() => {
    if (isStopping.value) return 'orange';
    if (isRunning.value) return 'warning';
    if (statusMessage.value === '已断开' || statusMessage.value.includes('失败')) return 'error';
    if (statusMessage.value === '已连接' || statusMessage.value === '准备就绪') return 'success';
    return 'info';
  });

  function hideProgress() {
    progress.value.show = false;
    progress.value.is_final = false;
  }

  // REFACTOR: 新增一个 action 来统一处理所有“即发即忘”的后台任务启动逻辑。
  function launchTask(endpoint: string, payload: any, taskName: string, totalTasks: number) {
    if (isRunning.value) {
      logStore.addLog({ message: '已有任务在运行中，请稍后再试。', level: 'warning', timestamp: new Date().toLocaleTimeString() });
      return;
    }
    const requestId = `req-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
    const payloadWithId = { ...payload, request_id: requestId };

    setStatus(`正在提交: ${taskName}...`, true);
    updateProgress({
        success_count: 0,
        failed_count: 0,
        total: totalTasks,
        task_name: taskName,
        is_final: false
    });
    logStore.addLog({ message: `[前端] 已发送 '${taskName}' 启动指令 (ID: ${requestId})。`, level: 'info', timestamp: new Date().toLocaleTimeString() });

    api.post(endpoint, payloadWithId)
      .then(response => {
        console.log('API call successful:', response.data.message);
      })
      .catch(error => {
        const errorMsg = error.response?.data?.detail || error.message;
        logStore.addLog({ message: `[前端] 任务提交失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
        setStatus("任务启动失败", false);
      });
  }

  function setStatus(message: string, running?: boolean) {
    statusMessage.value = message;
    if (running !== undefined) {
      isRunning.value = running;
    }

    if (running === false) {
      isStopping.value = false;
      if (progress.value.is_final) {
        clearTimeout(progressResetTimer);
        progressResetTimer = window.setTimeout(hideProgress, 3000);
      } else {
        hideProgress();
      }
    }
  }

  function updateProgress(data: Omit<ProgressState, 'show'>) {
    if (isStopping.value) return;
    clearTimeout(progressResetTimer);
    progress.value = { ...data, show: true };

    if (data.is_final) {
        clearTimeout(progressResetTimer);
        progressResetTimer = window.setTimeout(hideProgress, 3000);
    }
  }

  function initiateStop() {
    if (!isRunning.value) return;
    isStopping.value = true;
    statusMessage.value = "正在停止...";
  }

  async function checkInitialStatus(): Promise<boolean> {
    try {
      const response = await api.get('/api/status');
      const { is_running, progress: progressData } = response.data;

      if (is_running && progressData && typeof progressData.total !== 'undefined') {
        isRunning.value = true;
        statusMessage.value = `正在执行: ${progressData.task_name}...`;
        progress.value = {
            success_count: progressData.success_count || 0,
            failed_count: progressData.failed_count || 0,
            total: progressData.total || 0,
            task_name: progressData.task_name,
            show: true,
            is_final: false
        };
        return true;
      } else {
        isRunning.value = false;
        statusMessage.value = "准备就绪";
      }
    } catch (error) {
      console.error("Initial status check failed:", error);
      statusMessage.value = "状态检查失败";
    }
    return false;
  }

  function toggleLogDrawer() { showLogDrawer.value = !showLogDrawer.value; }

  function openCloseDialog(target: CloseTarget) {
    closeTarget.value = target;
    showCloseDialog.value = true;
  }

  return {
    statusMessage, isRunning, isStopping, showLogDrawer, showRebalanceDialog,
    statusColor, logStore, rebalancePlan, showCloseDialog, closeTarget,
    showWeightDialog, progress,
    setStatus, toggleLogDrawer, openCloseDialog,
    updateProgress, initiateStop, checkInitialStatus,
    launchTask
  };
});
