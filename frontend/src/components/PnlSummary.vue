<!-- frontend/src/components/PnlSummary.vue -->
<!-- 盈亏汇总：三个数字统一走 pnlTone —— 正负号是主要信息，颜色只是强化 -->
<template>
  <v-card variant="flat" class="pnl-card">
    <div class="d-flex align-stretch">
      <div class="pnl-cell">
        <div class="pnl-label">
          多头总盈亏
          <v-icon size="12" class="ml-1" color="long">mdi-arrow-up-bold</v-icon>
        </div>
        <div class="pnl-value num" :class="longTone.textClass">{{ longTone.text }}</div>
      </div>

      <v-divider vertical />

      <div class="pnl-cell">
        <div class="pnl-label">
          空头总盈亏
          <v-icon size="12" class="ml-1" color="short">mdi-arrow-down-bold</v-icon>
        </div>
        <div class="pnl-value num" :class="shortTone.textClass">{{ shortTone.text }}</div>
      </div>

      <v-divider vertical />

      <div class="pnl-cell">
        <div class="pnl-label">净总盈亏</div>
        <div class="pnl-value num" :class="totalTone.textClass">{{ totalTone.text }}</div>
      </div>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { usePositionStore } from '@/stores/positionStore'
import { pnlTone } from '@/utils/tone'

const pnlStore = usePositionStore()

const longTone = computed(() => pnlTone(pnlStore.longPnl))
const shortTone = computed(() => pnlTone(pnlStore.shortPnl))
const totalTone = computed(() => pnlTone(pnlStore.totalPnl))
</script>

<style scoped>
.pnl-card {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
}
.pnl-cell {
  flex: 1 1 0;
  padding: 14px 18px;
  min-width: 0;
}
.pnl-label {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  margin-bottom: 4px;
  display: flex;
  align-items: center;
}
.pnl-value {
  font-size: 22px;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: -0.01em;
}
</style>
