<template>
  <v-dialog v-model="show" persistent max-width="800px">
    <v-card>
      <v-card-title>
        <span class="text-h5">管理交易币种列表</span>
      </v-card-title>
      <v-card-text>
        <v-row>
          <v-col cols="12" md="6">
            <v-card variant="outlined" class="pa-4">
              <v-card-title class="text-subtitle-1 mb-2">
                做多币种列表 ({{ currentLongPool.length }})
                <v-tooltip location="top">
                  <template v-slot:activator="{ props }">
                    <v-btn icon="mdi-select-all" variant="text" size="small" v-bind="props" @click="selectAllCoins('long')"></v-btn>
                  </template>
                  <span>全选做多币种</span>
                </v-tooltip>
              </v-card-title>
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
                item-title="text"
                item-value="value"
                :menu-props="{ maxHeight: '300px' }"
                >
                <template v-slot:item="{ item, props }">
                  <v-list-item v-bind="props">
                    <template v-slot:prepend>
                      <v-icon
                        :color="currentLongPool.includes(item.value) ? 'primary' : 'transparent'"
                        :icon="currentLongPool.includes(item.value) ? 'mdi-check' : ''"
                      ></v-icon>
                    </template>
                    <v-list-item-title>{{ item.title }}</v-list-item-title>
                  </v-list-item>
                </template>
              </v-autocomplete>
            </v-card>
          </v-col>

          <v-col cols="12" md="6">
            <v-card variant="outlined" class="pa-4">
              <v-card-title class="text-subtitle-1 mb-2">
                做空币种列表 ({{ currentShortPool.length }})
                <v-tooltip location="top">
                  <template v-slot:activator="{ props }">
                    <v-btn icon="mdi-select-all" variant="text" size="small" v-bind="props" @click="selectAllCoins('short')"></v-btn>
                  </template>
                  <span>全选做空币种</span>
                </v-tooltip>
              </v-card-title>
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
                item-title="text"
                item-value="value"
                :menu-props="{ maxHeight: '300px' }"
                >
                <template v-slot:item="{ item, props }">
                  <v-list-item v-bind="props">
                    <template v-slot:prepend>
                      <v-icon
                        :color="currentShortPool.includes(item.value) ? 'primary' : 'transparent'"
                        :icon="currentShortPool.includes(item.value) ? 'mdi-check' : ''"
                      ></v-icon>
                    </template>
                    <v-list-item-title>{{ item.title }}</v-list-item-title>
                  </v-list-item>
                </template>
              </v-autocomplete>
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

const currentLongPool = ref<string[]>([]);
const currentShortPool = ref<string[]>([]);
const defaultCoinPools = ref({
  long_coins_pool: [] as string[],
  short_coins_pool: [] as string[]
});

const show = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
});

// 核心修改：创建一个唯一的总币种列表作为数据源
const allAvailableCoins = computed(() => {
  const combined = [...settingsStore.availableLongCoins, ...settingsStore.availableShortCoins];
  const uniqueCoins = [...new Set(combined)].sort();
  return uniqueCoins;
});

// 核心修改：做多列表的可用币种，基于总列表，排除已选的做空币种
const longPoolAvailableCoins = computed(() => {
  const shortPoolSet = new Set(currentShortPool.value);
  return allAvailableCoins.value
    .filter(coin => !shortPoolSet.has(coin))
    .map(coin => ({ text: coin, value: coin }));
});

// 核心修改：做空列表的可用币种，基于总列表，排除已选的做多币种
const shortPoolAvailableCoins = computed(() => {
  const longPoolSet = new Set(currentLongPool.value);
  return allAvailableCoins.value
    .filter(coin => !longPoolSet.has(coin))
    .map(coin => ({ text: coin, value: coin }));
});

// 新增功能：全选按钮逻辑
const selectAllCoins = (poolType: 'long' | 'short') => {
  if (poolType === 'long') {
    currentLongPool.value = longPoolAvailableCoins.value.map(item => item.value);
  } else if (poolType === 'short') {
    currentShortPool.value = shortPoolAvailableCoins.value.map(item => item.value);
  }
};

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

const savePools = async () => {
  if (!settingsStore.settings) return;

  const updatedSettings = {
    ...settingsStore.settings,
    long_coin_list: currentLongPool.value,
    short_coin_list: currentShortPool.value,
  };

  try {
    // 调用更新币种列表的 API
    await apiClient.post('/api/settings/update-coin-pools', {
      long_coins_pool: updatedSettings.long_coin_list,
      short_coins_pool: updatedSettings.short_coin_list
    });

    // 重新获取所有配置，确保前端状态与后端同步
    await settingsStore.fetchSettings();

    uiStore.logStore.addLog({ message: '交易币种列表已更新并保存。', level: 'success', timestamp: new Date().toLocaleTimeString() });
    closeDialog();
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message;
    uiStore.logStore.addLog({ message: `保存币种列表失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
  }
};

const closeDialog = () => {
  show.value = false;
};

// 核心监听器：当任何一个列表变化时，强制互斥
watch(currentLongPool, (newLongPool, oldLongPool) => {
  const newlyAdded = newLongPool.filter(coin => !oldLongPool.includes(coin));
  if (newlyAdded.length > 0) {
    currentShortPool.value = currentShortPool.value.filter(coin => !newlyAdded.includes(coin));
  }
}, { deep: true });

watch(currentShortPool, (newShortPool, oldShortPool) => {
  const newlyAdded = newShortPool.filter(coin => !oldShortPool.includes(coin));
  if (newlyAdded.length > 0) {
    currentLongPool.value = currentLongPool.value.filter(coin => !newlyAdded.includes(coin));
  }
}, { deep: true });

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
</style>
