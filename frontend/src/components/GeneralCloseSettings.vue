<template>
  <v-card v-if="settingsStore.settings">
    <v-card-title class="text-subtitle-1">通用平仓设置</v-card-title>
    <v-divider></v-divider>
    <v-card-text>
        <v-row dense align="center">
          <!-- 平仓参数 -->
          <v-col cols="12" md="8">
            <v-row dense>
              <v-col cols="12" sm="6">
                <v-text-field
                  label="平仓Maker重试次数"
                  v-model.number="settingsStore.settings.close_maker_retries"
                  type="number"
                  variant="outlined"
                  density="compact"
                  hide-details
                />
              </v-col>
              <v-col cols="12" sm="6">
                <v-text-field
                  label="平仓订单超时 (秒)"
                  v-model.number="settingsStore.settings.close_order_fill_timeout_seconds"
                  type="number"
                  variant="outlined"
                  density="compact"
                  hide-details
                />
              </v-col>
            </v-row>
          </v-col>

          <!-- 平掉选中按钮 -->
          <v-col cols="12" md="4" class="text-md-right mt-4 mt-md-0">
            <v-btn
              color="warning"
              variant="tonal"
              @click="openCloseSelectedDialog"
              :disabled="positionStore.selectedPositions.length === 0"
              prepend-icon="mdi-close-box-multiple"
              block
            >
              平掉选中 ({{ positionStore.selectedPositions.length }})
            </v-btn>
          </v-col>
        </v-row>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { useSettingsStore } from '@/stores/settingsStore';
import { usePositionStore } from '@/stores/positionStore';
import { useUiStore } from '@/stores/uiStore';

const settingsStore = useSettingsStore();
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
</script>
