<!-- frontend/src/components/CoinPoolsDialog.vue -->
<template>
  <v-dialog v-model="show" persistent max-width="600px">
    <v-card>
      <v-card-title>
        <span class="text-h5">管理交易币种列表</span>
      </v-card-title>
      <v-card-text>
        <!-- 合并后的可用币种列表，用于用户选择 -->
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
          return-object
          item-title="text"
          item-value="value"
        >
          <!-- 全选/反选功能 -->
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
          <!-- 做多池 -->
          <v-tab-item value="long">
            <v-card variant="outlined" class="mt-4">
              <v-card-title class="text-subtitle-1">
                做多币种列表 ({{ currentLongPool.length }})
              </v-card-title>
              <v-card-text>
                <v-chip-group v-model="currentLongPool" column multiple filter>
                  <v-chip
                    v-for="coin in currentLongPool"
                    :key="coin"
                    :value="coin"
                    filter
                    closable
                    @update:model-value="removeChip('long', coin)"
                    color="success"
                    label
                    size="small"
                  >
                    {{ coin }}
                  </v-chip>
                </v-chip-group>
                <div v-if="!currentLongPool || currentLongPool.length === 0" class="text-caption grey--text pa-2">
                  尚未选择做多币种。
                </div>
              </v-card-text>
            </v-card>
          </v-tab-item>

          <!-- 做空池 -->
          <v-tab-item value="short">
            <v-card variant="outlined" class="mt-4">
              <v-card-title class="text-subtitle-1">
                做空币种列表 ({{ currentShortPool.length }})
              </v-card-title>
              <v-card-text>
                <v-chip-group v-model="currentShortPool" column multiple filter>
                  <v-chip
                    v-for="coin in currentShortPool"
                    :key="coin"
                    :value="coin"
                    filter
                    closable
                    @update:model-value="removeChip('short', coin)"
                    color="error"
                    label
                    size="small"
                  >
                    {{ coin }}
                  </v-chip>
                </v-chip-group>
                <div v-if="!currentShortPool || currentShortPool.length === 0" class="text-caption grey--text pa-2">
                  尚未选择做空币种。
                </div>
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
import { ref, computed, watch, onMounted, nextTick } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUiStore } from '@/stores/uiStore';
import apiClient from '@/services/api';

const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits(['update:modelValue']);

const settingsStore = useSettingsStore();
const uiStore = useUiStore();

const currentTab = ref('long'); // 默认显示做多池
const selectedCoinsToAdd = ref<string[]>([]); // 用于 v-autocomplete 选择的币种
const currentLongPool = ref<string[]>([]); // 当前做多池的币种
const currentShortPool = ref<string[]>([]); // 当前做空池的币种
const isRefreshingCoins = ref(false);

// 定义从 coin_lists.json 加载的默认值
const defaultCoinPools = ref({
  long_coins_pool: [] as string[],
  short_coins_pool: [] as string[]
});

// 合并的可用币种列表，用于 v-autocomplete 的 items
// 包含 text 和 value 属性，以支持 v-autocomplete 的自定义显示
const allAvailableCoins = computed(() => {
  const combined = [...settingsStore.availableLongCoins, ...settingsStore.availableShortCoins];
  const uniqueCoins = [...new Set(combined)].sort();
  return uniqueCoins.map(coin => ({ text: coin, value: coin }));
});

// 同步 v-model
const show = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
});

// 初始化临时池数据
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
  // 确保 selectedCoinsToAdd 在每次打开时清空
  selectedCoinsToAdd.value = [];
  // 确保 tab 默认是 long
  currentTab.value = 'long';
};

// 重置为默认值
const resetPools = () => {
  currentLongPool.value = defaultCoinPools.value.long_coins_pool || [];
  currentShortPool.value = defaultCoinPools.value.short_coins_pool || [];
  selectedCoinsToAdd.value = [];
};

