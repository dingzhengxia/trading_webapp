<!-- frontend/src/components/PositionsTable.vue -->
<!--
  重设计（redesign-spec 2026-11-13 · B4）：
  xs（<600）：6 列表格降级为卡片——头行 合约 + 方向徽标 + 浮动盈亏大字；
  次行 回报率 · 名义价值；底部 反手/平仓按钮（40px 高，右对齐）。
  checkbox 与「开仓均价」列在 xs 隐藏（开仓均价进卡片点击展开）；批量选择用「多选」开关。
  sm+ 保留表格（sm 横滚、md+ 完整 6 列）；表格高度 xs 不再占用 45vh（卡片流自然高度）。
  判色一律走 tone.ts（pnlClass / directionTone）。
-->
<template>
  <v-card>
    <!-- 顶部标题栏 -->
    <v-toolbar density="compact" flat>
      <v-toolbar-title class="text-subtitle-2 font-weight-medium">{{ title }}</v-toolbar-title>
      <v-spacer></v-spacer>
      <v-chip
        :color="side === 'long' ? 'long' : 'short'"
        label
        variant="tonal"
        size="small"
        class="mr-2"
      >
        <span class="font-weight-medium num">
          总价值 ${{ formatAmount(totalNotional) }}
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
      <!-- xs：批量选择改走「多选」开关（卡片出现 checkbox），完成批量平仓 -->
      <v-switch
        v-if="isXs"
        v-model="selectMode"
        label="多选"
        color="primary"
        density="compact"
        inset
        hide-details
        class="mr-1 mobile-switch"
      ></v-switch>
      <v-btn
        color="warning"
        variant="outlined"
        size="small"
        @click="handleReverseAll"
        :disabled="positions.length === 0"
        prepend-icon="mdi-swap-horizontal-multiple"
      >
        批量反手 (全部)
      </v-btn>
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

    <!-- xs：卡片化 -->
    <div v-if="isXs" class="pa-2 d-flex flex-column ga-2">
      <EmptyState
        v-if="positions.length === 0 && !loading"
        icon="mdi-chart-line-variant"
        title="无持仓数据"
      />
      <div
        v-for="item in positions"
        :key="item.full_symbol"
        class="position-card"
        :class="{
          'position-card--selectable': selectMode,
          'position-card--selected': selectMode && isCardSelected(item),
        }"
        @click="handleCardClick(item)"
      >
        <!-- 头行：合约 + 方向徽标 + 浮动盈亏大字 -->
        <div class="d-flex align-center ga-2">
          <v-checkbox-btn
            v-if="selectMode"
            :model-value="isCardSelected(item)"
            :aria-label="`选择 ${item.full_symbol}`"
            hide-details
            color="primary"
            class="position-card__check"
            @click.stop
            @update:model-value="toggleCardSelect(item)"
          ></v-checkbox-btn>
          <span class="position-card__symbol">{{ item.full_symbol }}</span>
          <span class="dir-badge" :class="`dir-badge--${directionTone(item.side).key}`">
            <v-icon>{{ directionTone(item.side).icon }}</v-icon
            >{{ directionTone(item.side).label }}
          </span>
          <v-spacer></v-spacer>
          <span class="position-card__pnl num" :class="pnlClass(item.pnl)">
            {{ formatSigned(item.pnl) }}
          </span>
        </div>
        <!-- 次行：回报率 · 名义价值 -->
        <div class="position-card__sub text-caption">
          <span>回报率 <span class="num" :class="pnlClass(item.pnl_percentage)">{{ formatSignedPercent(item.pnl_percentage) }}</span></span>
          <span>名义价值 <span class="num">${{ formatFixed(item.notional, 2) }}</span></span>
          <v-spacer></v-spacer>
          <!-- 展开与选择分离：多选态下点卡片是选中，展开只能点这里 -->
          <v-btn
            icon
            variant="text"
            size="x-small"
            class="position-card__expand"
            :aria-label="cardExpanded.has(item.full_symbol) ? '收起明细' : '展开明细'"
            :aria-expanded="cardExpanded.has(item.full_symbol)"
            @click.stop="toggleCardExpand(item.full_symbol)"
          >
            <v-icon size="18" class="text-medium-emphasis">
              {{ cardExpanded.has(item.full_symbol) ? 'mdi-chevron-up' : 'mdi-chevron-down' }}
            </v-icon>
          </v-btn>
        </div>
        <!-- 点击展开：开仓均价 / 数量（xs 表格列隐藏，细节收在这里） -->
        <div v-if="cardExpanded.has(item.full_symbol)" class="text-caption text-medium-emphasis mt-1">
          开仓均价 <span class="num">{{ entryPriceText(item.entry_price) }}</span>
          · 数量 <span class="num">{{ item.contracts }}</span>
        </div>
        <!-- 底部操作：40px 高按钮，右对齐 -->
        <div class="d-flex ga-2 justify-end mt-2" @click.stop>
          <v-btn
            color="warning"
            variant="tonal"
            size="small"
            class="position-card__btn"
            :disabled="uiStore.isRunning"
            @click="openReverseDialog(item)"
          >
            反手
          </v-btn>
          <v-btn
            color="error"
            variant="tonal"
            size="small"
            class="position-card__btn"
            @click="uiStore.openCloseDialog({ type: 'single', position: item })"
          >
            平仓
          </v-btn>
        </div>
      </div>
    </div>

    <!-- sm+：表格 -->
    <v-data-table-virtual
      v-else
      v-model="positionStore.selectedPositions"
      :headers="headers"
      :items="positions"
      item-value="full_symbol"
      show-select
      density="compact"
      class="text-caption position-table"
      fixed-header
      :height="isSm ? '45vh' : 'calc(50vh - 120px)'"
      no-data-text="无持仓数据"
    >
      <template v-slot:item.notional="{ item }">
        <span class="num">${{ formatFixed(item.notional, 2) }}</span>
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
        <span class="num">{{ entryPriceText(item.entry_price) }}</span>
      </template>
      <template v-slot:item.actions="{ item }">
        <v-btn
          color="warning"
          variant="text"
          size="small"
          :disabled="uiStore.isRunning"
          @click="openReverseDialog(item)"
        >
          反手
        </v-btn>
        <v-btn
          color="error"
          variant="text"
          size="small"
          @click="uiStore.openCloseDialog({ type: 'single', position: item })"
        >
          平仓
        </v-btn>
      </template>
    </v-data-table-virtual>

    <!-- 反手确认弹窗：先全平当前仓位，再按价值反向开仓（限价 post-only） -->
    <v-dialog v-model="reverseDialog" max-width="460" persistent>
      <v-card>
        <v-card-title class="text-subtitle-1 font-weight-medium">
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
            当前仓位名义价值 ${{ formatFixed(reverseTarget.notional, 2) }}（已预填）
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
    <!-- 批量反手确认弹窗：本表全部仓位逐个先全平再反向开仓（限价 post-only） -->
    <v-dialog v-model="batchReverseDialog" max-width="560" persistent>
      <v-card>
        <v-card-title class="text-subtitle-1 font-weight-medium">
          <v-icon color="warning" class="mr-2">mdi-swap-horizontal-multiple</v-icon>
          确认批量反手（{{ props.side === 'long' ? '多头' : '空头' }}全部）
        </v-card-title>
        <v-card-text>
          <v-alert type="warning" variant="tonal" density="compact" class="mb-3">
            将对下列 <strong>{{ batchReverseItems.length }}</strong> 个仓位逐一<strong>先全平、再反向开仓</strong>
            （限价 post-only，有 USDC 合约自动走 USDC）。执行中不可撤销。
          </v-alert>
          <div
            v-for="item in batchReverseItems"
            :key="item.symbol"
            class="d-flex align-center ga-3 py-1"
          >
            <span class="batch-reverse__symbol">{{ item.symbol }}</span>
            <v-chip :color="directionTone(item.fromSide).color" size="x-small" label>
              {{ directionTone(item.fromSide).label }}
            </v-chip>
            <v-icon size="small" class="text-medium-emphasis">mdi-arrow-right-bold</v-icon>
            <v-chip :color="directionTone(item.toSide).color" size="x-small" label>
              {{ directionTone(item.toSide).label }}
            </v-chip>
            <v-spacer></v-spacer>
            <span class="text-caption text-medium-emphasis">现价 ${{ formatFixed(item.notional, 2) }}</span>
            <v-text-field
              v-model.number="item.value"
              type="number"
              min="1"
              step="1"
              label="目标价值 (USD)"
              variant="outlined"
              density="compact"
              hide-details
              class="batch-reverse__value"
            ></v-text-field>
          </div>
          <div class="text-caption text-medium-emphasis mt-2">
            目标价值已按当前名义价值预填，可逐项调整；后端会逐币校验（如该币多空并存则该项跳过并报错，不影响其它币）。
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="batchReverseDialog = false">取消</v-btn>
          <v-btn
            color="warning"
            variant="tonal"
            :disabled="!batchReverseValid || uiStore.isRunning"
            @click="confirmBatchReverse"
          >
            确认批量反手
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import type { Position } from '@/models/types'
import { useUiStore } from '@/stores/uiStore'
import { usePositionStore } from '@/stores/positionStore'
import { directionTone, pnlClass } from '@/utils/tone'
import { formatAmount, formatFixed, formatQuantity, formatSigned, formatSignedPercent } from '@/utils/format'
import { ENDPOINTS } from '@/services/endpoints'
import EmptyState from '@/components/EmptyState.vue'

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
const display = useDisplay()

