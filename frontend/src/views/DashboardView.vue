<template>
  <div>
    <!-- 第一行：盈亏统计 -->
    <v-row>
      <v-col cols="12">
        <PnlSummary />
      </v-col>
    </v-row>

    <!-- 第二行：全局操作栏 (平掉选中) -->
    <v-row>
      <v-col cols="12">
        <v-card>
          <v-card-text class="d-flex justify-center align-center pa-2">
            <v-btn
              color="warning"
              variant="tonal"
              @click="openCloseSelectedDialog"
              :disabled="positionStore.selectedPositions.length === 0"
              prepend-icon="mdi-close-box-multiple"
              class="mx-auto"
            >
              平掉选中 ({{ positionStore.selectedPositions.length }})
            </v-btn>
          </v-card-text>
        </v-card>
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
import { useUiStore } from '@/stores/uiStore';
import PositionsTable from '@/components/PositionsTable.vue';
import PnlSummary from '@/components/PnlSummary.vue';

const positionStore = usePositionStore();
const uiStore = useUiStore();

const openCloseSelectedDialog = () => {
  const selected = positionStore.positions.filter(p =>
    positionStore.selectedPositions.includes(p.full_symbol)
  );
  if (selected.length > 0) {
    uiStore.openCloseDialog({ type: 'selected', positions: selected });
  }
};

onMounted(() => {
  positionStore.fetchPositions();
});
</script>
