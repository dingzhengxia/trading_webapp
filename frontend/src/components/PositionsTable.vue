<!-- frontend/src/components/PositionsTable.vue (最终正确版) -->
<template>
  <v-card>
    <!-- 顶部标题栏 -->
    <v-toolbar density="compact" flat>
      <v-toolbar-title class="text-h6">{{ title }}</v-toolbar-title>
      <v-spacer></v-spacer>
      <v-chip
        :color="side === 'long' ? 'success' : 'error'"
        label
        variant="flat"
        size="small"
        class="mr-2"
      >
        <span class="font-weight-bold">
          总价值: ${{
            totalNotional.toLocaleString('en-US', {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })
          }}
        </span>
      </v-chip>
      <v-btn
        icon="mdi-refresh"
        variant="text"
        size="small"
        @click="emit('refresh')"
        :loading="loading"
      ></v-btn>
    </v-toolbar>

    <!-- 第二行操作栏 -->
    <v-toolbar density="compact" flat color="transparent" class="px-2">
      <v-btn
        color="warning"
        variant="tonal"
        size="small"
        @click="handleCloseSelected"
        :disabled="selectedInThisTable.length === 0"
        prepend-icon="mdi-close-box-multiple"
      >
        平掉选中 ({{ selectedInThisTable.length }})
      </v-btn>
      <v-spacer></v-spacer>
      <v-btn
        color="blue-grey"
        variant="tonal"
        size="small"
        @click="handleCloseAll"
        prepend-icon="mdi-close-circle-multiple"
      >
        批量平仓 (全部)
      </v-btn>
    </v-toolbar>

    <v-divider></v-divider>

    <v-data-table-virtual
      v-model="positionStore.selectedPositions"
      :headers="headers"
      :items="positions"
      item-value="full_symbol"
      show-select
      density="compact"
      class="text-caption position-table"
      fixed-header
      height="calc(50vh - 120px)"
      no-data-text="无持仓数据"
    >
      <template v-slot:item.notional="{ item }">${{ item.notional.toFixed(2) }}</template>
      <template v-slot:item.pnl="{ item }">
        <span :class="item.pnl >= 0 ? 'text-success' : 'text-error'">{{
          item.pnl.toFixed(2)
        }}</span>
      </template>
      <template v-slot:item.pnl_percentage="{ item }">
        <span :class="item.pnl_percentage >= 0 ? 'text-success' : 'text-error'">
          {{ item.pnl_percentage > 0 ? '+' : '' }}{{ item.pnl_percentage.toFixed(2) }}%
        </span>
      </template>
      <template v-slot:item.actions="{ item }">
        <v-btn
          color="error"
          variant="text"
          size="x-small"
          @click="uiStore.openCloseDialog({ type: 'single', position: item })"
        >
          平仓
        </v-btn>
      </template>
    </v-data-table-virtual>
  </v-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Position } from '@/models/types'
import { useUiStore } from '@/stores/uiStore'
import { usePositionStore } from '@/stores/positionStore'

type TDataTableHeader = {
  key: string
  value?: any
  title: string
  align?: 'start' | 'center' | 'end'
  sortable?: boolean
  width?: string | number
  [key: string]: any
}

const props = defineProps<{
  title: string
  side: 'long' | 'short'
  positions: Position[]
  loading: boolean
}>()

const emit = defineEmits(['refresh'])
const uiStore = useUiStore()
const positionStore = usePositionStore()

const totalNotional = computed(() => {
  return props.positions.reduce((sum, position) => sum + position.notional, 0)
})

const selectedInThisTable = computed(() => {
  const currentTableSymbols = new Set(props.positions.map((p) => p.full_symbol))
  return positionStore.selectedPositions
    .filter((fullSymbol) => currentTableSymbols.has(fullSymbol))
    .map((fullSymbol) => props.positions.find((p) => p.full_symbol === fullSymbol)!)
    .filter((p) => p)
})

const handleCloseAll = () => {
  uiStore.openCloseDialog({ type: 'by_side', side: props.side })
}

const handleCloseSelected = () => {
  if (selectedInThisTable.value.length > 0) {
    uiStore.openCloseDialog({ type: 'selected', positions: selectedInThisTable.value })
  }
}

const headers: TDataTableHeader[] = [
  { title: '合约', key: 'full_symbol', sortable: true, width: '20%' },
  { title: '名义价值', key: 'notional', sortable: true, width: '15%' },
  { title: '浮动盈亏', key: 'pnl', sortable: true, width: '15%' },
  { title: '回报率', key: 'pnl_percentage', sortable: true, width: '15%' },
  { title: '开仓均价', key: 'entry_price', width: '15%' },
  { title: '操作', key: 'actions', sortable: false, align: 'end', width: '5%' },
]
</script>

<!-- FINAL, CORRECT FIX: 使用更强力的CSS规则 -->
<style scoped>
/*
  使用 :deep() 来穿透组件作用域，直接作用于 Vuetify 的内部 class。
  我们直接 targeting the table header cell (<th>) 本身。
  并使用 !important 来确保我们的样式拥有最高优先级，覆盖任何 Vuetify 的默认响应式样式。
*/
:deep(.position-table .v-data-table__th) {
  white-space: nowrap !important;
}
</style>
