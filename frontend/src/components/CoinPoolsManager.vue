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
              <span>全选</span>
            </v-tooltip>
          </div>
          <v-autocomplete
            v-model="longPool"
            :items="mapToSelectItems(availableCoinsForLongPool)"
            label="从总池中选择做多备选币种"
            multiple chips closable-chips clearable variant="outlined" hide-details
            item-title="title" item-value="value" :menu-props="{ maxHeight: '300px' }"
          >
            <template v-slot:item="{ item, props }">
              <v-list-item v-bind="props" class="pl-0">
                <template v-slot:prepend>
                  <v-checkbox-btn :model-value="longPool.includes(item.value)" readonly class="mr-2"></v-checkbox-btn>
                </template>
              </v-list-item>
            </template>
          </v-autocomplete>
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
              <span>全选</span>
            </v-tooltip>
          </div>
          <v-autocomplete
            v-model="shortPool"
            :items="mapToSelectItems(availableCoinsForShortPool)"
            label="从总池中选择做空备选币种"
            multiple chips closable-chips clearable variant="outlined" hide-details
            item-title="title" item-value="value" :menu-props="{ maxHeight: '300px' }"
          >
            <template v-slot:item="{ item, props }">
              <v-list-item v-bind="props" class="pl-0">
                <template v-slot:prepend>
                  <v-checkbox-btn :model-value="shortPool.includes(item.value)" readonly class="mr-2"></v-checkbox-btn>
                </template>
              </v-list-item>
            </template>
          </v-autocomplete>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUiStore } from '@/stores/uiStore';
import apiClient from '@/services/api';

const settingsStore = useSettingsStore();
const uiStore = useUiStore();

const longPool = ref<string[]>([]);
const shortPool = ref<string[]>([]);

const allAvailableCoins = computed(() => [...new Set(settingsStore.availableCoins)].sort());
const mapToSelectItems = (coins: string[]) => coins.map(coin => ({ title: coin, value: coin }));

// 互斥逻辑的核心: 计算属性
const availableCoinsForLongPool = computed(() => {
  return allAvailableCoins.value.filter(coin => !shortPool.value.includes(coin));
});

const availableCoinsForShortPool = computed(() => {
  return allAvailableCoins.value.filter(coin => !longPool.value.includes(coin));
});

const selectAllCoins = (poolType: 'long' | 'short') => {
  if (poolType === 'long') {
    longPool.value = [...allAvailableCoins.value].filter(coin => !shortPool.value.includes(coin));
  } else if (poolType === 'short') {
    shortPool.value = [...allAvailableCoins.value].filter(coin => !longPool.value.includes(coin));
  }
};

const savePools = async () => {
  try {
    await apiClient.post('/api/settings/update-coin-pools', {
      long_coins_pool: longPool.value,
      short_coins_pool: shortPool.value
    });
    await settingsStore.fetchSettings();
    uiStore.logStore.addLog({ message: '币种备选池已成功保存。', level: 'success', timestamp: new Date().toLocaleTimeString() });
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message;
    uiStore.logStore.addLog({ message: `保存币种备选池失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
  }
};

// 在组件加载时，从 store 加载数据
onMounted(async () => {
  await settingsStore.fetchSettings();
  longPool.value = settingsStore.availableLongCoins;
  shortPool.value = settingsStore.availableShortCoins;
});

defineExpose({
  savePools
});
</script>
