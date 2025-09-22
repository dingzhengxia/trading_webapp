<!-- frontend/src/components/CloseDialog.vue (最终修正版) -->
<template>
  <v-dialog v-model="uiStore.showCloseDialog" max-width="400px" persistent>
    <v-card v-if="uiStore.closeTarget">
      <v-card-title class="text-h5 text-center pt-4">{{ dialogTitle }}</v-card-title>
      <v-card-text>
        <div class="text-center">
          <div class="text-caption text-grey">请选择要平仓的仓位比例:</div>
        </div>

        <div class="text-center mt-4 mb-2">
          <div class="text-caption">预计平仓价值</div>
          <div class="text-h4 font-weight-bold text-amber-accent-3 my-1">
            ${{
              closeValue.toLocaleString('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })
            }}
          </div>
        </div>

        <v-slider
          v-model="closeRatio"
          :step="1"
          color="primary"
          class="my-4 align-center"
          hide-details
        >
          <template v-slot:thumb-label="{ modelValue }">
            <span class="font-weight-bold">{{ Math.ceil(modelValue) }}%</span>
          </template>
        </v-slider>

        <v-text-field
          v-model.number="closeRatio"
          type="number"
          variant="outlined"
          density="compact"
          hide-details
          suffix="%"
          class="mx-auto"
          style="max-width: 120px"
        ></v-text-field>
      </v-card-text>

      <!-- --- 核心修正：修复按钮布局 --- -->
      <v-card-actions class="pa-4">
        <v-spacer></v-spacer>
        <v-btn color="grey" variant="text" @click="closeDialog" class="mr-2"> 取消 </v-btn>
        <v-btn
          color="red-darken-1"
          variant="tonal"
          @click="executeClose"
          :disabled="closeRatio <= 0 || uiStore.isRunning"
        >
          确认平仓 {{ closeRatio }}%
        </v-btn>
      </v-card-actions>
      <!-- --- 修改结束 --- -->
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useUiStore } from '@/stores/uiStore'
import { usePositionStore } from '@/stores/positionStore'
import type { CloseTarget } from '@/stores/uiStore'

const uiStore = useUiStore()
const positionStore = usePositionStore()
const closeRatio = ref(100)

const dialogTitle = computed(() => {
  const target = uiStore.closeTarget
  if (!target) return '确认平仓'
  if (target.type === 'single') return `平仓: ${target.position.symbol}`
  if (target.type === 'selected') return `平掉选中的 ${target.positions.length} 个仓位`
  if (target.type === 'by_side') {
    if (target.side === 'long') return '平掉所有多头'
    if (target.side === 'short') return '平掉所有空头'
    if (target.side === 'all') return '平掉全部仓位'
  }
  return '确认平仓'
})

const totalNotionalToClose = computed(() => {
  const target = uiStore.closeTarget as CloseTarget | null
  if (!target) return 0

  switch (target.type) {
    case 'single':
      return target.position.notional
    case 'selected':
      return target.positions.reduce((sum, p) => sum + p.notional, 0)
    case 'by_side':
      if (target.side === 'long') return positionStore.longNotional
      if (target.side === 'short') return positionStore.shortNotional
      return positionStore.longNotional + positionStore.shortNotional
    default:
      return 0
  }
})

const closeValue = computed(() => {
  const ratio = Math.max(0, Math.min(100, Number(closeRatio.value) || 0))
  return totalNotionalToClose.value * (ratio / 100)
})

watch(closeRatio, (newValue) => {
  const numValue = Number(newValue)
  if (isNaN(numValue) || numValue < 0) {
    closeRatio.value = 0
  } else if (numValue > 100) {
    closeRatio.value = 100
  }
})

const closeDialog = () => {
  uiStore.showCloseDialog = false
}

watch(
  () => uiStore.showCloseDialog,
  (isOpen) => {
    if (isOpen) {
      closeRatio.value = 100
    }
  },
)

const executeClose = () => {
  const target = uiStore.closeTarget
  if (!target || uiStore.isRunning || closeRatio.value <= 0) return

  const ratio = closeRatio.value / 100
  let endpoint = ''
  let payload: any = {}
  let taskName = ''
  let totalTasks = 0

  if (target.type === 'single') {
    endpoint = '/api/positions/close'
    payload = { full_symbol: target.position.full_symbol, ratio }
    taskName = `平仓 ${target.position.symbol}`
    totalTasks = 1
  } else if (target.type === 'by_side') {
    endpoint = '/api/positions/close-by-side'
    payload = { side: target.side, ratio }
    taskName = `批量平仓-${target.side}`
    if (target.side === 'long') totalTasks = positionStore.longPositions.length
    else if (target.side === 'short') totalTasks = positionStore.shortPositions.length
    else totalTasks = positionStore.positions.length
  } else if (target.type === 'selected') {
    endpoint = '/api/positions/close-multiple'
    payload = { full_symbols: target.positions.map((p) => p.full_symbol), ratio }
    taskName = `平掉选中`
    totalTasks = payload.full_symbols.length
  }

  closeDialog()
  uiStore.launchTask(endpoint, payload, taskName, totalTasks)
}
</script>
