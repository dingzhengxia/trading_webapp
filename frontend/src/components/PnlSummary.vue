<!-- frontend/src/components/PnlSummary.vue -->
<template>
  <v-card>
    <v-card-title class="text-subtitle-1">盈亏统计 (PNL Summary)</v-card-title>
    <v-divider></v-divider>
    <v-card-text>
      <v-row no-gutters class="text-center">
        <v-col>
          <div class="text-caption">多头总盈亏</div>
          <div class="text-h6 font-weight-bold" :class="pnlStore.longPnl >= 0 ? 'text-success' : 'text-error'">
            {{ pnlStore.longPnl.toFixed(2) }}
          </div>
        </v-col>
        <v-divider vertical></v-divider>
        <v-col>
          <div class="text-caption">空头总盈亏</div>
          <div class="text-h6 font-weight-bold" :class="pnlStore.shortPnl >= 0 ? 'text-success' : 'text-error'">
            {{ pnlStore.shortPnl.toFixed(2) }}
          </div>
        </v-col>
        <v-divider vertical></v-divider>
        <v-col>
          <div class="text-caption">净总盈亏</div>
          <div class="text-h6 font-weight-bold" :class="pnlStore.totalPnl >= 0 ? 'text-success' : 'text-error'">
            {{ pnlStore.totalPnl.toFixed(2) }}
          </div>
        </v-col>
      </v-row>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { usePositionStore } from '@/stores/positionStore';

const pnlStore = usePositionStore(); // PNL 计算逻辑已移至 positionStore
</script>
