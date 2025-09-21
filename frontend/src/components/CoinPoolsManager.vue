<!-- frontend/src/components/CoinPoolsManager.vue (最终正确版) -->
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

          <v-select
            v-model="longPool"
            :items="filteredLongPoolItems"
            label="从总池中选择做多备选币种"
            multiple chips closable-chips clearable variant="outlined" hide-details
            item-title="title" item-value="value" :menu-props="{ maxHeight: '300px' }"
            hide-selected
          >
            <template v-slot:prepend-item>
              <v-text-field
                v-model="longSearch"
                placeholder="搜索币种..."
                variant="underlined"
                density="compact"
                hide-details
                class="px-4 mb-2"
                @click.stop
              ></v-text-field>
              <v-divider></v-divider>
            </template>

            <template v-slot:item="{ item, props }">
              <v-list-item v-bind="props" class="pl-0">
                <template v-slot:prepend>
                  <v-checkbox-btn :model-value="longPool.includes(item.value)" readonly class="mr-2"></v-checkbox-btn>
                </template>
              </v-list-item>
            </template>
          </v-select>
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

          <v-select
            v-model="shortPool"
            :items="filteredShortPoolItems"
            label="从总池中选择做空备选币种"
            multiple chips closable-chips clearable variant="outlined" hide-details
            item-title="title" item-value="value" :menu-props="{ maxHeight: '300px' }"
            hide-selected
          >
            <template v-slot:prepend-item>
              <v-text-field
                v-model="shortSearch"
                placeholder="搜索币种..."
                variant="underlined"
                density="compact"
                hide-details
                class="px-4 mb-2"
                @click.stop
              ></v-text-field>
              <v-divider></v-divider>
            </template>

            <template v-slot:item="{ item, props }">
              <v-list-item v-bind="props" class="pl-0">
                <template v-slot:prepend>
                  <v-checkbox-btn :model-value="shortPool.includes(item.value)" readonly class="mr-2"></v-checkbox-btn>
                </template>
              </v-list-item>
            </template>
          </v-select>

        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUiStore } from '@/stores/uiStore';
import apiClient from '@/services/api';

const settingsStore = useSettingsStore();
const uiStore = useUiStore();

const longPool = ref([...settingsStore.availableLongCoins]);
const shortPool = ref([...settingsStore.availableShortCoins]);

const longSearch = ref('');
const shortSearch = ref('');

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

const filteredLongPoolItems = computed(() => {
  if (!longSearch.value) {
    return availableForLongPool.value;
  }
  return availableForLongPool.value.filter(item =>
    item.title.toLowerCase().includes(longSearch.value.toLowerCase())
  );
});

const filteredShortPoolItems = computed(() => {
  if (!shortSearch.value) {
    return availableForShortPool.value;
  }
  return availableForShortPool.value.filter(item =>
    item.title.toLowerCase().includes(shortSearch.value.toLowerCase())
  );
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
