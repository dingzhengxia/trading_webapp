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
            item-title="title"
            item-value="value"
            :menu-props="{ maxHeight: '300px' }"
          >
            <template v-slot:item="{ item, props }">
              <v-list-item v-bind="props" class="pl-0">
                <template v-slot:prepend>
                  <!-- 复选框现在直接绑定 item 的 value -->
                  <v-checkbox-btn :model-value="currentLongPool.includes(item.value)" readonly class="mr-2"></v-checkbox-btn>
                </template>
                <!-- **核心修复**: 不再手动渲染 v-list-item-title。v-bind="props" 会自动处理。 -->
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
            item-title="title"
            item-value="value"
            :menu-props="{ maxHeight: '300px' }"
          >
            <template v-slot:item="{ item, props }">
              <v-list-item v-bind="props" class="pl-0">
                <template v-slot:prepend>
                  <v-checkbox-btn :model-value="currentShortPool.includes(item.value)" readonly class="mr-2"></v-checkbox-btn>
                </template>
                 <!-- **核心修复**: 同样移除这里的手动标题渲染 -->
              </v-list-item>
            </template>
          </v-autocomplete>
        </v-card>
      </v-col>
    </v-row>
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

const allAvailableCoins = computed(() => [...new Set(settingsStore.availableCoins)].sort());

// **核心修复**: 将字符串数组转换为对象数组，明确指定 title 和 value
const mapToSelectItems = (coins: string[]) => coins.map(coin => ({ title: coin, value: coin }));

const longPoolAvailableCoins = computed(() => {
  const shortPoolSet = new Set(currentShortPool.value);
  const available = allAvailableCoins.value.filter(coin => !shortPoolSet.has(coin));
  return mapToSelectItems(available);
});

const shortPoolAvailableCoins = computed(() => {
  const longPoolSet = new Set(currentLongPool.value);
  const available = allAvailableCoins.value.filter(coin => !longPoolSet.has(coin));
  return mapToSelectItems(available);
});

const selectAllCoins = (poolType: 'long' | 'short') => {
  if (poolType === 'long') currentLongPool.value = longPoolAvailableCoins.value.map(item => item.value);
  else if (poolType === 'short') currentShortPool.value = shortPoolAvailableCoins.value.map(item => item.value);
};

const initializeTempPools = () => {
  if (settingsStore.settings) {
    const initialLong = settingsStore.settings.long_coin_list || [];
    const initialShort = settingsStore.settings.short_coin_list || [];
    const shortSet = new Set(initialShort);

    currentLongPool.value = initialLong.filter(coin => !shortSet.has(coin));
    currentShortPool.value = initialShort;
  }
};

const resetPools = () => {
  const defaultLong = defaultCoinPools.value.long_coins_pool || [];
  const defaultShort = defaultCoinPools.value.short_coins_pool || [];
  const defaultShortSet = new Set(defaultShort);

  currentLongPool.value = defaultLong.filter(coin => !defaultShortSet.has(coin));
  currentShortPool.value = defaultShort;
};

const savePools = async () => {
  if (!settingsStore.settings) return;
  try {
    await apiClient.post('/api/settings/update-coin-pools', {
      long_coins_pool: currentLongPool.value,
      short_coins_pool: currentShortPool.value
    });
    await settingsStore.fetchSettings();
    uiStore.logStore.addLog({ message: '交易币种列表已更新并保存。', level: 'success', timestamp: new Date().toLocaleTimeString() });
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message;
    uiStore.logStore.addLog({ message: `保存币种列表失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
  }
};

defineExpose({ savePools });

watch(currentLongPool, (newLongPool, oldLongPool) => {
  const addedToLong = newLongPool.filter(coin => !(oldLongPool || []).includes(coin));
  if (addedToLong.length > 0) {
    currentShortPool.value = currentShortPool.value.filter(coin => !addedToLong.includes(coin));
  }
});

watch(currentShortPool, (newShortPool, oldShortPool) => {
  const addedToShort = newShortPool.filter(coin => !(oldShortPool || []).includes(coin));
  if (addedToShort.length > 0) {
    currentLongPool.value = currentLongPool.value.filter(coin => !addedToShort.includes(coin));
  }
});

onMounted(() => {
  if (settingsStore.settings) {
    defaultCoinPools.value.long_coins_pool = [...settingsStore.availableLongCoins];
    defaultCoinPools.value.short_coins_pool = [...settingsStore.availableShortCoins];
    initializeTempPools();
  }
});
</script>
