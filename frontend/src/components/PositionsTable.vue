<!-- frontend/src/components/PositionsTable.vue (最终正确版) -->
<template>
  <v-card>
    <!-- 顶部标题栏 -->
    <v-toolbar density="compact" flat>
      <v-toolbar-title class="text-h6">{{ title }}</v-toolbar-title>
      <v-spacer></v-spacer>
      <v-chip
        :color="side === 'long' ? 'long' : 'short'"
        label
        variant="tonal"
        size="small"
        class="mr-2"
      >
        <span class="font-weight-medium num">
          总价值 ${{
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
    <v-toolbar density="compact" flat color="transparent" class="px-2 toolbar-wrap">
      <v-btn
        color="error"
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
        color="error"
        variant="outlined"
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
      :headers="visibleHeaders"
      :items="positions"
      item-value="full_symbol"
      show-select
      density="compact"
      class="text-caption position-table"
      fixed-header
      :height="isMobile ? '45vh' : 'calc(50vh - 120px)'"
      no-data-text="无持仓数据"
    >
      <template v-slot:item.notional="{ item }">
        <span class="num">${{ item.notional.toFixed(2) }}</span>
      </template>
      <template v-slot:item.pnl="{ item }">
        <span class="num" :class="pnlClass(item.pnl)">{{ formatSigned(item.pnl) }}</span>
      </template>
      <template v-slot:item.pnl_percentage="{ item }">
        <span class="num" :class="pnlClass(item.pnl_percentage)">
          {{ formatSignedPercent(item.pnl_percentage) }}
        </span>
      </template>
      <template v-slot:item.entry_price="{ item }">
        <span class="num">{{ Number(item.entry_price).toLocaleString('en-US', { maximumFractionDigits: 6 }) }}</span>
      </template>
      <template v-slot:item.actions="{ item }">
        <v-btn
          color="warning"
          variant="text"
          size="x-small"
          :disabled="uiStore.isRunning"
          @click="openReverseDialog(item)"
        >
          反手
        </v-btn>
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

    <!-- 反手确认弹窗：先全平当前仓位，再按价值反向开仓（限价 post-only） -->
    <v-dialog v-model="reverseDialog" max-width="460" persistent>
      <v-card>
        <v-card-title class="text-h6">
          <v-icon color="warning" class="mr-2">mdi-swap-horizontal</v-icon>
          确认反手
        </v-card-title>
        <v-card-text v-if="reverseTarget">
          <div class="mb-3">
            <span class="font-weight-bold">{{ reverseTarget.full_symbol }}</span>
            <v-icon size="small" class="mx-2">mdi-arrow-right-bold</v-icon>
            <v-chip
              :color="directionTone(reverseTarget.side === 'long' ? 'short' : 'long').color"
              size="small"
              label
            >
              反手后{{ reverseTarget.side === 'long' ? '做空' : '做多' }}
            </v-chip>
          </div>
          <v-alert type="warning" variant="tonal" density="compact" class="mb-4">
            将先<strong>全平</strong>该币种当前仓位，再以限价 post-only 单反向开仓（有 USDC 合约自动走 USDC）。执行中不可撤销。
          </v-alert>
          <v-text-field
            v-model.number="reverseValue"
            label="反手后目标价值 (USD)"
            type="number"
            min="1"
            step="1"
            variant="outlined"
            density="compact"
            :rules="[(v: number) => v > 0 || '价值必须大于 0']"
            hide-details="auto"
          ></v-text-field>
          <div class="text-caption text-medium-emphasis mt-1">
            当前仓位名义价值 ${{ reverseTarget.notional.toFixed(2) }}（已预填）
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="reverseDialog = false">取消</v-btn>
          <v-btn
            color="warning"
            variant="tonal"
            :disabled="!(reverseValue > 0) || uiStore.isRunning"
            @click="confirmReverse"
          >
            确认反手
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDisplay } from 'vuetify'
import type { Position } from '@/models/types'
import { useUiStore } from '@/stores/uiStore'
import { usePositionStore } from '@/stores/positionStore'
import { directionTone, pnlClass } from '@/utils/tone'
import { formatSigned, formatSignedPercent } from '@/utils/format'

type TDataTableHeader = {
  key: string
  title: string
  align?: 'start' | 'center' | 'end'
  sortable?: boolean
  width?: string | number
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

// --- 反手（单仓位）---
const reverseDialog = ref(false)
const reverseTarget = ref<Position | null>(null)
const reverseValue = ref(0)

const openReverseDialog = (position: Position) => {
  reverseTarget.value = position
  reverseValue.value = Math.max(1, Math.round(position.notional * 100) / 100)
  reverseDialog.value = true
}

const confirmReverse = () => {
  const target = reverseTarget.value
  if (!target || !(reverseValue.value > 0)) return
  // 传 full_symbol 即可，后端会自动截取基础币种（XAUT/USDT:USDT → XAUT）
  uiStore.launchTask(
    '/api/trading/manual',
    { items: [{ symbol: target.full_symbol, action: 'reverse', value: Number(reverseValue.value) }] },
    `反手交易 ${target.full_symbol}`,
    1,
  )
  reverseDialog.value = false
}

const headers: TDataTableHeader[] = [
  { title: '合约', key: 'full_symbol', sortable: true, width: '20%' },
  { title: '名义价值', key: 'notional', sortable: true, width: '15%' },
  { title: '浮动盈亏', key: 'pnl', sortable: true, width: '15%' },
  { title: '回报率', key: 'pnl_percentage', sortable: true, width: '15%' },
  { title: '开仓均价', key: 'entry_price', width: '15%' },
  { title: '操作', key: 'actions', sortable: false, align: 'end', width: '12%' },
]

// 手机端隐藏「开仓均价」列，避免表格横向溢出
const { smAndDown } = useDisplay()
const isMobile = computed(() => smAndDown.value)
const visibleHeaders = computed(() =>
  isMobile.value ? headers.filter((header) => header.key !== 'entry_price') : headers,
)
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

/* 手机端：操作栏按钮允许换行，避免被裁切 */
.toolbar-wrap :deep(.v-toolbar__content) {
  flex-wrap: wrap;
  height: auto !important;
  padding: 6px 8px !important;
  gap: 6px;
}

</style>
