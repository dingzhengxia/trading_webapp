// frontend/src/stores/positionStore.ts (完整升级版)
import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import type { Position } from '@/models/types';
import api from '@/services/api';

export const usePositionStore = defineStore('position', () => {
  const positions = ref<Position[]>([]);
  const loading = ref(false);

  const longPositions = computed(() => positions.value.filter(p => p.side === 'long'));
  const shortPositions = computed(() => positions.value.filter(p => p.side === 'short'));

  // --- 新增：PNL 计算属性 ---
  const longPnl = computed(() => longPositions.value.reduce((sum, p) => sum + p.pnl, 0));
  const shortPnl = computed(() => shortPositions.value.reduce((sum, p) => sum + p.pnl, 0));
  const totalPnl = computed(() => longPnl.value + shortPnl.value);
  // -------------------------

  async function fetchPositions() {
    loading.value = true;
    try {
      const response = await api.get<Position[]>('/api/positions');
      positions.value = response.data;
    } catch (error) {
      console.error("Failed to fetch positions", error);
    } finally {
      loading.value = false;
    }
  }

  return {
    positions, loading,
    longPositions, shortPositions,
    longPnl, shortPnl, totalPnl, // 导出 PNL 数据
    fetchPositions
  };
});
