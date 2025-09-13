<template>
  <v-card>
    <v-card-title class="d-flex align-center py-2">
      <span class="text-h6 mr-4">{{ title }}</span>
      <v-chip :color="side === 'long' ? 'success' : 'error'" label variant="flat" size="small">
        <span class="font-weight-bold">
          总价值: ${{ totalNotional.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}
        </span>
      </v-chip>
      <v-spacer></v-spacer>

      <!-- 核心升级：智能批量平仓按钮 -->
      <v-btn
        :color="selectedInThisTable.length > 0 ? 'warning' : 'blue-grey'"
        variant="tonal"
        size="small"
        class="mr-2"
        @click="handleBulkClose"
      >
        <v-icon left>{{ selectedInThisTable.length > 0 ? 'mdi-close-box-multiple' : 'mdi-close-circle-multiple' }}</v-icon>
        {{ selectedInThisTable.length > 0 ? `平掉选中 (${selectedInThisTable.length})` : '批量平仓' }}
      </v-btn>

      <v-btn icon="mdi-refresh" variant="text" size="small" @click="emit('refresh')" :loading="loading"></v-btn>
    </v-card-title>

    <v-divider></v-divider>

    <v-data-table-virtual
      v-model="positionStore.selectedPositions"
      :headers="headers"
      :items="positions"
      item-value="full_symbol"
      show-select
      density="compact"
      class="text-caption"
      fixed-header
      height="calc(50vh - 100px)"
      no-data-text="无持仓数据"
    >
      <template v-slot:item.notional="{ item }">${{ item.notional.toFixed(2) }}</template>
      <template v-slot:item.pnl="{ item }">
        <span :class="item.pnl >= 0 ? 'text-success' : 'text-error'">{{ item.pnl.toFixed(2) }}</span>
      </template>
      <template v-slot:item.pnl_percentage="{ item }">
        <span :class="item.pnl_percentage >= 0 ? 'text-success' : 'text-error'">
          {{ item.pnl_percentage > 0 ? '+' : '' }}{{ item.pnl_percentage.toFixed(2) }}%
        </span>
      </template>
      <template v-slot:item.actions="{ item }">
        <v-btn color="error" variant="text" size="x-small" @click="uiStore.openCloseDialog({ type: 'single', position: item })">
          平仓
        </v-btn>
      </template>
    </v-data-table-virtual>
  </v-card>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { Position } from '@/models/types';
import { useUiStore } from '@/stores/uiStore';
import { usePositionStore } from '@/stores/positionStore';

type TDataTableHeader = {
  key: string;
  value?: any;
  title: string;
  align?: 'start' | 'center' | 'end';
  sortable?: boolean;
  width?: string | number;
  [key: string]: any;
};

const props = defineProps<{
  title: string;
  side: 'long' | 'short';
  positions: Position[];
  loading: boolean;
}>();

const emit = defineEmits(['refresh']);
const uiStore = useUiStore();
const positionStore = usePositionStore();

const totalNotional = computed(() => {
  return props.positions.reduce((sum, position) => sum + position.notional, 0);
});

const selectedInThisTable = computed(() => {
  const currentTableSymbols = new Set(props.positions.map(p => p.full_symbol));
  return positionStore.selectedPositions
    .filter(fullSymbol => currentTableSymbols.has(fullSymbol))
    .map(fullSymbol => props.positions.find(p => p.full_symbol === fullSymbol)!)
    .filter(p => p);
});

const handleBulkClose = () => {
  if (selectedInThisTable.value.length > 0) {
    uiStore.openCloseDialog({ type: 'selected', positions: selectedInThisTable.value });
  } else {
    uiStore.openCloseDialog({ type: 'by_side', side: props.side });
  }
};

const headers: TDataTableHeader[] = [
  { title: '合约', key: 'full_symbol', sortable: true, width: '20%' },
  { title: '名义价值', key: 'notional', sortable: true, width: '15%' },
  { title: '浮动盈亏', key: 'pnl', sortable: true, width: '15%' },
  { title: '回报率', key: 'pnl_percentage', sortable: true, width: '15%' },
  { title: '开仓均价', key: 'entry_price', width: '15%' },
  { title: '操作', key: 'actions', sortable: false, align: 'end', width: '5%' },
];
</script>
