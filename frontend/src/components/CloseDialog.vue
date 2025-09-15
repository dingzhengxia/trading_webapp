<!-- frontend/src/components/CloseDialog.vue (最终完整版) -->
<template>
  <v-dialog v-model="uiStore.showCloseDialog" max-width="400px" persistent>
    <v-card v-if="uiStore.closeTarget">
      <v-card-title class="text-h5">{{ dialogTitle }}</v-card-title>
      <v-card-text>
        <p>请选择要平仓的仓位比例:</p>
        <v-slider v-model="closeRatio" :step="1" thumb-label="always" class="my-4">
          <template v-slot:append>
            <v-text-field v-model="closeRatio" type="number" style="width: 80px" density="compact" hide-details variant="outlined" suffix="%"></v-text-field>
          </template>
        </v-slider>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="blue-darken-1" variant="text" @click="closeDialog">取消</v-btn>
        <v-btn color="red-darken-1" variant="tonal" @click="executeClose" :disabled="closeRatio === 0 || uiStore.isRunning">
          确认平仓 {{ closeRatio }}%
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useUiStore } from '@/stores/uiStore';
import { usePositionStore } from '@/stores/positionStore';
import apiClient from '@/services/api';

const uiStore = useUiStore();
const positionStore = usePositionStore();
const closeRatio = ref(100);

const dialogTitle = computed(() => {
  const target = uiStore.closeTarget;
  if (!target) return '确认平仓';
  if (target.type === 'single') return `平仓: ${target.position.full_symbol}`;
  if (target.type === 'selected') return `平掉选中的 ${target.positions.length} 个仓位`;
  if (target.type === 'by_side') {
    if (target.side === 'long') return '平掉所有多头';
    if (target.side === 'short') return '平掉所有空头';
    if (target.side === 'all') return '平掉全部仓位';
  }
  return '确认平仓';
});

const closeDialog = () => {
  uiStore.showCloseDialog = false;
  closeRatio.value = 100;
};

const executeClose = async () => {
  const target = uiStore.closeTarget;
  if (!target || uiStore.isRunning) return;

  const ratio = closeRatio.value / 100;
  let endpoint: string = '';
  let payload: any = {};
  let taskName: string = '';
  let totalTasks: number = 0;

  if (target.type === 'single') {
    endpoint = '/api/positions/close';
    payload = { full_symbol: target.position.full_symbol, ratio };
    taskName = `平仓 ${target.position.symbol}`;
    totalTasks = 1;
  } else if (target.type === 'by_side') {
    endpoint = '/api/positions/close-by-side';
    payload = { side: target.side, ratio };
    taskName = `批量平仓-${target.side}`;
    if(target.side === 'long') totalTasks = positionStore.longPositions.length;
    else if(target.side === 'short') totalTasks = positionStore.shortPositions.length;
    else totalTasks = positionStore.positions.length;
  } else if (target.type === 'selected') {
    endpoint = '/api/positions/close-multiple';
    const symbols = target.positions.map(p => p.full_symbol);
    payload = { full_symbols: symbols, ratio };
    taskName = `平掉选中`;
    totalTasks = symbols.length;
  }

  // 1. 立即关闭弹窗
  closeDialog();

  // 2. 使用统一的API调用逻辑
  uiStore.setStatus( `正在提交: ${taskName}...`, true);
  uiStore.updateProgress({
    success_count: 0, failed_count: 0, total: totalTasks,
    task_name: taskName, is_final: false
  });

  try {
    const response = await apiClient.post(endpoint, payload);
    uiStore.logStore.addLog({ message: response.data.message || `${taskName} 已成功开始执行。`, level: 'info', timestamp: new Date().toLocaleTimeString() });
  } catch (e: any) {
    const errorMsg = e.response?.data?.detail || e.message;
    uiStore.logStore.addLog({ message: `任务启动失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
    uiStore.setStatus("任务启动失败", false);
  }
};
</script>
