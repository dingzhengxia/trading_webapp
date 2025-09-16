// frontend/src/stores/settingsStore.ts
import { defineStore } from 'pinia';
import { ref, watch, computed } from 'vue';
import type { UserSettings, CoinPools } from '@/models/types';
import api from '@/services/api';
import { useUiStore } from './uiStore';
import { debounce } from 'lodash-es'; // 引入 lodash 的 debounce

const defaultSettings: UserSettings = {
  api_key: '', api_secret: '', use_testnet: true, enable_proxy: false, proxy_url: 'http://127.0.0.1:7890',
  leverage: 20,
  total_long_position_value: 1000.0,
  total_short_position_value: 500.0,
  // --- 修改：默认值为空数组 ---
  user_selected_long_coins: [],
  user_selected_short_coins: [],
  // --- 修改结束 ---
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
  rel_strength_days: 60, // 保持后端命名
  rebalance_foam_days: 1,
  rebalance_short_ratio_max: 0.7,
  rebalance_short_ratio_min: 0.35
};

// --- 新增 CoinPools 接口 ---
interface CoinPools {
    all_available_coins: string[];
}
// --- 新增结束 ---

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<UserSettings | null>(null);
  // --- 修改：移除 availableLongCoins, availableShortCoins ---
  const availableCoins = ref<string[]>([]); // 合并后的所有可用币种
  // --- 修改结束 ---
  const loading = ref(true);
  const uiStore = useUiStore();

  async function fetchSettings() {
    loading.value = true;
    try {
      // 确保后端 API 返回的数据结构与此处类型定义一致
      const response = await api.get<{ user_settings: UserSettings } & CoinPools>('/api/settings');
      settings.value = { ...defaultSettings, ...response.data.user_settings };
      // --- 修改：存储合并后的列表 ---
      availableCoins.value = response.data.all_available_coins;
      // --- 修改结束 ---

      // --- 核心逻辑：如果用户选择的列表是空的，则用全局可用列表填充 ---
      // 这确保了首次运行时或用户清空列表后，应用仍能正常工作
      if (!settings.value.user_selected_long_coins || settings.value.user_selected_long_coins.length === 0) {
          console.log('[SettingsStore] user_selected_long_coins is empty, defaulting to availableCoins.');
          settings.value.user_selected_long_coins = [...availableCoins.value]; // 浅拷贝
      }
      if (!settings.value.user_selected_short_coins || settings.value.user_selected_short_coins.length === 0) {
          console.log('[SettingsStore] user_selected_short_coins is empty, defaulting to availableCoins.');
          settings.value.user_selected_short_coins = [...availableCoins.value]; // 浅拷贝
      }
      // --- 核心逻辑结束 ---

    } catch (error) {
      console.error("Failed to fetch settings:", error);
      uiStore.logStore.addLog({ message: "获取配置失败，请检查后端服务。", level: 'error', timestamp: new Date().toLocaleTimeString() });
      // 发生错误时，回退到默认值
      settings.value = { ...defaultSettings };
      availableCoins.value = []; // 后端如果没返回，前端也显示为空
    } finally {
      loading.value = false;
    }
  }

  // --- 新增：更新用户选择的币种列表 ---
  async function updateCoinPoolSelection(longCoins: string[], shortCoins: string[]) {
      try {
          const response = await api.post('/api/settings/update-pools', {
              selected_long_coins: longCoins,
              selected_short_coins: shortCoins
          });
          // 更新本地状态
          if (settings.value) {
              // 确保更新的是本地的响应式数据
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
  // --- 新增结束 ---

  async function saveSettings(newSettings: UserSettings | null) {
    if (!newSettings) return;
    try {
      // 假设 POST /api/settings 用于保存所有设置（包括用户选择的列表）
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
          // 确保我们只保存用户显式修改过的设置，而不是响应式更新触发的默认值填充
          saveSettings(newSettingsValue);
        }, 1200); // 延迟1.2秒保存
      }
    },
    { deep: true }
  );

  return {
    settings,
    // --- 修改：暴露合并后的列表 ---
    availableCoins,
    // --- 修改结束 ---
    loading,
    fetchSettings,
    saveSettings,
    updateCoinPoolSelection // 暴露新的action
  };
});
