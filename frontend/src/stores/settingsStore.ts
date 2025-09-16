// frontend/src/stores/settingsStore.ts
import { defineStore } from 'pinia';
import { ref, watch, computed } from 'vue';
import type { UserSettings, CoinPools } from '@/models/types';
import api from '@/services/api';
import { useUiStore } from './uiStore';
import { debounce } from 'lodash-es'; // 确保已安装 lodash-es

const defaultSettings: UserSettings = {
  api_key: '', api_secret: '', use_testnet: true, enable_proxy: false, proxy_url: 'http://127.0.0.1:7890',
  leverage: 20,
  total_long_position_value: 1000.0,
  total_short_position_value: 500.0,
  // --- 直接使用 long_coin_list 和 short_coin_list 作为用户选择的列表 ---
  long_coin_list: ["BTC", "ETH"],
  short_coin_list: ["SOL", "AVAX"],
  // --- 移除了 user_selected_* 字段 ---
  // --- 结束 ---
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
  rel_strength_days: 60,
  rebalance_foam_days: 1,
  rebalance_short_ratio_max: 0.7,
  rebalance_short_ratio_min: 0.35
};

interface CoinPools {
    all_available_coins: string[];
}

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<UserSettings | null>(null);
  const availableCoins = ref<string[]>([]); // 合并后的所有可用币种
  const loading = ref(true);
  const uiStore = useUiStore();

  async function fetchSettings() {
    loading.value = true;
    try {
      const response = await api.get<{ user_settings: UserSettings } & CoinPools>('/api/settings');
      // --- 重要：合并时，如果用户设置中没有 long_coin_list/short_coin_list，则使用默认值 ---
      settings.value = {
        ...defaultSettings,
        ...response.data.user_settings,
        // 确保在加载时，如果用户配置中这两个列表为空，则使用全局的 ALL_AVAILABLE_COINS
        // 这样即使配置文件被清空，用户也能看到所有币种
        long_coin_list: response.data.user_settings.long_coin_list?.length > 0 ? response.data.user_settings.long_coin_list : DEFAULT_CONFIG.long_coin_list,
        short_coin_list: response.data.user_settings.short_coin_list?.length > 0 ? response.data.user_settings.short_coin_list : DEFAULT_CONFIG.short_coin_list,
      };
      availableCoins.value = response.data.all_available_coins;

      // --- 移除之前不必要的空列表回退逻辑 ---
      // if (!settings.value.user_selected_long_coins || settings.value.user_selected_long_coins.length === 0) {
      //     settings.value.user_selected_long_coins = [...availableCoins.value];
      // }
      // if (!settings.value.user_selected_short_coins || settings.value.user_selected_short_coins.length === 0) {
      //     settings.value.user_selected_short_coins = [...availableCoins.value];
      // }
      // --- 结束 ---

    } catch (error) {
      console.error("Failed to fetch settings:", error);
      uiStore.logStore.addLog({ message: "获取配置失败，请检查后端服务。", level: 'error', timestamp: new Date().toLocaleTimeString() });
      settings.value = { ...defaultSettings }; // 回退到默认配置
      availableCoins.value = ALL_AVAILABLE_COINS || []; // 后端加载失败时，回退到硬编码的全局列表
    } finally {
      loading.value = false;
    }
  }

  // --- 更新用户选择的币种列表，并直接保存 ---
  async function updateCoinPoolSelection(longCoins: string[], shortCoins: string[]) {
      try {
          // 假设 update-pools 接口只更新用户选择的部分
          const response = await api.post('/api/settings/update-pools', {
              selected_long_coins: longCoins,
              selected_short_coins: shortCoins
          });
          // 但是，我们需要将更改直接应用到 settings.value
          if (settings.value) {
              settings.value.long_coin_list = [...longCoins]; // 直接更新 long_coin_list
              settings.value.short_coin_list = [...shortCoins]; // 直接更新 short_coin_list
          }
          uiStore.logStore.addLog({ message: response.data.message || "币种列表已更新。", level: 'success', timestamp: new Date().toLocaleTimeString() });
      } catch (error: any) {
          const errorMsg = error.response?.data?.error || error.message;
          uiStore.logStore.addLog({ message: `更新币种列表失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
          console.error("Failed to update coin pools:", error);
      }
  }
  // --- 更新结束 ---

  async function saveSettings(newSettings: UserSettings | null) {
    if (!newSettings) return;
    try {
      // 使用 POST /api/settings 接口保存所有设置
      await api.post('/api/settings', newSettings);
      uiStore.logStore.addLog({ message: "配置已自动保存。", level: 'info', timestamp: new Date().toLocaleTimeString() });
    } catch (error) {
      console.error("Failed to save settings:", error);
      uiStore.logStore.addLog({ message: "自动保存配置失败！", level: 'error', timestamp: new Date().toLocaleTimeString() });
    }
  }

  let saveTimeout: number;
  watch(
    settings,
    (newSettingsValue) => {
      if (!loading.value && newSettingsValue) {
        clearTimeout(saveTimeout);
        saveTimeout = window.setTimeout(() => {
          saveSettings(newSettingsValue);
        }, 1200);
      }
    },
    { deep: true }
  );

  return {
    settings,
    availableCoins,
    loading,
    fetchSettings,
    saveSettings,
    updateCoinPoolSelection
  };
});
