<!-- frontend/src/components/PositionsPanel.vue -->
<!-- 多头 + 空头仓位表的组合面板：Dashboard 与 Trading 共用，数据自取自 positionStore -->
<template>
  <v-row>
    <v-col cols="12">
      <PositionsTable
        title="▲ 多头仓位"
        side="long"
        :positions="positionStore.longPositions"
        :loading="positionStore.loading"
        @refresh="positionStore.fetchPositions()"
      />
    </v-col>
    <v-col cols="12">
      <PositionsTable
        title="▼ 空头仓位"
        side="short"
        :positions="positionStore.shortPositions"
        :loading="positionStore.loading"
        @refresh="positionStore.fetchPositions()"
      />
    </v-col>
  </v-row>
</template>

<script setup lang="ts">
import { usePositionStore } from '@/stores/positionStore'
import PositionsTable from '@/components/PositionsTable.vue'

const positionStore = usePositionStore()

defineExpose({
  refresh: () => positionStore.fetchPositions(),
})
</script>
