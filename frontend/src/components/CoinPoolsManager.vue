<!-- frontend/src/components/CoinPoolsManager.vue (最终 Vue-Multiselect 版) -->
<template>
  <div>
    <v-row>
      <v-col cols="12" md="6">
        <v-card variant="tonal" class="pa-4">
          <div class="d-flex align-center mb-2">
            <span class="text-subtitle-1 font-weight-medium">做多币种备选池 ({{ longPool.length }})</span>
            <v-tooltip location="top">
              <template v-slot:activator="{ props }">
                <v-btn icon="mdi-select-all" variant="text" size="small" v-bind="props" @click="selectAllCoins('long')"></v-btn>
              </template>
              <span>全选可用</span>
            </v-tooltip>
          </div>

          <Multiselect
            v-model="longPool"
            :options="availableForLongPool"
            mode="tags"
            placeholder="选择或搜索币种"
            :searchable="true"
            :close-on-select="false"
          />

        </v-card>
      </v-col>

      <v-col cols="12" md="6">
        <v-card variant="tonal" class="pa-4">
          <div class="d-flex align-center mb-2">
            <span class="text-subtitle-1 font-weight-medium">做空币种备选池 ({{ shortPool.length }})</span>
             <v-tooltip location="top">
              <template v-slot:activator="{ props }">
                <v-btn icon="mdi-select-all" variant="text" size="small" v-bind="props" @click="selectAllCoins('short')"></v-btn>
              </template>
              <span>全选可用</span>
            </v-tooltip>
          </div>

          <Multiselect
            v-model="shortPool"
            :options="availableForShortPool"
            mode="tags"
            placeholder="选择或搜索币种"
            :searchable="true"
            :close-on-select="false"
          />

        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<!--
  为了让 vue-multiselect 的样式能融入 Vuetify 暗色主题，
  我们需要一些全局CSS。我们把它放在这里，并移除 scoped。
-->
<style>
@import "vue-multiselect/dist/vue-multiselect.css";

:root {
  --ms-bg: #2E2E2E;
  --ms-border-color: #4a4a4a;
  --ms-ring-color: #5897fb;
  --ms-placeholder-color: rgba(255, 255, 255, 0.5);
  --ms-option-bg-pointed: #4a4a4a;
  --ms-option-bg-selected: #1867C0;
  --ms-option-bg-selected-pointed: #1E88E5;
  --ms-tag-bg: #1867C0;
  --ms-tag-color: #FFFFFF;
  --ms-tag-radius: 4px;
  --ms-dropdown-bg: #2E2E2E;
  --ms-dropdown-border-color: #4a4a4a;
  --ms-font-size: 0.875rem;
  --ms-line-height: 1.25rem;
}

.multiselect-tags-search {
  background: var(--ms-bg) !important;
  color: white !important;
}
</style>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUiStore } from '@/stores/uiStore';
import apiClient from '@/services/api';
import Multiselect from 'vue-multiselect';

const settingsStore = useSettingsStore();
const uiStore = useUiStore();

const longPool = ref([...settingsStore.availableLongCoins]);
const shortPool = ref([...settingsStore.availableShortCoins]);

const allAvailableCoins = computed(() => [...new Set(settingsStore.availableCoins)].sort());

// vue-multiselect 需要字符串数组作为 options
const availableForLongPool = computed(() => {
  const shortSet = new Set(shortPool.value);
  return allAvailableCoins.value.filter(coin => !shortSet.has(coin));
});

const availableForShortPool = computed(() => {
  const longSet = new Set(longPool.value);
  return allAvailableCoins.value.filter(coin => !longSet.has(coin));
});

const selectAllCoins = (poolType: 'long' | 'short') => {
  if (poolType === 'long') {
    longPool.value = availableForLongPool.value;
  } else if (poolType === 'short') {
    shortPool.value = availableForShortPool.value;
  }
};

const savePools = async () => {
  try {
    await apiClient.post('/api/settings/update-coin-pools', {
      long_coins_pool: longPool.value,
      short_coins_pool: shortPool.value
    });
    settingsStore.updateAvailablePools(longPool.value, shortPool.value);
    uiStore.logStore.addLog({ message: '币种备选池已成功保存。', level: 'success', timestamp: new Date().toLocaleTimeString() });
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message;
    uiStore.logStore.addLog({ message: `保存币种备选池失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
  }
};

watch(
  () => settingsStore.availableLongCoins,
  (newVal) => { longPool.value = [...newVal]; }, { deep: true }
);

watch(
  () => settingsStore.availableShortCoins,
  (newVal) => { shortPool.value = [...newVal]; }, { deep: true }
);

defineExpose({
  savePools
});
</script>
