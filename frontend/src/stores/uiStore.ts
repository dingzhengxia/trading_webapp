// frontend/src/stores/uiStore.ts (终极日志诊断版)
import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { useLogStore } from './logStore';
import type {RebalancePlan, Position, CloseTarget, Progress} from '@/models/types';
import api from '@/services/api';

export const useUiStore = defineStore('ui', () => {
  console.log('[uiStore] Store instance created/re-created.');
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

  // --- 修改：为 progress 对象添加明确的类型 ---
  const progress = ref<Progress>({ // <-- 使用 Progress 接口
    success_count: 0,
    failed_count: 0,
    total: 0,
    task_name: '',
    show: false,
    is_final: false
  });
  // --- 修改结束 ---

  const statusColor = computed(() => {
    if (isStopping.value) return 'error';
    if (isRunning.value) return 'warning';
    if (statusMessage.value === '已断开' || statusMessage.value.includes('失败')) return 'error';
    if (statusMessage.value === '准备就绪') return 'success';
    return 'info';
  });

  function hideProgress() {
    console.log(`%c[uiStore] HIDE_PROGRESS called. Setting progress.show to false.`, 'color: orange;');
    progress.value.show = false;
    progress.value.is_final = false;
  }

  function setStatus(message: string, running?: boolean) {
    console.log(`%c[uiStore] SET_STATUS called with: message="${message}", running=${running}`, 'color: lightblue;', 'Current isRunning:', isRunning.value);

    // 保护逻辑
    if (message === '已断开' && isRunning.value && running === false) {
      console.log('%c[uiStore] SET_STATUS protection activated: Task is running, but WS disconnected. ONLY updating message.', 'color: violet;');
      statusMessage.value = message;
      return;
    }

    statusMessage.value = message;
    if (running !== undefined) {
      console.log(`[uiStore] SET_STATUS changing isRunning from ${isRunning.value} to ${running}`);
      isRunning.value = running;
    }

    if (running === false) {
      console.log('[uiStore] SET_STATUS detected running === false.');
      isStopping.value = false;
      if (progress.value.is_final) {
        console.log('[uiStore] SET_STATUS: is_final is true. Hiding progress in 3s.');
        clearTimeout(progressResetTimer);
        progressResetTimer = window.setTimeout(hideProgress, 3000);
      } else {
        console.log('[uiStore] SET_STATUS: is_final is false. Hiding progress immediately.');
        hideProgress();
      }
    }
  }

  function updateProgress(data: { success_count: number; failed_count: number; total: number; task_name: string; is_final: boolean }) {
    console.log('%c[uiStore] UPDATE_PROGRESS called with data:', 'color: lightgreen;', data);
    if (isStopping.value) {
      console.log('[uiStore] UPDATE_PROGRESS ignored because isStopping is true.');
      return;
    }
    clearTimeout(progressResetTimer);
    progress.value = { ...data, show: true };
    console.log('[uiStore] UPDATE_PROGRESS finished. New progress.show state:', progress.value.show);

    if (data.is_final) {
        console.log('[uiStore] UPDATE_PROGRESS detected is_final flag. Hiding progress in 3s.');
        clearTimeout(progressResetTimer);
        progressResetTimer = window.setTimeout(hideProgress, 3000);
    }
  }

  function initiateStop() {
    console.log('%c[uiStore] INITIATE_STOP called.', 'color: red;');
    if (!isRunning.value) {
      console.log('[uiStore] INITIATE_STOP ignored because isRunning is false.');
      return;
    }
    isStopping.value = true;
    statusMessage.value = "正在停止...";
  }

  async function checkInitialStatus(): Promise<boolean> {
    console.log('%c[uiStore] CHECK_INITIAL_STATUS starting...', 'color: cyan;');
    try {
      const response = await api.get('/api/status');
      const { is_running, progress: progressData } = response.data;
      console.log('[uiStore] CHECK_INITIAL_STATUS API response received:', { is_running, progressData });

      if (is_running && progressData && typeof progressData.total !== 'undefined') {
        console.log('[uiStore] CHECK_INITIAL_STATUS found a running task. Restoring state directly.');
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
        console.log('[uiStore] CHECK_INITIAL_STATUS finished. State restored. isRunning:', isRunning.value, 'progress.show:', progress.value.show);
        return true;
      } else {
        console.log('[uiStore] CHECK_INITIAL_STATUS found no running task.');
        isRunning.value = false;
        statusMessage.value = "准备就绪";
      }
    } catch (error) {
      console.error("[uiStore] CHECK_INITIAL_STATUS failed:", error);
      statusMessage.value = "状态检查失败";
    }
    console.log('%c[uiStore] CHECK_INITIAL_STATUS finished.', 'color: cyan;');
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