// ---- 断点：xs 卡片化 / sm 表格(45vh) / md+ 表格(calc 高度) ----
const isXs = computed(() => display.xs.value)
const isSm = computed(() => display.sm.value)

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

// --- xs 卡片：展开明细（开仓均价 / 数量） ---
const cardExpanded = ref<Set<string>>(new Set())
const toggleCardExpand = (fullSymbol: string): void => {
  const next = new Set(cardExpanded.value)
  if (next.has(fullSymbol)) {
    next.delete(fullSymbol)
  } else {
    next.add(fullSymbol)
  }
  cardExpanded.value = next
}
const entryPriceText = (value: number): string => formatQuantity(value)

// --- xs 卡片：批量选择（与 v-data-table 共用 positionStore.selectedPositions） ---
const selectMode = ref(false)
const isCardSelected = (item: Position): boolean =>
  positionStore.selectedPositions.includes(item.full_symbol)
const toggleCardSelect = (item: Position): void => {
  positionStore.selectedPositions = isCardSelected(item)
    ? positionStore.selectedPositions.filter((s) => s !== item.full_symbol)
    : [...positionStore.selectedPositions, item.full_symbol]
}

/**
 * 卡片点击：平时展开明细；多选态下改为「选中/取消」。
 * 多选时用户的手指落点就是整张卡，若仍走展开，勾选框 40px 的命中区等于逼人点小靶。
 */
