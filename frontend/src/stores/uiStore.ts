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
    if (isRunning.value) return 'warning';
    if (statusMessage.value === '已断开') return 'error';
    return 'success';
  });

  function setStatus(message: string, running?: boolean) {
    statusMessage.value = message;
    if (running !== undefined) isRunning.value = running;

    if (running === false && progress.value.is_final) {
      clearTimeout(progressResetTimer);
      progressResetTimer = window.setTimeout(() => {
        progress.value.show = false;
        progress.value.is_final = false; // 重置final状态
      }, 3000);
    } else if (running === false) {
      // 如果任务不是正常结束（例如被用户停止），则立即隐藏
      progress.value.show = false;
    }
  }

  function updateProgress(data: { success_count: number; failed_count: number; total: number; task_name: string; is_final: boolean }) {
    // 核心修改：收到任何进度更新，立即清除隐藏计时器并强制显示
    clearTimeout(progressResetTimer);
    // 将传入的数据与 show: true 合并，确保进度条始终可见
    progress.value = { ...data, show: true };
  }

  function toggleLogDrawer() { showLogDrawer.value = !showLogDrawer.value; }
  function openCloseDialog(target: CloseTarget) {
    closeTarget.value = target;
    showCloseDialog.value = true;
  }

  return {
    statusMessage, isRunning, showLogDrawer, showRebalanceDialog,
    statusColor, logStore, rebalancePlan, showCloseDialog, closeTarget,
    showWeightDialog, progress,
    setStatus, toggleLogDrawer, openCloseDialog,
    updateProgress
  };
});
