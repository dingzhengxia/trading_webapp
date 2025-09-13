<template>
  <div>
    <!-- 第一行：盈亏统计 -->
    <v-row>
      <v-col cols="12">
        <PnlSummary />
      </v-col>
    </v-row>

    <!-- 第二行：通用平仓设置 (现在包含了“平掉选中”按钮) -->
    <v-row>
      <v-col cols="12">
        <GeneralCloseSettings />
      </v-col>
    </v-row>

    <!-- 第三行：多头仓位 -->
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
    </v-row>

    <!-- 第四行：空头仓位 -->
    <v-row>
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
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
import { usePositionStore } from '@/stores/positionStore';
import PositionsTable from '@/components/PositionsTable.vue';
import PnlSummary from '@/components/PnlSummary.vue';
import GeneralCloseSettings from '@/components/GeneralCloseSettings.vue';

const positionStore = usePositionStore();

onMounted(() => {
  positionStore.fetchPositions();
});
</script>
