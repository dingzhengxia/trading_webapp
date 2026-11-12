// frontend/src/stores/settingsStore.ts (完整代码)
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { UserSettings } from '@/models/types'
import { api } from '@/services/endpoints'
import { useUiStore } from './uiStore'
import { getErrorMessage, getErrorStatus } from '@/utils/errors'

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

  // --- 新增 ---
  enable_long_trailing_stop: false,
  long_trailing_stop_callback_rate: 1.0,
  enable_short_trailing_stop: false,
  short_trailing_stop_callback_rate: 1.0,
  // -----------

  open_maker_retries: 5,
  open_order_fill_timeout_seconds: 60,
  close_maker_retries: 3,
  close_order_fill_timeout_seconds: 12,
  unprotected_position_action: 'auto_close',
  close_price_chase_ticks: 1,
  api_max_concurrency: 3,
  api_min_interval_sec: 0.08,
  api_max_retries: 3,
  api_failure_threshold: 5,
  api_circuit_breaker_cooldown_sec: 30,
  api_418_cooldown_sec: 60,
  api_429_base_backoff_sec: 2,
  api_429_max_backoff_sec: 30,
  rebalance_method: 'multi_factor_weakest',
  rebalance_top_n: 50,
  rebalance_min_volume_usd: 20000000,
  rebalance_abs_momentum_days: 30,
  rebalance_rel_strength_days: 60,
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
      // 带时间戳防浏览器/代理缓存：刷新后必须看到服务端最新值
      const response = await api.getSettings<{
        user_settings: Partial<UserSettings>
        available_coins: string[]
        available_long_coins: string[]
        available_short_coins: string[]
      }>()
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

  async function saveGeneralSettings(
    newSettings: UserSettings | null,
  ): Promise<{ ok: boolean; detail: string }> {
    if (!newSettings) return { ok: false, detail: '配置尚未加载完成' }
    // 过滤空字符串/NaN：输入框清空时 Vuetify 给出 ''，若原样落库会让杠杆、止损百分比变成非法值
    const payload: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(newSettings)) {
      if (value === '' || value === null || value === undefined) continue
      if (typeof value === 'number' && !Number.isFinite(value)) continue
      payload[key] = value
    }
    try {
      await api.postSettings(payload)
      uiStore.logStore.addLog({
        message: '通用配置已自动保存。',
        level: 'success',
        timestamp: new Date().toLocaleTimeString(),
      })
      return { ok: true, detail: '' }
    } catch (error) {
      console.error('Failed to save settings:', error)
      // 服务端 detail 必须原样带给用户：只说“保存失败”等于让人去翻日志
      const status = getErrorStatus(error)
      const detail = `${getErrorMessage(error)}${status ? `（HTTP ${status}）` : ''}`
      uiStore.logStore.addLog({
        message: `配置保存失败：${detail}`,
        level: 'error',
        timestamp: new Date().toLocaleTimeString(),
      })
      return { ok: false, detail }
    }
  }

  /**
   * 增量更新若干设置项（后端按 key 合并），并同步内存副本。
   *
   * 直接 POST 而不更新 store 会导致“下次任意页面保存整包设置时把旧值写回”，
   * 因此所有局部设置写入都应走这里。
   */
  async function patchSettings(
    partial: Partial<UserSettings>,
  ): Promise<{ ok: boolean; detail: string }> {
    if (settings.value) {
      Object.assign(settings.value, partial)
    }
    try {
      await api.patchSettings(partial)
      return { ok: true, detail: '' }
    } catch (error) {
      console.error('Failed to patch settings:', error)
      const status = getErrorStatus(error)
      const detail = `${getErrorMessage(error)}${status ? `（HTTP ${status}）` : ''}`
      uiStore.logStore.addLog({
        message: `配置保存失败：${detail}`,
        level: 'error',
        timestamp: new Date().toLocaleTimeString(),
      })
      return { ok: false, detail }
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
    patchSettings,
    updateAvailablePools,
  }
})
