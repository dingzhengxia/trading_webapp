// frontend/src/stores/uiStore.ts (最终完整版)
import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { useLogStore } from './logStore';
import type { RebalancePlan, Position } from '@/models/types';
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
  const showLogDrawer = ref(false);
  const showRebalanceDialog = ref(false);
  const rebalancePlan = ref<RebalancePlan | null>(null);
  const showCloseDialog = ref(false);
  const closeTarget = ref<CloseTarget | null>(null);
  const showWeightDialog = ref(false);

  let progressResetTimer: number;

  const progress = ref({
    success_count: 0,
    failed_count: 0,
    total: 0,
    task_name: '',
    show: false,
    is_final: false
  });

  const statusColor = computed(() => {
    if (isStopping.value) return 'error';
    if (isRunning.value) return 'warning';
    if (statusMessage.value === '已断开' || statusMessage.value.includes('失败')) return 'error';
    if (statusMessage.value === '准备就绪') return 'success';
    return 'info';
  });

  function hideProgress() {
    progress.value.show = false;
    progress.value.is_final = false;
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

  function updateProgress(data: { success_count: number; failed_count: number; total: number; task_name: string; is_final: boolean }) {
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
        console.log("恢复UI状态:", progressData);
        // 直接设置数据，不调用会产生副作用的函数
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
      console.error("检查初始状态失败:", error);
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
    statusMessage,
    isRunning,
    isStopping,
    showLogDrawer,
    showRebalanceDialog,
    statusColor,
    logStore,
    rebalancePlan,
    showCloseDialog,
    closeTarget,
    showWeightDialog,
    progress,
    setStatus,
    toggleLogDrawer,
    openCloseDialog,
    updateProgress,
    initiateStop,
    checkInitialStatus
  };
});
