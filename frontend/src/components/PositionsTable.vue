<template>
  <v-card>
    <v-card-title class="d-flex align-center py-2">
      <span class="text-h6">{{ title }}</span>
      <v-spacer></v-spacer>
      <v-menu>
        <template v-slot:activator="{ props }">
          <v-btn v-bind="props" color="blue-grey" variant="tonal" size="small" class="mr-2">
            批量平仓
            <v-icon end>mdi-chevron-down</v-icon>
          </v-btn>
        </template>
        <v-list density="compact">
          <v-list-item @click="uiStore.openCloseDialog({ type: 'by_side', side: side })">
            <v-list-item-title>平掉此方向仓位...</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>
      <v-btn icon="mdi-refresh" variant="text" size="small" @click="emit('refresh')" :loading="loading"></v-btn>
    </v-card-title>
    <v-divider></v-divider>
    <v-data-table-virtual
      :headers="headers"
      :items="positions"
      item-value="full_symbol"
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
import type { Position } from '@/models/types';
import { useUiStore } from '@/stores/uiStore';

// --- 核心修复：直接定义 Header 类型，不再从 Vuetify 导入 ---
type TDataTableHeader = {
  key: string;
  value?: any;
  title: string;
  align?: 'start' | 'center' | 'end';
  sortable?: boolean;
  width?: string | number;
  [key: string]: any;
};
// --------------------------------------------------------

const props = defineProps<{
  title: string;
  side: 'long' | 'short';
  positions: Position[];
  loading: boolean;
}>();

const emit = defineEmits(['refresh']);
const uiStore = useUiStore();

// --- 核心修复：为 headers 提供我们自己定义的类型 ---
const headers: TDataTableHeader[] = [
  { title: '合约', key: 'full_symbol', sortable: true, width: '20%' },
  { title: '名义价值', key: 'notional', sortable: true, width: '15%' },
  { title: '浮动盈亏', key: 'pnl', sortable: true, width: '15%' },
  { title: '回报率', key: 'pnl_percentage', sortable: true, width: '15%' },
  { title: '开仓均价', key: 'entry_price', width: '15%' },
  { title: '操作', key: 'actions', sortable: false, align: 'end', width: '5%' },
];
// -------------------------------------------
</script>
