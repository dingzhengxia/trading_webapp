<!-- frontend/src/components/CoinPoolsDialog.vue -->
<template>
  <v-dialog v-model="show" persistent max-width="600px">
    <v-card>
      <v-card-title>
        <span class="text-h5">管理交易币种列表</span>
      </v-card-title>
      <v-card-text>
        <v-tabs v-model="currentTab">
          <v-tab value="long">做多币种池</v-tab>
          <v-tab value="short">做空币种池</v-tab>
        </v-tabs>
        <v-tabs-items v-model="currentTab">
          <!-- 做多币种池 -->
          <v-tab-item value="long">
            <v-text-field
              v-model="tempLongPool"
              label="做多币种 (用逗号分隔)"
              hint="例如: BTC,ETH,SOL"
              persistent-hint
              chips
              closable-chips
              clearable
              variant="outlined"
              auto-grow
              rows="3"
              row-height="30"
              class="mt-4"
            ></v-text-field>
          </v-tab-item>
          <!-- 做空币种池 -->
          <v-tab-item value="short">
            <v-text-field
              v-model="tempShortPool"
              label="做空币种 (用逗号分隔)"
              hint="例如: XRP,ADA,BNB"
              persistent-hint
              chips
              closable-chips
              clearable
              variant="outlined"
              auto-grow
              rows="3"
              row-height="30"
              class="mt-4"
            ></v-text-field>
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
import apiClient from '@/services/api'; // 导入 apiClient

const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits(['update:modelValue']);

const settingsStore = useSettingsStore();
const uiStore = useUiStore();

const currentTab = ref('long');
const tempLongPool = ref('');
const tempShortPool = ref('');

// 定义从 coin_lists.json 加载的默认值
const defaultCoinPools = ref({
  long_coins_pool: [] as string[],
  short_coins_pool: [] as string[]
});

// --- 核心修改：在组件挂载时加载默认的币种池 ---
onMounted(async () => {
  // 确保 settingsStore 已加载，以获取 available_long_coins 和 available_short_coins
  if (!settingsStore.settings) {
    await settingsStore.fetchSettings();
  }
  // 使用 settingsStore 中已有的可用币种列表作为默认值
  defaultCoinPools.value.long_coins_pool = settingsStore.availableLongCoins || [];
  defaultCoinPools.value.short_coins_pool = settingsStore.availableShortCoins || [];
});
// --- 修改结束 ---

// 同步 v-model
const show = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
});

// 初始化临时池数据
const initializeTempPools = () => {
  if (settingsStore.settings) {
    // 使用 settingsStore 中已有的数据进行初始化
    tempLongPool.value = settingsStore.settings.long_coin_list.join(',');
    tempShortPool.value = settingsStore.settings.short_coin_list.join(',');
  } else {
    // 如果 settingsStore.settings 还没有加载，则先尝试加载，再初始化
    settingsStore.fetchSettings().then(() => {
      tempLongPool.value = settingsStore.settings?.long_coin_list.join(',') || '';
      tempShortPool.value = settingsStore.settings?.short_coin_list.join(',') || '';
    });
  }
};

// 重置为默认值
const resetPools = () => {
  tempLongPool.value = defaultCoinPools.value.long_coins_pool.join(',');
  tempShortPool.value = defaultCoinPools.value.short_coins_pool.join(',');
};

const savePools = async () => {
  if (!settingsStore.settings) return;

  const updatedSettings = {
    ...settingsStore.settings,
    long_coin_list: tempLongPool.value.split(',').map(s => s.trim()).filter(s => s),
    short_coin_list: tempShortPool.value.split(',').map(s => s.trim()).filter(s => s),
  };

  try {
    // 调用新的 API 端点来更新 coin_lists.json
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
};

// 监听 dialog 打开事件，初始化临时数据
watch(() => props.modelValue, (newValue) => {
  if (newValue) {
    initializeTempPools();
  }
});
</script>
