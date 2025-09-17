// frontend/src/stores/settingsStore.ts
import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { UserSettings } from '@/models/types';
import api from '@/services/api';
import { useUiStore } from './uiStore';

const defaultSettings: UserSettings = {
  api_key: '', api_secret: '', use_testnet: true, enable_proxy: false, proxy_url: 'http://127.0.0.1:7890',
  leverage: 20,
  total_long_position_value: 1000.0,
  total_short_position_value: 500.0,
  long_coin_list: ["BTC", "ETH"],
  short_coin_list: ["SOL", "AVAX"],
  long_custom_weights: {},
  enable_long_trades: true,
  enable_short_trades: true,
  enable_long_sl_tp: true,
  long_stop_loss_percentage: 50.0,
  long_take_profit_percentage: 100.0,
  enable_short_sl_tp: true,
  short_stop_loss_percentage: 80.0,
  short_take_profit_percentage: 150.0,
  open_maker_retries: 5,
  open_order_fill_timeout_seconds: 60,
  close_maker_retries: 3,
  close_order_fill_timeout_seconds: 12,
  rebalance_method: 'multi_factor_weakest',
  rebalance_top_n: 50,
  rebalance_min_volume_usd: 20000000,
  rebalance_abs_momentum_days: 30,
  rebalance_rel_strength_days: 60,
  rebalance_foam_days: 1,
  rebalance_short_ratio_max: 0.7,
  rebalance_short_ratio_min: 0.35,
};


export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<UserSettings | null>(null);
  const availableCoins = ref<string[]>([]);
  const availableLongCoins = ref<string[]>([]);
  const availableShortCoins = ref<string[]>([]);
  // 新增 ref 来保存交易终端选中的币种
  const selectedLongCoins = ref<string[]>([]);
  const selectedShortCoins = ref<string[]>([]);
  const loading = ref(true);
  const uiStore = useUiStore();

  async function fetchSettings() {
    loading.value = true;
    try {
      const response = await api.get('/api/settings');
      settings.value = { ...defaultSettings, ...response.data.user_settings };
      availableCoins.value = response.data.available_coins;
      availableLongCoins.value = response.data.available_long_coins;
      availableShortCoins.value = response.data.available_short_coins;
      // 从后端加载新字段到 ref 中
      selectedLongCoins.value = settings.value.long_coin_list;
      selectedShortCoins.value = settings.value.short_coin_list;
    } catch (error) {
      console.error("Failed to fetch settings:", error);
      uiStore.logStore.addLog({ message: "获取配置失败，请检查后端服务。", level: 'error', timestamp: new Date().toLocaleTimeString() });
    } finally {
      loading.value = false;
    }
  }

  async function saveGeneralSettings(newSettings: UserSettings | null) {
    if (!newSettings) return;
    try {
      await api.post('/api/settings', newSettings);
      uiStore.logStore.addLog({ message: "通用配置已成功保存。", level: 'success', timestamp: new Date().toLocaleTimeString() });
    } catch (error) {
      console.error("Failed to save settings:", error);
      uiStore.logStore.addLog({ message: "保存通用配置失败！", level: 'error', timestamp: new Date().toLocaleTimeString() });
    }
  }

  // 新增一个 action 来专门保存交易终端的选中池
  async function saveSelectedCoinPools() {
    if (!settings.value) return;
    try {
      await api.post('/api/settings', {
        long_coin_list: selectedLongCoins.value,
        short_coin_list: selectedShortCoins.value
      });
      uiStore.logStore.addLog({ message: "交易终端币种选择已成功保存。", level: 'success', timestamp: new Date().toLocaleTimeString() });
    } catch (error) {
      console.error("Failed to save selected coin pools:", error);
      uiStore.logStore.addLog({ message: "保存交易终端币种选择失败！", level: 'error', timestamp: new Date().toLocaleTimeString() });
    }
  }

  return { settings, loading, availableCoins, availableLongCoins, availableShortCoins, fetchSettings, saveGeneralSettings, selectedLongCoins, selectedShortCoins, saveSelectedCoinPools };
});
