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
          v-model="selectedCoinsToAdd"
          :items="allAvailableCoins"
          label="选择要添加到池的币种"
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

        <v-row>
          <!-- 做多池 -->
          <v-col cols="6">
            <v-card variant="outlined" height="100%">
              <v-card-title class="text-subtitle-1">
                做多池
                <v-chip size="small" label class="ml-2">{{ currentLongPool.length }}</v-chip>
              </v-card-title>
              <v-card-text>
                <v-alert type="info" density="compact" class="mb-4">
                  以下是您为做多选择的币种:
                </v-alert>
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
              <v-card-actions>
                <v-spacer></v-spacer>
                <!-- 批量添加按钮 -->
                <v-btn color="success" size="small" @click="addSelectedToPool('long')" :disabled="selectedCoinsToAdd.length === 0">
                  添加选中的币种
                </v-btn>
              </v-card-actions>
            </v-card>
          </v-col>

          <!-- 做空池 -->
          <v-col cols="6">
            <v-card variant="outlined" height="100%">
              <v-card-title class="text-subtitle-1">
                做空池
                 <v-chip size="small" label class="ml-2">{{ currentShortPool.length }}</v-chip>
              </v-card-title>
              <v-card-text>
                <v-alert type="info" density="compact" class="mb-4">
                  以下是您为做空选择的币种:
                </v-alert>
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
              <v-card-actions>
                <v-spacer></v-spacer>
                <!-- 批量添加按钮 -->
                <v-btn color="error" size="small" @click="addSelectedToPool('short')" :disabled="selectedCoinsToAdd.length === 0">
                  添加选中的币种
                </v-btn>
              </v-card-actions>
            </v-card>
          </v-col>
        </v-row>

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

const currentTab = ref('long'); // 默认显示做多池
const selectedCoinsToAdd = ref<string[]>([]); // 用于 v-autocomplete 的选择
const currentLongPool = ref<string[]>([]); // 当前做多池的币种
const currentShortPool = ref<string[]>([]); // 当前做空池的币种
const isRefreshingCoins = ref(false);

// 定义从 coin_lists.json 加载的默认值
const defaultCoinPools = ref({
  long_coins_pool: [] as string[],
  short_coins_pool: [] as string[]
});

// 合并的可用币种列表，用于 v-autocomplete 的 items
const allAvailableCoins = computed(() => {
  const combined = [...settingsStore.availableLongCoins, ...settingsStore.availableShortCoins];
  // 去重并排序
  return [...new Set(combined)].sort();
});

// 同步 v-model
const show = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
});

// 初始化临时池数据
const initializeTempPools = () => {
  if (settingsStore.settings) {
    // 使用 settingsStore 中已有的做多/做空列表进行初始化
    currentLongPool.value = settingsStore.settings.long_coin_list || [];
    currentShortPool.value = settingsStore.settings.short_coin_list || [];
    selectedCoinsToAdd.value = []; // 清空多选框的选中项
  } else {
    // 如果 settingsStore.settings 还没有加载，则先尝试加载，再初始化
    settingsStore.fetchSettings().then(() => {
      currentLongPool.value = settingsStore.settings?.long_coin_list || [];
      currentShortPool.value = settingsStore.settings?.short_coin_list || [];
      selectedCoinsToAdd.value = [];
    });
  }
};

// 重置为默认值
const resetPools = () => {
  // 使用从 API 加载的默认值
  currentLongPool.value = defaultCoinPools.value.long_coins_pool || [];
  currentShortPool.value = defaultCoinPools.value.short_coins_pool || [];
  selectedCoinsToAdd.value = [];
};

// 刷新可用币种列表
const refreshAvailableCoins = async () => {
  isRefreshingCoins.value = true;
  try {
    // 重新加载设置，这会更新 settingsStore.availableLongCoins 和 availableShortCoins
    await settingsStore.fetchSettings();
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
    uiStore.logStore.addLog({ message: '请先选择要添加的币种。', level: 'warning', timestamp: new Date().toLocaleTimeString() });
    return;
  }

  let updatedPool: string[];
  if (poolType === 'long') {
    // 合并新选择的币种，并去重，然后排序
    updatedPool = [...new Set([...currentLongPool.value, ...selectedCoinsToAdd.value])].sort();
    currentLongPool.value = updatedPool;
  } else {
    updatedPool = [...new Set([...currentShortPool.value, ...selectedCoinsToAdd.value])].sort();
    currentShortPool.value = updatedPool;
  }

  // 清空 selectedCoinsToAdd，以便下次添加
  selectedCoinsToAdd.value = [];
  uiStore.logStore.addLog({ message: `已将 ${selectedCoinsToAdd.value.length} 个币种添加到 ${poolType} 池。`, level: 'success', timestamp: new Date().toLocaleTimeString() });
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
    settingsStore.settings = updatedSettings; // 更新 store 中的值

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
</script>

<style scoped>
/* 可以根据需要添加样式 */
.v-chip--filter {
  background-color: rgba(255, 255, 255, 0.1); /* 使 filter chip 稍微软化 */
}
.v-chip {
    margin: 4px; /* 稍微增加chip之间的间距 */
}
.v-card-text > .v-tabs-items > .v-tab-item {
    padding-top: 16px; /* 为tab内容添加顶部间距 */
}
</style>
