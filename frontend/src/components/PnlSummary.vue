<!-- frontend/src/components/PnlSummary.vue (完整代码) -->
<template>
  <v-card>
    <v-card-title class="text-subtitle-1">仓位概览</v-card-title>
    <v-divider></v-divider>
    <v-card-text>
      <v-row no-gutters class="text-center">
        <!-- 多头信息 -->
        <v-col>
          <div class="text-caption">多头总价值</div>
          <div class="text-h6 font-weight-bold text-success">
            ${{ pnlStore.longNotional.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}
          </div>
        </v-col>
        <v-col>
          <div class="text-caption">多头总盈亏</div>
          <div class="text-h6 font-weight-bold" :class="pnlStore.longPnl >= 0 ? 'text-success' : 'text-error'">
            {{ pnlStore.longPnl >= 0 ? '+' : '' }}{{ pnlStore.longPnl.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}
          </div>
        </v-col>

        <v-divider vertical class="mx-2"></v-divider>

        <!-- 空头信息 -->
        <v-col>
          <div class="text-caption">空头总价值</div>
          <div class="text-h6 font-weight-bold text-error">
            ${{ pnlStore.shortNotional.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}
          </div>
        </v-col>
        <v-col>
          <div class="text-caption">空头总盈亏</div>
          <div class="text-h6 font-weight-bold" :class="pnlStore.shortPnl >= 0 ? 'text-success' : 'text-error'">
             {{ pnlStore.shortPnl.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}
          </div>
        </v-col>

        <v-divider vertical class="mx-2"></v-divider>

        <!-- 净值信息 -->
        <v-col>
          <div class="text-caption">净总盈亏</div>
          <div class="text-h6 font-weight-bold" :class="pnlStore.totalPnl >= 0 ? 'text-success' : 'text-error'">
             {{ pnlStore.totalPnl >= 0 ? '+' : '' }}{{ pnlStore.totalPnl.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}
          </div>
        </v-col>
      </v-row>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { usePositionStore } from '@/stores/positionStore';

const pnlStore = usePositionStore();
</script>
