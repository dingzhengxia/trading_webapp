<!-- frontend/src/components/CoinPoolsManager.vue -->
<template>
  <div>
    <v-row>
      <v-col cols="12" md="6">
        <v-card variant="tonal" class="pa-4">
          <div class="d-flex align-center mb-2">
            <span class="text-subtitle-1 font-weight-medium">做多币种列表 ({{ currentLongPool.length }})</span>
            <v-tooltip location="top">
              <template v-slot:activator="{ props }">
                <v-btn icon="mdi-select-all" variant="text" size="small" v-bind="props" @click="selectAllCoins('long')"></v-btn>
              </template>
              <span>全选</span>
            </v-tooltip>
          </div>
          <v-autocomplete
            v-model="currentLongPool"
            :items="longPoolAvailableCoins"
            label="选择或输入做多币种"
            multiple
            chips
            closable-chips
            clearable
            variant="outlined"
            hide-details
            item-title="value"
            item-value="value"
            :menu-props="{ maxHeight: '300px' }"
          >
            <template v-slot:item="{ item, props }">
              <v-list-item v-bind="props" class="pl-0">
                <template v-slot:prepend>
                  <v-checkbox-btn :model-value="currentLongPool.includes(item.value)" readonly class="mr-2"></v-checkbox-btn>
                </template>
                <v-list-item-title>{{ item.title }}</v-list-item-title>
              </v-list-item>
            </template>
          </v-autocomplete>
        </v-card>
      </v-col>

      <v-col cols="12" md="6">
        <v-card variant="tonal" class="pa-4">
          <div class="d-flex align-center mb-2">
            <span class="text-subtitle-1 font-weight-medium">做空币种列表 ({{ currentShortPool.length }})</span>
            <v-tooltip location="top">
              <template v-slot:activator="{ props }">
                <v-btn icon="mdi-select-all" variant="text" size="small" v-bind="props" @click="selectAllCoins('short')"></v-btn>
              </template>
              <span>全选</span>
            </v-tooltip>
          </div>
          <v-autocomplete
            v-model="currentShortPool"
            :items="shortPoolAvailableCoins"
            label="选择或输入做空币种"
            multiple
            chips
            closable-chips
            clearable
            variant="outlined"
            hide-details
            item-title="value"
            item-value="value"
            :menu-props="{ maxHeight: '300px' }"
          >
            <template v-slot:item="{ item, props }">
              <v-list-item v-bind="props" class="pl-0">
                <template v-slot:prepend>
                  <v-checkbox-btn :model-value="currentShortPool.includes(item.value)" readonly class="mr-2"></v-checkbox-btn>
                </template>
                <v-list-item-title>{{ item.title }}</v-list-item-title>
              </v-list-item>
            </template>
          </v-autocomplete>
        </v-card>
      </v-col>
    </v-row>

    <!-- 重置按钮现在放在内容区域内 -->
    <v-btn color="primary" variant="text" @click="resetPools" class="mt-4">重置为默认</v-btn>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUiStore } from '@/stores/uiStore';
import apiClient from '@/services/api';

const settingsStore = useSettingsStore();
const uiStore = useUiStore();

const currentLongPool = ref<string[]>([]);
const currentShortPool = ref<string[]>([]);
const defaultCoinPools = ref({ long_coins_pool: [] as string[], short_coins_pool: [] as string[] });

// **关键修复**：添加前端去重作为最后防线，确保列表唯一
const allAvailableCoins = computed(() => [...new Set(settingsStore.availableCoins)].sort());

const longPoolAvailableCoins = computed(() => {
  const shortPoolSet = new Set(currentShortPool.value);
  return allAvailableCoins.value.filter(coin => !shortPoolSet.has(coin));
});

const shortPoolAvailableCoins = computed(() => {
  const longPoolSet = new Set(currentLongPool.value);
  return allAvailableCoins.value.filter(coin => !longPoolSet.has(coin));
});

const selectAllCoins = (poolType: 'long' | 'short') => {
  if (poolType === 'long') currentLongPool.value = [...longPoolAvailableCoins.value];
  else if (poolType === 'short') currentShortPool.value = [...shortPoolAvailableCoins.value];
};

const initializeTempPools = () => {
  if (settingsStore.settings) {
    currentLongPool.value = [...(settingsStore.settings.long_coin_list || [])];
    currentShortPool.value = [...(settingsStore.settings.short_coin_list || [])];
  }
};

const resetPools = () => {
  currentLongPool.value = [...(defaultCoinPools.value.long_coins_pool || [])];
  currentShortPool.value = [...(defaultCoinPools.value.short_coins_pool || [])];
};

const savePools = async () => {
  if (!settingsStore.settings) return;
  try {
    await apiClient.post('/api/settings/update-coin-pools', {
      long_coins_pool: currentLongPool.value,
      short_coins_pool: currentShortPool.value
    });
    await settingsStore.fetchSettings(); // 重新获取配置以同步
    uiStore.logStore.addLog({ message: '交易币种列表已更新并保存。', level: 'success', timestamp: new Date().toLocaleTimeString() });
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message;
    uiStore.logStore.addLog({ message: `保存币种列表失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
  }
};

// 暴露 savePools 方法给父组件
defineExpose({ savePools });

watch(currentLongPool, (newVal) => {
  currentShortPool.value = currentShortPool.value.filter(coin => !newVal.includes(coin));
});

watch(currentShortPool, (newVal) => {
  currentLongPool.value = currentLongPool.value.filter(coin => !newVal.includes(coin));
});

onMounted(async () => {
  if (!settingsStore.settings || settingsStore.availableCoins.length === 0) {
    await settingsStore.fetchSettings();
  }
  defaultCoinPools.value.long_coins_pool = settingsStore.availableLongCoins || [];
  defaultCoinPools.value.short_coins_pool = settingsStore.availableShortCoins || [];
  initializeTempPools();
});
</script>
