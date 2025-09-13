import { defineStore } from 'pinia';
import { ref, watch } from 'vue';
import type { UserSettings } from '@/models/types';
import api from '@/services/api';
import { useUiStore } from './uiStore';

// 提供一个完整的默认设置对象，用于初始化和确保所有字段都存在
const defaultSettings: UserSettings = {
  leverage: 20,
  total_long_position_value: 1000.0,
  total_short_position_value: 500.0,
  long_coin_list: ["BTC", "ETH"],
  short_coin_list: ["SOL", "AVAX"],
  long_custom_weights: {},
  rebalance_method: 'multi_factor_weakest',
  rebalance_top_n: 50,
  rebalance_min_volume_usd: 20000000,
  rebalance_abs_momentum_days: 30,
  rebalance_rel_strength_days: 60,
  rebalance_foam_days: 1,
  open_maker_retries: 5,
  open_order_fill_timeout_seconds: 60,
  close_maker_retries: 3,
  close_order_fill_timeout_seconds: 12,
  enable_long_trades: true,
  enable_short_trades: true,
  enable_long_sl_tp: true,
  long_stop_loss_percentage: 50.0,
  long_take_profit_percentage: 100.0,
  enable_short_sl_tp: true,
  short_stop_loss_percentage: 80.0,
  short_take_profit_percentage: 150.0,
};

export const useSettingsStore = defineStore('settings', () => {
  // --- 核心修复：使用完整的默认对象进行初始化 ---
  const settings = ref<UserSettings>({ ...defaultSettings });
  // ---------------------------------------------

  const availableLongCoins = ref<string[]>([]);
  const availableShortCoins = ref<string[]>([]);
  const loading = ref(true);
  const uiStore = useUiStore();

  async function fetchSettings() {
    loading.value = true;
    try {
      const response = await api.get('/api/settings');

      // --- 核心修复：将加载的设置与默认设置合并 ---
      // 这样可以确保即使 user_settings.json 中缺少某些字段，
      // settings.value 对象也始终包含所有必需的属性。
      settings.value = { ...defaultSettings, ...response.data.user_settings };
      // ---------------------------------------------

      availableLongCoins.value = response.data.available_long_coins;
      availableShortCoins.value = response.data.available_short_coins;
    } catch (error) {
      console.error("Failed to fetch settings:", error);
      uiStore.logStore.addLog({ message: "获取配置失败，请检查后端服务是否运行。", level: 'error', timestamp: new Date().toLocaleTimeString() });
    } finally {
      loading.value = false;
    }
  }

  async function saveSettings() {
    try {
      await api.post('/api/settings', settings.value);
      uiStore.logStore.addLog({ message: "配置已自动保存。", level: 'info', timestamp: new Date().toLocaleTimeString() });
    } catch (error) {
      console.error("Failed to save settings:", error);
      uiStore.logStore.addLog({ message: "自动保存配置失败！", level: 'error', timestamp: new Date().toLocaleTimeString() });
    }
  }

  let saveTimeout: number;
  watch(
    settings,
    () => {
      if (!loading.value) {
        clearTimeout(saveTimeout);
        saveTimeout = window.setTimeout(() => {
          saveSettings();
        }, 1000);
      }
    },
    { deep: true }
  );

  return { settings, availableLongCoins, availableShortCoins, loading, fetchSettings, saveSettings };
});
