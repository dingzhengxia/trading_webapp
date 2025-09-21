<!-- frontend/src/components/CoinPoolsManager.vue (完整代码) -->
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

          <MultiSelect
            v-model="longPool"
            :options="availableForLongPool"
            optionLabel="title"
            optionValue="value"
            placeholder="从总池中选择做多备选币种"
            filter
            class="w-full prime-multiselect"
            :maxSelectedLabels="3"
            selectedItemsLabel="{0} 个币种已选择"
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

          <MultiSelect
            v-model="shortPool"
            :options="availableForShortPool"
            optionLabel="title"
            optionValue="value"
            placeholder="从总池中选择做空备选币种"
            filter
            class="w-full prime-multiselect"
            :maxSelectedLabels="3"
            selectedItemsLabel="{0} 个币种已选择"
          />

        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<style>
/*
  全局样式，适配 PrimeVue 组件以更好地融入 Vuetify 暗色主题。
  移除 scoped 以便样式能正确应用到 PrimeVue 的弹出菜单。
*/
.prime-multiselect {
  width: 100%;
}
.p-multiselect {
  background-color: #2E2E2E !important;
  border: 1px solid #4a4a4a !important;
  box-shadow: none !important;
}
.p-multiselect:not(.p-disabled):hover {
  border-color: #7a7a7a !important;
}
.p-multiselect-label {
 color: rgba(255, 255, 255, 0.7) !important;
}
.p-multiselect-panel {
  background-color: #2E2E2E !important;
  border: 1px solid #4a4a4a !important;
}
.p-multiselect-header {
   background-color: #2E2E2E !important;
}
.p-multiselect-item:hover {
  background-color: #4a4a4a !important;
}
.p-inputtext {
  background-color: #212121 !important;
  color: white !important;
}
</style>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUiStore } from '@/stores/uiStore';
import apiClient from '@/services/api';
import MultiSelect from 'primevue/multiselect';

const settingsStore = useSettingsStore();
const uiStore = useUiStore();

const longPool = ref([...settingsStore.availableLongCoins]);
const shortPool = ref([...settingsStore.availableShortCoins]);

const allAvailableCoins = computed(() => [...new Set(settingsStore.availableCoins)].sort());
const mapToSelectItems = (coins: string[]) => coins.map(coin => ({ title: coin, value: coin }));

const availableForLongPool = computed(() => {
  const shortSet = new Set(shortPool.value);
  const available = allAvailableCoins.value.filter(coin => !shortSet.has(coin));
  return mapToSelectItems(available);
});

const availableForShortPool = computed(() => {
  const longSet = new Set(longPool.value);
  const available = allAvailableCoins.value.filter(coin => !longSet.has(coin));
  return mapToSelectItems(available);
});

const selectAllCoins = (poolType: 'long' | 'short') => {
  if (poolType === 'long') {
    longPool.value = availableForLongPool.value.map(item => item.value);
  } else if (poolType === 'short') {
    shortPool.value = availableForShortPool.value.map(item => item.value);
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
  (newVal) => {
    longPool.value = [...newVal];
  },
  { deep: true }
);

watch(
  () => settingsStore.availableShortCoins,
  (newVal) => {
    shortPool.value = [...newVal];
  },
  { deep: true }
);

defineExpose({
  savePools
});
</script>
