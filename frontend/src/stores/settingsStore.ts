// frontend/src/stores/settingsStore.ts
import { defineStore } from 'pinia';
import { ref, watch, computed } from 'vue';
import type { UserSettings, CoinPools } from '@/models/types';
import api from '@/services/api';
import { useUiStore } from './uiStore';
import { debounce } from 'lodash-es';

const defaultSettings: UserSettings = {
  // ... (所有默认配置) ...
  api_key: '', api_secret: '', use_testnet: true, enable_proxy: false, proxy_url: 'http://127.0.0.1:7890',
  leverage: 20,
  total_long_position_value: 1000.0,
  total_short_position_value: 500.0,
  long_coin_list: ["BTC", "ETH"],
  short_coin_list: ["SOL", "AVAX"],
  user_selected_long_coins: [],
  user_selected_short_coins: [],
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
      settings.value = { ...defaultSettings, ...response.data.user_settings };
      availableCoins.value = response.data.all_available_coins;

      if (!settings.value.user_selected_long_coins || settings.value.user_selected_long_coins.length === 0) {
          console.log('[SettingsStore] user_selected_long_coins is empty, defaulting to availableCoins.');
          settings.value.user_selected_long_coins = [...availableCoins.value];
      }
      if (!settings.value.user_selected_short_coins || settings.value.user_selected_short_coins.length === 0) {
          console.log('[SettingsStore] user_selected_short_coins is empty, defaulting to availableCoins.');
          settings.value.user_selected_short_coins = [...availableCoins.value];
      }

    } catch (error) {
      console.error("Failed to fetch settings:", error);
      uiStore.logStore.addLog({ message: "获取配置失败，请检查后端服务。", level: 'error', timestamp: new Date().toLocaleTimeString() });
      // --- 错误处理回退 ---
      settings.value = { ...defaultSettings }; // 回退到默认配置
      // 当 API 调用失败时，availableCoins 应该回退到前端代码中硬编码的默认值
      // `defaultSettings.long_coin_list` 和 `defaultSettings.short_coin_list` 是一个可能的备选，
      // 但 `all_available_coins` 是从 coin_lists.json 加载的，理论上应该被优先使用。
      // 如果 `all_available_coins` 在后端加载失败时已经是空列表，那前端也应该显示为空。
      // 所以，这里直接使用 `defaultSettings` 中已有的 `long_coin_list` 和 `short_coin_list` 作为用户选择的默认值，
      // 然后 `availableCoins` 应该匹配 `all_available_coins` 的状态（即可能是空列表）。
      availableCoins.value = []; // 如果 API 失败，我们不知道正确的 `all_available_coins`，所以设为空。
                                 // 如果您希望在 API 失败时也显示默认的 coin_list，则应改为:
                                 // availableCoins.value = [...defaultSettings.long_coin_list, ...defaultSettings.short_coin_list].filter((v, i, a) => a.indexOf(v) === i);
                                 // 但更安全的做法是，如果 API 失败，就让币种选择变为空白或提示用户。
      // 确保用户选择的列表也回退到（可能是空的）可用列表
      settings.value.user_selected_long_coins = [...availableCoins.value];
      settings.value.user_selected_short_coins = [...availableCoins.value];
      // --- 错误处理回退结束 ---
    } finally {
      loading.value = false;
    }
  }

  async function updateCoinPoolSelection(longCoins: string[], shortCoins: string[]) {
      try {
          const response = await api.post('/api/settings/update-pools', {
              selected_long_coins: longCoins,
              selected_short_coins: shortCoins
          });
          if (settings.value) {
              settings.value.user_selected_long_coins = [...longCoins];
              settings.value.user_selected_short_coins = [...shortCoins];
          }
          uiStore.logStore.addLog({ message: response.data.message || "币种列表已更新。", level: 'success', timestamp: new Date().toLocaleTimeString() });
      } catch (error: any) {
          const errorMsg = error.response?.data?.error || error.message;
          uiStore.logStore.addLog({ message: `更新币种列表失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
          console.error("Failed to update coin pools:", error);
      }
  }

  async function saveSettings(newSettings: UserSettings | null) {
    if (!newSettings) return;
    try {
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
