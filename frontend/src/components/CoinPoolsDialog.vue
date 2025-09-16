<template>
  <v-dialog v-model="show" persistent max-width="600px">
    <v-card>
      <v-card-title>
        <span class="text-h5">管理交易币种列表</span>
      </v-card-title>
      <v-card-text>
        <v-tabs v-model="currentTab" fixed-tabs>
          <v-tab value="long">做多池</v-tab>
          <v-tab value="short">做空池</v-tab>
        </v-tabs>

        <v-tabs-items v-model="currentTab">
          <v-tab-item value="long">
            <v-card variant="outlined" class="mt-4">
              <v-card-title class="text-subtitle-1">
                做多币种列表 ({{ currentLongPool.length }})
              </v-card-title>
              <v-card-text>
                <v-autocomplete
                  v-model="currentLongPool"
                  :items="allAvailableCoins"
                  label="选择或输入做多币种"
                  multiple
                  chips
                  closable-chips
                  clearable
                  variant="outlined"
                  auto-grow
                  rows="3"
                  row-height="30"
                  class="mb-4"
                  :loading="isRefreshingCoins"
                  hide-details
                  item-title="text"
                  item-value="value"
                  :menu-props="{ maxHeight: '300px' }"
                >
                  <template v-slot:append-outer>
                    <v-tooltip location="top">
                      <template v-slot:activator="{ props }">
                        <v-btn icon="mdi-refresh" variant="text" v-bind="props" @click="refreshAvailableCoins" :loading="isRefreshingCoins"></v-btn>
                      </template>
                      <span>刷新可用币种列表</span>
                    </v-tooltip>
                  </template>
                </v-autocomplete>
              </v-card-text>
            </v-card>
          </v-tab-item>

          <v-tab-item value="short">
            <v-card variant="outlined" class="mt-4">
              <v-card-title class="text-subtitle-1">
                做空币种列表 ({{ currentShortPool.length }})
              </v-card-title>
              <v-card-text>
                <v-autocomplete
                  v-model="currentShortPool"
                  :items="allAvailableCoins"
                  label="选择或输入做空币种"
                  multiple
                  chips
                  closable-chips
                  clearable
                  variant="outlined"
                  auto-grow
                  rows="3"
                  row-height="30"
                  class="mb-4"
                  :loading="isRefreshingCoins"
                  hide-details
                  item-title="text"
                  item-value="value"
                  :menu-props="{ maxHeight: '300px' }"
                >
                  <template v-slot:append-outer>
                    <v-tooltip location="top">
                      <template v-slot:activator="{ props }">
                        <v-btn icon="mdi-refresh" variant="text" v-bind="props" @click="refreshAvailableCoins" :loading="isRefreshingCoins"></v-btn>
                      </template>
                      <span>刷新可用币种列表</span>
                    </v-tooltip>
                  </template>
                </v-autocomplete>
              </v-card-text>
            </v-card>
          </v-tab-item>
        </v-tabs-items>
      </v-card-text>
      <v-card-actions>
        <v-btn color="primary" variant="text" @click="resetPools">重置为默认</v-btn>
        <v-spacer></v-spacer>
        <v-btn color="blue-darken-1" variant="text" @click="closeDialog">取消</v-btn>
        <v-btn color="green-darken-1" variant="tonal" @click="savePools">保存</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUiStore } from '@/stores/uiStore';
import apiClient from '@/services/api';

const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits(['update:modelValue']);

const settingsStore = useSettingsStore();
const uiStore = useUiStore();

const currentTab = ref('long');
const currentLongPool = ref<string[]>([]);
const currentShortPool = ref<string[]>([]);
const isRefreshingCoins = ref(false);

const defaultCoinPools = ref({
  long_coins_pool: [] as string[],
  short_coins_pool: [] as string[]
});

const allAvailableCoins = computed(() => {
  const combined = [...settingsStore.availableLongCoins, ...settingsStore.availableShortCoins];
  const uniqueCoins = [...new Set(combined)].sort();
  return uniqueCoins.map(coin => ({ text: coin, value: coin }));
});

const show = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
});

const initializeTempPools = () => {
  if (settingsStore.settings) {
    currentLongPool.value = settingsStore.settings.long_coin_list || [];
    currentShortPool.value = settingsStore.settings.short_coin_list || [];
  } else {
    settingsStore.fetchSettings().then(() => {
      currentLongPool.value = settingsStore.settings?.long_coin_list || [];
      currentShortPool.value = settingsStore.settings?.short_coin_list || [];
    });
  }
};

const resetPools = () => {
  currentLongPool.value = defaultCoinPools.value.long_coins_pool || [];
  currentShortPool.value = defaultCoinPools.value.short_coins_pool || [];
};

const refreshAvailableCoins = async () => {
  isRefreshingCoins.value = true;
  try {
    await settingsStore.fetchSettings();
    defaultCoinPools.value.long_coins_pool = settingsStore.availableLongCoins || [];
    defaultCoinPools.value.short_coins_pool = settingsStore.availableShortCoins || [];
    resetPools();
    uiStore.logStore.addLog({ message: '可用币种列表已刷新。', level: 'info', timestamp: new Date().toLocaleTimeString() });
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message;
    uiStore.logStore.addLog({ message: `刷新可用币种列表失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
  } finally {
    isRefreshingCoins.value = false;
  }
};

const savePools = async () => {
  if (!settingsStore.settings) return;

  const updatedSettings = {
    ...settingsStore.settings,
    long_coin_list: currentLongPool.value,
    short_coin_list: currentShortPool.value,
  };

  try {
    await apiClient.post('/api/settings/update-coin-pools', {
      long_coins_pool: updatedSettings.long_coin_list,
      short_coins_pool: updatedSettings.short_coin_list
    });

    await settingsStore.saveSettings(updatedSettings);
    settingsStore.settings = updatedSettings;

    uiStore.logStore.addLog({ message: '交易币种列表已更新并保存。', level: 'success', timestamp: new Date().toLocaleTimeString() });
    closeDialog();
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message;
    uiStore.logStore.addLog({ message: `保存币种列表失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
  }
};

const closeDialog = () => {
  show.value = false;
  currentTab.value = 'long';
};

watch(() => props.modelValue, (newValue) => {
  if (newValue) {
    initializeTempPools();
  }
});

onMounted(async () => {
  if (!settingsStore.settings) {
    await settingsStore.fetchSettings();
  }
  defaultCoinPools.value.long_coins_pool = settingsStore.availableLongCoins || [];
  defaultCoinPools.value.short_coins_pool = settingsStore.availableShortCoins || [];
});

</script>

<style scoped>
/* chip 之间的间距 */
.v-chip {
  margin: 4px;
  
}
/* tab 内容的顶部间距 */
.v-card-text > .v-tabs-items > .v-tab-item {
  padding-top: 16px;
}
/* 调整 v-autocomplete 的样式 */
.v-autocomplete {
  max-height: 150px; /* 限制高度，防止过长 */
  overflow-y: auto; /* 启用滚动条 */
}
</style>