const handleCardClick = (item: Position): void => {
  if (selectMode.value) {
    toggleCardSelect(item)
  } else {
    toggleCardExpand(item.full_symbol)
  }
}

/** 关掉多选时清掉本表的选中项：否则「平掉选中」会带着看不见的勾选继续可用 */
const clearTableSelection = (): void => {
  const current = new Set(props.positions.map((p) => p.full_symbol))
  positionStore.selectedPositions = positionStore.selectedPositions.filter(
    (symbol) => !current.has(symbol),
  )
}
watch(selectMode, (on) => {
  if (!on) clearTableSelection()
})

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
    ENDPOINTS.tradingManual,
    { items: [{ symbol: target.full_symbol, action: 'reverse', value: Number(reverseValue.value) }] },
    `反手交易 ${target.full_symbol}`,
    1,
  )
  reverseDialog.value = false
}

// --- 批量反手（本表 side 全部仓位：先全平、再反向开仓，一次请求下发全部 items） ---
type BatchReverseItem = { symbol: string; fromSide: 'long' | 'short'; toSide: 'long' | 'short'; notional: number; value: number }
const batchReverseDialog = ref(false)
const batchReverseItems = ref<BatchReverseItem[]>([])

const batchReverseValid = computed(() =>
  batchReverseItems.value.length > 0 && batchReverseItems.value.every((item) => item.value > 0),
)

const handleReverseAll = () => {
  batchReverseItems.value = props.positions.map((position) => ({
    symbol: position.full_symbol,
    fromSide: position.side,
    toSide: position.side === 'long' ? 'short' : 'long',
    notional: position.notional,
    value: Math.max(1, Math.round(position.notional * 100) / 100),
  }))
  batchReverseDialog.value = true
}

const confirmBatchReverse = () => {
  if (!batchReverseValid.value) return
  const count = batchReverseItems.value.length
  uiStore.launchTask(
    ENDPOINTS.tradingManual,
    {
      items: batchReverseItems.value.map((item) => ({
        symbol: item.symbol,
        action: 'reverse',
        value: Number(item.value),
      })),
    },
    `批量反手 ${props.side === 'long' ? '多头' : '空头'} ×${count}`,
    1,
  )
  batchReverseDialog.value = false
}

