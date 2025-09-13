<template>
  <v-dialog v-model="uiStore.showCloseDialog" max-width="400px">
    <v-card v-if="uiStore.closeTarget">
      <v-card-title class="text-h5">
        确认平仓:
        <span v-if="uiStore.closeTarget.type === 'single'">{{ uiStore.closeTarget.position.full_symbol }}</span>
        <span v-else>{{ closeSideText }}</span>
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
        <v-btn color="red-darken-1" variant="tonal" @click="executeClose" :disabled="closeRatio === 0">
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

const closeSideText = computed(() => {
  if (uiStore.closeTarget?.type === 'by_side') {
    if (uiStore.closeTarget.side === 'long') return '所有多头';
    if (uiStore.closeTarget.side === 'short') return '所有空头';
    if (uiStore.closeTarget.side === 'all') return '全部仓位';
  }
  return '';
});

const executeClose = async () => {
  const target = uiStore.closeTarget;
  if (!target) return;

  const ratio = closeRatio.value / 100;
  let url = '';
  let data: any = {};
  let logMessage = '';

  if (target.type === 'single') {
    url = '/api/positions/close';
    data = { full_symbol: target.position.full_symbol, ratio };
    logMessage = `正在提交 ${target.position.full_symbol} 的平仓指令 (${closeRatio.value}%)...`;
  } else {
    url = '/api/positions/close-by-side';
    data = { side: target.side, ratio };
    logMessage = `正在提交批量平仓 ${closeSideText.value} 的指令 (${closeRatio.value}%)...`;
  }

  await openLogAndPost(url, data, logMessage);

  uiStore.showCloseDialog = false;
  closeRatio.value = 100;
};

const openLogAndPost = async (url: string, data: any, logMessage: string) => {
  uiStore.logStore.addLog({ message: logMessage, level: 'info', timestamp: new Date().toLocaleTimeString() });
  if (!uiStore.showLogDrawer) {
    uiStore.showLogDrawer = true;
  }
  try {
    await api.post(url, data);
  } catch(e: any) {
    const errorMsg = e.response?.data?.detail || e.message;
    uiStore.logStore.addLog({ message: `操作失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
  }
}
</script>
