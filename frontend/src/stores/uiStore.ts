// frontend/src/stores/uiStore.ts
import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { useLogStore } from './logStore';
import type { RebalancePlan, Position } from '@/models/types';

export type CloseTarget =
  | { type: 'single'; position: Position }
  | { type: 'by_side'; side: 'long' | 'short' | 'all' };

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

  const statusColor = computed(() => {
    if (isRunning.value) return 'warning';
    if (statusMessage.value === '已断开') return 'error';
    return 'success';
  });

  function setStatus(message: string, running?: boolean) {
    statusMessage.value = message;
    if (running !== undefined) {
      isRunning.value = running;
    }
  }

  function openLogDrawer() {
    showLogDrawer.value = true;
  }

  function closeLogDrawer() {
    showLogDrawer.value = false;
  }

  function toggleLogDrawer() {
    showLogDrawer.value = !showLogDrawer.value;
  }

  function openCloseDialog(target: CloseTarget) {
    closeTarget.value = target;
    showCloseDialog.value = true;
  }

  return {
    statusMessage, isRunning, showLogDrawer, showRebalanceDialog,
    statusColor, logStore, rebalancePlan, showCloseDialog, closeTarget,
    showWeightDialog,
    setStatus, toggleLogDrawer, openCloseDialog, openLogDrawer, closeLogDrawer
  };
});
