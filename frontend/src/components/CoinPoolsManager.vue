<!-- frontend/src/components/CoinPoolsManager.vue -->
<template>
  <div v-if="settingsStore.settings">
    <v-row>
      <v-col cols="12" md="6">
        <v-card variant="tonal" class="pa-4">
          <div class="d-flex align-center mb-2">
            <span class="text-subtitle-1 font-weight-medium">做多币种列表 ({{ settingsStore.settings.long_coin_list.length }})</span>
            <v-tooltip location="top">
              <template v-slot:activator="{ props }">
                <v-btn icon="mdi-select-all" variant="text" size="small" v-bind="props" @click="selectAllCoins('long')"></v-btn>
              </template>
              <span>全选</span>
            </v-tooltip>
          </div>
          <v-autocomplete
            v-model="settingsStore.settings.long_coin_list"
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
                  <v-checkbox-btn :model-value="settingsStore.settings!.long_coin_list.includes(item.value)" readonly class="mr-2"></v-checkbox-btn>
                </template>
              </v-list-item>
            </template>
          </v-autocomplete>
        </v-card>
      </v-col>

      <v-col cols="12" md="6">
        <v-card variant="tonal" class="pa-4">
          <div class="d-flex align-center mb-2">
            <span class="text-subtitle-1 font-weight-medium">做空币种列表 ({{ settingsStore.settings.short_coin_list.length }})</span>
            <v-tooltip location="top">
              <template v-slot:activator="{ props }">
                <v-btn icon="mdi-select-all" variant="text" size="small" v-bind="props" @click="selectAllCoins('short')"></v-btn>
              </template>
              <span>全选</span>
            </v-tooltip>
          </div>
          <v-autocomplete
            v-model="settingsStore.settings.short_coin_list"
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
                  <v-checkbox-btn :model-value="settingsStore.settings!.short_coin_list.includes(item.value)" readonly class="mr-2"></v-checkbox-btn>
                </template>
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
import { computed, watch } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';

const settingsStore = useSettingsStore();

const allAvailableCoins = computed(() => [...new Set(settingsStore.availableCoins)].sort());

const mapToSelectItems = (coins: string[]) => coins.map(coin => ({ title: coin, value: coin }));

const longPoolAvailableCoins = computed(() => {
  if (!settingsStore.settings) return [];
  const shortPoolSet = new Set(settingsStore.settings.short_coin_list);
  const available = allAvailableCoins.value.filter(coin => !shortPoolSet.has(coin));
  return mapToSelectItems(available);
});

const shortPoolAvailableCoins = computed(() => {
  if (!settingsStore.settings) return [];
  const longPoolSet = new Set(settingsStore.settings.long_coin_list);
  const available = allAvailableCoins.value.filter(coin => !longPoolSet.has(coin));
  return mapToSelectItems(available);
});

const selectAllCoins = (poolType: 'long' | 'short') => {
  if (!settingsStore.settings) return;
  if (poolType === 'long') {
    settingsStore.settings.long_coin_list = longPoolAvailableCoins.value.map(item => item.value);
  } else if (poolType === 'short') {
    settingsStore.settings.short_coin_list = shortPoolAvailableCoins.value.map(item => item.value);
  }
};

const resetPools = () => {
  if (!settingsStore.settings) return;
  settingsStore.settings.long_coin_list = [...settingsStore.availableLongCoins];
  settingsStore.settings.short_coin_list = [...settingsStore.availableShortCoins];
};

// 监听器确保两个列表互斥
watch(() => settingsStore.settings?.long_coin_list, (newLongPool, oldLongPool) => {
  if (!newLongPool || !oldLongPool || !settingsStore.settings) return;
  const addedToLong = newLongPool.filter(coin => !oldLongPool.includes(coin));
  if (addedToLong.length > 0) {
    settingsStore.settings.short_coin_list = settingsStore.settings.short_coin_list.filter(coin => !addedToLong.includes(coin));
  }
}, { deep: true });

watch(() => settingsStore.settings?.short_coin_list, (newShortPool, oldShortPool) => {
  if (!newShortPool || !oldShortPool || !settingsStore.settings) return;
  const addedToShort = newShortPool.filter(coin => !oldShortPool.includes(coin));
  if (addedToShort.length > 0) {
    settingsStore.settings.long_coin_list = settingsStore.settings.long_coin_list.filter(coin => !addedToShort.includes(coin));
  }
}, { deep: true });

</script>
