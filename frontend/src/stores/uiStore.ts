// frontend/src/stores/uiStore.ts (最终修复版)
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

  // --- 核心修改在这里 ---

  // 新增一个专门隐藏进度条的函数
  function hideProgress() {
    progress.value.show = false;
    progress.value.is_final = false;
  }

  function setStatus(message: string, running?: boolean) {
    statusMessage.value = message;

    if (running !== undefined) {
      isRunning.value = running;
    }

    // 如果任务结束，则解除停止状态锁
    if (running === false) {
      isStopping.value = false;
      // setStatus 不再负责隐藏进度条。这个逻辑转移到 _execute_and_log_task 结束时广播的 status 消息处理中。
      // 我们依赖 is_final 标志来决定是否延迟隐藏。
      if (progress.value.is_final) {
        clearTimeout(progressResetTimer);
        progressResetTimer = window.setTimeout(hideProgress, 3000); // 延迟隐藏
      } else {
        hideProgress(); // 立即隐藏
      }
    }
  }

  function updateProgress(data: { success_count: number; failed_count: number; total: number; task_name: string; is_final: boolean }) {
    if (isStopping.value) return;
    clearTimeout(progressResetTimer); // 收到任何新进度，都取消“延迟隐藏”的计划
    progress.value = { ...data, show: true };

    // 如果这是一个最终状态的更新，我们也在这里启动延迟隐藏计时器
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

        // 恢复状态时，我们只设置 isRunning 和 statusMessage，不触发隐藏逻辑
        statusMessage.value = `正在执行: ${progressData.task_name}...`;
        isRunning.value = true;

        // 然后用干净的数据更新进度条，让它显示出来
        updateProgress({
            success_count: progressData.success_count || 0,
            failed_count: progressData.failed_count || 0,
            total: progressData.total || 0,
            task_name: progressData.task_name,
            is_final: false
        });
        return true;
      }
    } catch (error) { console.error("检查初始状态失败:", error); }
    return false;
  }

  // --- 修改结束 ---

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