const headers: TDataTableHeader[] = [
  { title: '合约', key: 'full_symbol', sortable: true, width: '20%' },
  { title: '名义价值', key: 'notional', sortable: true, width: '15%' },
  { title: '浮动盈亏', key: 'pnl', sortable: true, width: '15%' },
  { title: '回报率', key: 'pnl_percentage', sortable: true, width: '15%' },
  { title: '开仓均价', key: 'entry_price', width: '15%' },
  { title: '操作', key: 'actions', sortable: false, align: 'end', width: '12%' },
]
</script>

<style scoped>
/* 表头不换行（sm+ 表格） */
:deep(.position-table .v-data-table__th) {
  white-space: nowrap !important;
}

/* 表格里的勾选框同理：未选中态原来继承中等强调灰 + 细描边，在表头浅底上几乎看不见。
   只调未选中的 blank 图标，选中态的主色标记保持原样。 */
.position-table :deep(.v-selection-control__input > .v-icon) {
  font-size: 22px;
}
.position-table :deep(.v-icon.mdi-checkbox-blank-outline) {
  color: rgb(var(--v-theme-on-surface)) !important;
  opacity: 0.75;
}

/* 手机端：操作栏按钮允许换行，避免被裁切 */
.toolbar-wrap :deep(.v-toolbar__content) {
  flex-wrap: wrap;
  height: auto !important;
  padding: 6px 8px !important;
  gap: 6px;
}

/* xs 卡片：只写结构样式，配色全部走主题令牌 */
.position-card {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
  padding: 10px 12px;
  min-width: 0;
  cursor: pointer;
}
.position-card__symbol {
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.position-card__pnl {
  font-size: 16px;
  font-weight: 600;
}
.position-card__sub {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
  color: rgba(var(--v-theme-on-surface), 0.72);
}
/* 多选态下整卡是勾选命中区，给个手型提示 */
.position-card--selectable {
  cursor: pointer;
}
/* 勾选框（用户反馈「看不清」）：Vuetify 未选中态继承卡片的中等强调灰 + 1px 细描边图标，
   白卡上几乎不可见。这里做三件事：放大图形、描边提到 0.55 不透明度的正文色、
   命中区从 compact 的 28 抬到 40。选中态仍交给 color="primary"，不覆写。 */
.position-card__check {
  flex: 0 0 auto;
  margin-left: -6px; /* 抵消 40px 命中区带来的视觉缩进 */
}
.position-card__check :deep(.v-selection-control) {
  --v-selection-control-size: 40px;
  flex: 0 0 auto; /* 默认 flex:1 0 会挤占币种名的宽度 */
}
.position-card__check :deep(.v-selection-control__input > .v-icon) {
  font-size: 26px;
}
.position-card__check :deep(.v-icon.mdi-checkbox-blank-outline) {
  /* 未选中框：给足正文色（浅色 #3F4750 on 白 ≈ 10:1）。
     Vuetify 未选中态继承卡片文字色且图标是 1px 描边，实际渲染出来的框
     在手机上几乎不可见；这里只针对 blank 图标提色，选中态仍是 primary。 */
  color: rgb(var(--v-theme-on-surface)) !important;
  opacity: 0.75;
}
/* 选中必须整卡可见：只靠小勾变化，用户扫一眼分不清选了哪几个 */
.position-card--selected {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.06);
  box-shadow: inset 0 0 0 1px rgb(var(--v-theme-primary));
}
/* 展开按钮：多选态下卡片点击已改为选中，展开只剩这个入口，命中区给到 32 */
.position-card__expand {
  flex: 0 0 auto;
  width: 32px !important;
  height: 32px !important;
  margin: -6px -8px -6px 0;
}
/* 底部按钮 40px 高（规格要求的手机触控高度） */
.position-card__btn {
  min-height: 40px;
}
/* 开关在手机工具栏里收紧，避免把「批量平仓」挤下去 */
.mobile-switch {
  flex: 0 0 auto;
  transform: translateY(-4px);
}

/* 批量反手弹窗：币种不挤压、价值输入固定宽 */
.batch-reverse__symbol {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.batch-reverse__value {
  flex: 0 0 130px;
}
</style>
