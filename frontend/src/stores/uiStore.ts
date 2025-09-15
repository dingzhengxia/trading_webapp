// frontend/src/stores/uiStore.ts (完整代码)
import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { useLogStore } from './logStore';
import type { RebalancePlan, Position } from '@/models/types';

export type CloseTarget =
  | { type: 'single'; position: Position }
  | { type: 'by_side'; side: 'long' | 'short' | 'all' }
  | { type: 'selected'; positions: Position[] };

export const useUiStore = defineStore('ui', () => {
  const logStore = useLogStore();
  const statusMessage = ref('准备就绪');
  const isRunning = ref(false);
  const isStopping = ref(false); // 新增：停止状态锁
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
    if (statusMessage.value === '已断开') return 'error';
    return 'success';
  });

  function setStatus(message: string, running?: boolean) {
    statusMessage.value = message;
    if (running !== undefined) isRunning.value = running;

    if (running === false) {
      isStopping.value = false; // 解除停止状态锁

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
    updateProgress, initiateStop
  };
});
