<!-- frontend/src/components/GeneralCloseSettings.vue -->
<template>
  <v-card v-if="settingsStore.settings">
    <v-card-title class="text-subtitle-1">通用平仓设置</v-card-title>
    <v-divider></v-divider>
    <v-card-text>
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
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { useSettingsStore } from '@/stores/settingsStore.ts';
const settingsStore = useSettingsStore();
</script>
