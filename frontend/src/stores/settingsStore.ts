// frontend/src/stores/settingsStore.ts (最终版)
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { UserSettings } from '@/models/types'
import api from '@/services/api'
import { useUiStore } from './uiStore'

const defaultSettings: UserSettings = {
  api_key: '',
  api_secret: '',
  use_testnet: true,
  enable_proxy: false,
  proxy_url: 'http://127.0.0.1:7890',
  leverage: 20,
  total_long_position_value: 1000.0,
  total_short_position_value: 500.0,
  long_coin_list: ['BTC', 'ETH'],
  short_coin_list: ['SOL', 'AVAX'],
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
  rebalance_volume_ma_days: 20,
  rebalance_volume_spike_ratio: 3.0,
  rebalance_benchmark_coin: ['BTC'],

  enable_rebalance_filters: true,
  rebalance_rsi_period: 14,
  rebalance_rsi_threshold: 25.0,
  rebalance_short_term_momentum_days: 3,
  rebalance_short_term_momentum_threshold: 15.0,
  rebalance_bollinger_period: 20,
  rebalance_bollinger_std_dev: 2,
  rebalance_bollinger_width_spike_ratio: 2.0,
};

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<UserSettings | null>(null)
  const availableCoins = ref<string[]>([])
  const availableLongCoins = ref<string[]>([])
  const availableShortCoins = ref<string[]>([])
  const loading = ref(true)
  const uiStore = useUiStore()

  async function fetchSettings() {
    if (settings.value === null) {
      loading.value = true
    }

    try {
      const response = await api.get('/api/settings')
      const fetchedSettings = {...defaultSettings, ...response.data.user_settings}

      if (settings.value) {
        Object.assign(settings.value, fetchedSettings)
      } else {
        settings.value = fetchedSettings
      }

      availableCoins.value = response.data.available_coins
      availableLongCoins.value = response.data.available_long_coins
      availableShortCoins.value = response.data.available_short_coins
    } catch (error) {
      console.error('Failed to fetch settings:', error)
      uiStore.logStore.addLog({
        message: '获取配置失败，请检查后端服务。',
        level: 'error',
        timestamp: new Date().toLocaleTimeString(),
      })
    } finally {
      loading.value = false
    }
  }

  function updateAvailablePools(longPool: string[], shortPool: string[]) {
    availableLongCoins.value = longPool
    availableShortCoins.value = shortPool
  }

  async function saveGeneralSettings(newSettings: UserSettings | null) {
    if (!newSettings) return
    try {
      await api.post('/api/settings', newSettings)
      uiStore.logStore.addLog({
        message: '通用配置已自动保存。',
        level: 'success',
        timestamp: new Date().toLocaleTimeString(),
      })
    } catch (error) {
      console.error('Failed to save settings:', error)
      uiStore.logStore.addLog({
        message: '自动保存配置失败！',
        level: 'error',
        timestamp: new Date().toLocaleTimeString(),
      })
    }
  }

  async function saveSelectedCoinLists(longList: string[], shortList: string[]) {
    if (!settings.value) return
    try {
      const payload = {
        ...settings.value,
        long_coin_list: longList,
        short_coin_list: shortList,
      }
      await api.post('/api/settings', payload)
      uiStore.logStore.addLog({
        message: '交易终端币种列表已自动保存。',
        level: 'info',
        timestamp: new Date().toLocaleTimeString(),
      })
      if (settings.value) {
        settings.value.long_coin_list = longList
        settings.value.short_coin_list = shortList
      }
    } catch (error) {
      console.error('Failed to save selected coin lists:', error)
      uiStore.logStore.addLog({
        message: '自动保存币种列表失败！',
        level: 'error',
        timestamp: new Date().toLocaleTimeString(),
      })
    }
  }

  return {
    settings,
    availableCoins,
    availableLongCoins,
    availableShortCoins,
    loading,
    fetchSettings,
    saveGeneralSettings,
    saveSelectedCoinLists,
    updateAvailablePools,
  }
})
