<!-- frontend/src/views/DashboardView.vue -->
<template>
  <div>
    <!-- 盈亏统计 -->
    <v-row>
      <v-col cols="12">
        <PnlSummary />
      </v-col>
    </v-row>

    <!-- 多空仓位（共享面板） -->
    <PositionsPanel ref="panel" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import PnlSummary from '@/components/PnlSummary.vue'
import PositionsPanel from '@/components/PositionsPanel.vue'

const panel = ref<InstanceType<typeof PositionsPanel> | null>(null)

onMounted(() => {
  panel.value?.refresh()
})
</script>
