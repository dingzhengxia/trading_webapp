<template>
  <v-dialog v-model="uiStore.showCloseDialog" max-width="400px" persistent>
    <v-card v-if="uiStore.closeTarget">
      <v-card-title class="text-h5">
        {{ dialogTitle }}
      </v-card-title>
      <v-card-text>
        <p>请选择要平仓的仓位比例:</p>
        <v-slider
          v-model="closeRatio"
          :step="1"
          thumb-label="always"
          class="my-4"
        >
          <template v-slot:append>
            <v-text-field
              v-model="closeRatio"
              type="number"
              style="width: 80px"
              density="compact"
              hide-details
              variant="outlined"
              suffix="%"
            ></v-text-field>
          </template>
        </v-slider>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="blue-darken-1" variant="text" @click="uiStore.showCloseDialog = false">取消</v-btn>
        <v-btn color="red-darken-1" variant="tonal" @click="executeClose" :disabled="closeRatio === 0" :loading="isLoading">
          确认平仓 {{ closeRatio }}%
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useUiStore } from '@/stores/uiStore';
import api from '@/services/api';

const uiStore = useUiStore();
const closeRatio = ref(100);
const isLoading = ref(false);

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

const executeClose = async () => {
  const target = uiStore.closeTarget;
  if (!target) return;

  isLoading.value = true;

  // --- 核心修复：立即关闭弹窗 ---
  uiStore.showCloseDialog = false;
  // --------------------------

  const ratio = closeRatio.value / 100;

  try {
    if (target.type === 'single') {
      const logMessage = `正在提交 ${target.position.full_symbol} 的平仓指令 (${closeRatio.value}%)...`;
      await postWithLog('/api/positions/close', { full_symbol: target.position.full_symbol, ratio }, logMessage);
    } else if (target.type === 'by_side') {
      const sideText = dialogTitle.value;
      const logMessage = `正在提交批量平仓 ${sideText} 的指令 (${closeRatio.value}%)...`;
      await postWithLog('/api/positions/close-by-side', { side: target.side, ratio }, logMessage);
    } else if (target.type === 'selected') {
      const symbolsToClose = target.positions.map(p => p.full_symbol);
      const logMessage = `正在提交批量平仓 ${symbolsToClose.length} 个选中仓位的指令...`;
      await postWithLog('/api/positions/close-multiple', { full_symbols: symbolsToClose, ratio }, logMessage);
    }
  } finally {
    isLoading.value = false;
    closeRatio.value = 100; // 重置滑块
  }
};

const postWithLog = async (url: string, data: any, logMessage: string) => {
  uiStore.logStore.addLog({ message: logMessage, level: 'info', timestamp: new Date().toLocaleTimeString() });
  try {
    await api.post(url, data);
  } catch(e: any) {
    const errorMsg = e.response?.data?.detail || e.message;
    uiStore.logStore.addLog({ message: `操作失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
  }
}
</script>
