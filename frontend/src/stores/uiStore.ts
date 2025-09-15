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
  const statusMessage = ref('准备就绪');
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
    success_count: 0, failed_count: 0, total: 0,
    task_name: '', show: false, is_final: false
  });

  const statusColor = computed(() => {
    if (isStopping.value) return 'error';
    if (isRunning.value) return 'warning';
    if (statusMessage.value === '已断开') return 'error';
    return 'success';
  });

  function setStatus(message: string, running?: boolean) {
    statusMessage.value = message;
    if (running !== undefined) isRunning.value = running;

    if (running === false) {
      isStopping.value = false;
      if (progress.value.is_final) {
        clearTimeout(progressResetTimer);
        progressResetTimer = window.setTimeout(() => {
          progress.value.show = false;
          progress.value.is_final = false;
        }, 3000);
      } else {
        progress.value.show = false;
      }
    }
  }

  function updateProgress(data: { success_count: number; failed_count: number; total: number; task_name: string; is_final: boolean }) {
    if (isStopping.value) return;
    clearTimeout(progressResetTimer);
    progress.value = { ...data, show: true };
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

      if (is_running && progressData && progressData.total !== undefined) {
        console.log("检测到后台任务正在运行，正在恢复UI状态:", progressData);

        const processed = (progressData.success_count || 0) + (progressData.failed_count || 0);
        setStatus(`正在执行: ${progressData.task_name}...`, true);

        // 直接用后端返回的数据更新进度条
        updateProgress({
            success_count: progressData.success_count || 0,
            failed_count: progressData.failed_count || 0,
            total: progressData.total || 0,
            task_name: `${progressData.task_name}: ${processed}/${progressData.total}`,
            is_final: false
        });
        return true;
      }
    } catch (error) { console.error("检查初始状态失败:", error); }
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
    updateProgress, initiateStop, checkInitialStatus
  };
});
