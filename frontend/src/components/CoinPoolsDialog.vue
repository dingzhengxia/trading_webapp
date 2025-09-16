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
          variant="outlined"
          clearable
          hide-details
          class="mb-4"
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

        <v-tabs v-model="currentTab">
          <v-tab value="long">添加到做多池</v-tab>
          <v-tab value="short">添加到做空池</v-tab>
        </v-tabs>

        <v-tabs-items v-model="currentTab">
          <!-- 做多币种池 -->
          <v-tab-item value="long">
            <v-alert type="info" density="compact" class="mb-4">
              以下是您为做多选择的币种：
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
              >
                {{ coin }}
              </v-chip>
            </v-chip-group>
            <div v-if="!currentLongPool || currentLongPool.length === 0" class="text-caption grey--text pa-2">
              尚未选择做多币种。
            </div>
          </v-tab-item>

          <!-- 做空币种池 -->
          <v-tab-item value="short">
            <v-alert type="info" density="compact" class="mb-4">
              以下是您为做空选择的币种：
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
              >
                {{ coin }}
              </v-chip>
            </v-chip-group>
            <div v-if="!currentShortPool || currentShortPool.length === 0" class="text-caption grey--text pa-2">
              尚未选择做空币种。
            </div>
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
const selectedCoins = ref<string[]>([]); // 用于多选组件选择的币种
const currentLongPool = ref<string[]>([]);
const currentShortPool = ref<string[]>([]);
const isRefreshingCoins = ref(false);

// 合并的可用币种列表
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
    currentLongPool.value = settingsStore.settings.long_coin_list || [];
    currentShortPool.value = settingsStore.settings.short_coin_list || [];
    selectedCoins.value = []; // 清空多选框的选中项
  } else {
    // 如果 settingsStore.settings 还没有加载，则先尝试加载，再初始化
    settingsStore.fetchSettings().then(() => {
      currentLongPool.value = settingsStore.settings?.long_coin_list || [];
      currentShortPool.value = settingsStore.settings?.short_coin_list || [];
      selectedCoins.value = [];
    });
  }
};

// 重置为默认值
const resetPools = () => {
  currentLongPool.value = settingsStore.availableLongCoins || [];
  currentShortPool.value = settingsStore.availableShortCoins || [];
  selectedCoins.value = [];
};

// 刷新可用币种列表
const refreshAvailableCoins = async () => {
  isRefreshingCoins.value = true;
  try {
    await settingsStore.fetchSettings(); // 重新加载设置，会更新 availableCoins
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
const removeChip = (poolType: 'long' | 'short', coin: string) => {
  if (poolType === 'long') {
    currentLongPool.value = currentLongPool.value.filter(c => c !== coin);
  } else {
    currentShortPool.value = currentShortPool.value.filter(c => c !== coin);
  }
};

const savePools = async () => {
  if (!settingsStore.settings) return;

  // 将当前选中项添加到对应的池中
  const coinsToAdd = selectedCoins.value;
  let newLongPool = [...currentLongPool.value];
  let newShortPool = [...currentShortPool.value];

  if (currentTab.value === 'long') {
    newLongPool = [...new Set([...newLongPool, ...coinsToAdd])]; // 合并并去重
  } else {
    newShortPool = [...new Set([...newShortPool, ...coinsToAdd])]; // 合并并去重
  }

  const updatedSettings = {
    ...settingsStore.settings,
    long_coin_list: newLongPool.sort(), // 排序
    short_coin_list: newShortPool.sort(), // 排序
  };

  try {
    // 调用新的 API 端点来更新 coin_lists.json
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
  selectedCoins.value = []; // 清空选择
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
</style>
