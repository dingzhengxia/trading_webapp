<template>
  <div>
    <v-row>
      <v-col cols="12">
        <PnlSummary />
      </v-col>
    </v-row>

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

    <v-row justify="center" class="my-2">
      <v-col cols="auto">
        <v-btn
          color="warning"
          variant="tonal"
          @click="openCloseSelectedDialog"
          :disabled="positionStore.selectedPositions.length === 0"
          prepend-icon="mdi-close-box-multiple"
        >
          平掉选中 ({{ positionStore.selectedPositions.length }})
        </v-btn>
      </v-col>
    </v-row>

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

    <v-row>
      <v-col cols="12">
        <GeneralCloseSettings />
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
import GeneralCloseSettings from '@/components/GeneralCloseSettings.vue';

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
