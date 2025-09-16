<template>
  <v-dialog v-model="show" persistent max-width="600px">
    <v-card>
      <v-card-title>
        <span class="text-h5">管理交易币种列表</span>
      </v-card-title>
      <v-card-text>
        <v-autocomplete
          v-model="selectedCoins"
          :items="allAvailableCoins"
          label="选择或输入币种"
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
          ref="autocompleteRef"
        >
          <template v-slot:selection="{ item, index }">
            <v-chip v-if="index < 2">
              <span>{{ item.title }}</span>
            </v-chip>
            <span v-else-if="index === 2" class="text-grey text-caption align-self-center">
              (+{{ selectedCoins.length - 2 }} 更多)
            </span>
          </template>

          <template v-slot:append-outer>
            <v-tooltip location="top">
              <template v-slot:activator="{ props }">
                <v-btn icon="mdi-refresh" variant="text" v-bind="props" @click="refreshAvailableCoins" :loading="isRefreshingCoins"></v-btn>
              </template>
              <span>刷新可用币种列表</span>
            </v-tooltip>
          </template>
        </v-autocomplete>

        <v-tabs v-model="currentTab" fixed-tabs>
          <v-tab value="long">做多池</v-tab>
          <v-tab value="short">做空池</v-tab>
        </v-tabs>

        <v-tabs-items v-model="currentTab">
          <v-tab-item value="long">
            <v-card variant="outlined" class="mt-4 pa-4">
              <div v-if="!currentLongPool || currentLongPool.length === 0" class="text-caption grey--text">
                尚未选择做多币种。
              </div>
              <v-chip
                v-for="coin in currentLongPool"
                :key="coin"
                closable
                @click:close="removeChip('long', coin)"
                color="success"
                label
                size="small"
                variant="elevated"
              >
                {{ coin }}
              </v-chip>
            </v-card>
          </v-tab-item>

          <v-tab-item value="short">
            <v-card variant="outlined" class="mt-4 pa-4">
              <div v-if="!currentShortPool || currentShortPool.length === 0" class="text-caption grey--text">
                尚未选择做空币种。
              </div>
              <v-chip
                v-for="coin in currentShortPool"
                :key="coin"
                closable
                @click:close="removeChip('short', coin)"
                color="error"
                label
                size="small"
                variant="elevated"
              >
                {{ coin }}
              </v-chip>
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
const selectedCoins = ref<string[]>([]);
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
  // 确保 v-autocomplete 的选中项与当前 tab 匹配
  selectedCoins.value = currentTab.value === 'long' ? currentLongPool.value : currentShortPool.value;
};

const resetPools = () => {
  currentLongPool.value = defaultCoinPools.value.long_coins_pool || [];
  currentShortPool.value = defaultCoinPools.value.short_coins_pool || [];
  selectedCoins.value = currentTab.value === 'long' ? currentLongPool.value : currentShortPool.value;
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

const removeChip = (poolType: 'long' | 'short', coinToRemove: string) => {
  if (poolType === 'long') {
    currentLongPool.value = currentLongPool.value.filter(coin => coin !== coinToRemove);
  } else {
    currentShortPool.value = currentShortPool.value.filter(coin => coin !== coinToRemove);
  }
  // 如果当前 tab 匹配，同时从 selectedCoins 中移除，以保持同步
  if (currentTab.value === poolType) {
    selectedCoins.value = selectedCoins.value.filter(coin => coin !== coinToRemove);
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

// 监听 dialog 打开事件，初始化临时数据
watch(() => props.modelValue, (newValue) => {
  if (newValue) {
    initializeTempPools();
  }
});

// 监听 selectedCoins 的变化，更新当前活动的池
watch(selectedCoins, (newValue) => {
  if (currentTab.value === 'long') {
    currentLongPool.value = newValue;
  } else {
    currentShortPool.value = newValue;
  }
});

// 监听标签页切换，同步 v-autocomplete 的选中项
watch(currentTab, (newValue) => {
  selectedCoins.value = newValue === 'long' ? currentLongPool.value : currentShortPool.value;
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