// 刷新可用币种列表
const refreshAvailableCoins = async () => {
  isRefreshingCoins.value = true;
  try {
    await settingsStore.fetchSettings(); // 重新加载设置，会更新 availableCoins
    // 更新默认值
    defaultCoinPools.value.long_coins_pool = settingsStore.availableLongCoins || [];
    defaultCoinPools.value.short_coins_pool = settingsStore.availableShortCoins || [];
    // 重置到最新的默认值
    resetPools();
    uiStore.logStore.addLog({ message: '可用币种列表已刷新。', level: 'info', timestamp: new Date().toLocaleTimeString() });
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message;
    uiStore.logStore.addLog({ message: `刷新可用币种列表失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
  } finally {
    isRefreshingCoins.value = false;
  }
};

// 从池中移除币种 (当用户点击 chip 的 x 时触发)
const removeChip = (poolType: 'long' | 'short', coinToRemove: string) => {
  if (poolType === 'long') {
    currentLongPool.value = currentLongPool.value.filter(coin => coin !== coinToRemove);
  } else {
    currentShortPool.value = currentShortPool.value.filter(coin => coin !== coinToRemove);
  }
  // 同时从 selectedCoinsToAdd 中移除，如果它被选中了的话
  selectedCoinsToAdd.value = selectedCoinsToAdd.value.filter(coin => coin !== coinToRemove);
};

// 将选中的币种添加到指定的池中
const addSelectedToPool = (poolType: 'long' | 'short') => {
  if (!selectedCoinsToAdd.value || selectedCoinsToAdd.value.length === 0) {
    uiStore.logStore.addLog({ message: '请先在上方选择要添加的币种。', level: 'warning', timestamp: new Date().toLocaleTimeString() });
    return;
  }

  let updatedPool: string[];
  if (poolType === 'long') {
    // 合并新选择的币种，并去重，然后排序
    const newLongSet = new Set([...currentLongPool.value, ...selectedCoinsToAdd.value]);
    currentLongPool.value = Array.from(newLongSet).sort();
  } else {
    const newShortSet = new Set([...currentShortPool.value, ...selectedCoinsToAdd.value]);
    currentShortPool.value = Array.from(newShortSet).sort();
  }

  // 清空 selectedCoinsToAdd，以便下次添加
  selectedCoinsToAdd.value = [];
  uiStore.logStore.addLog({ message: `已将选中的 ${selectedCoinsToAdd.value.length} 个币种添加到 ${poolType} 池。`, level: 'success', timestamp: new Date().toLocaleTimeString() });
};

const savePools = async () => {
  if (!settingsStore.settings) return;

  // 最终将 currentLongPool 和 currentShortPool 保存到 settingsStore
  const updatedSettings = {
    ...settingsStore.settings,
    long_coin_list: currentLongPool.value,
    short_coin_list: currentShortPool.value,
  };

  try {
    // 调用后端 API 来更新 coin_lists.json
    await apiClient.post('/api/settings/update-coin-pools', {
      long_coins_pool: updatedSettings.long_coin_list,
      short_coins_pool: updatedSettings.short_coin_list
    });

    // 同时更新 user_settings.json 中的配置
    await settingsStore.saveSettings(updatedSettings);
    // 更新 settingsStore 中的值，以反映用户界面上的最新数据
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
  currentTab.value = 'long'; // 重置标签页
  selectedCoinsToAdd.value = []; // 清空选择
};

// 监听 dialog 打开事件，初始化临时数据
watch(() => props.modelValue, (newValue) => {
  if (newValue) {
    initializeTempPools();
  }
});

// --- 核心修改：添加 onMounted 钩子来初始化默认值 ---
onMounted(async () => {
  // 确保 settingsStore 已加载，以获取 available_long_coins 和 available_short_coins
  if (!settingsStore.settings) {
    await settingsStore.fetchSettings();
  }
  // 设置默认值
  defaultCoinPools.value.long_coins_pool = settingsStore.availableLongCoins || [];
  defaultCoinPools.value.short_coins_pool = settingsStore.availableShortCoins || [];
});
// --- 修改结束 ---

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
