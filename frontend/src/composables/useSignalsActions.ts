/**
 * 信号配置域动作层（T11）：各业务动作（开关 / 保存表单 / 扫描范围）。
 *
 * 全部动作经由 useSignalsConfig 暴露的两条写路径落库——
 * `patchSignalsConfig`（signals/config patch）与 `toggleSignalAutoTrade`（auto-trade 开关），
 * 单字段切换走 `runOptimisticPatch`（乐观更新 → patch → 失败回滚）。
 * 表单状态与校验来自 signalsFormState.ts，本层不做任何直接 api 调用。
 */
import { useSnackbarStore } from '@/stores/snackbar'
import { normalizeSymbolInput } from './signalsFormState'
import {
  autoForm,
  autoFormDirty,
  autoFormValid,
  paperDirty,
  paperForm,
  paperFormValid,
  pushVolumeDirty,
  pushVolumeInput,
  savingAuto,
  savingAutoTrade,
  savingDingtalkPush,
  savingLiveTimeout,
  savingPaperConfig,
  savingPaperToggle,
  savingPushConfig,
  savingScan,
  savingScope,
  savingSltpGuard,
  scanStaticSymbols,
  scopeDirty,
  scopeTimeframes,
  scopeTopN,
  scopeValid,
  syncAutoForm,
} from './signalsFormState'
import { useSignalsConfig } from './useSignalsConfig'

const {
  config,
  fetchSignals,
  exitMode,
  liveExit,
  liveTimeoutEnabled,
  paperEnabled,
  patchSignalsConfig,
  pushLog,
  pushStatus,
  runOptimisticPatch,
  sltpGuardEnabled,
  status,
  toggleSignalAutoTrade,
  tracking,
} = useSignalsConfig()

// ---------------------------------------------------------------------------
// 扫描开关与扫描范围
// ---------------------------------------------------------------------------
const onToggleScan = async (value: unknown): Promise<void> => {
  const enabled = Boolean(value)
  if (savingScan.value || enabled === status.value.enabled) return
  savingScan.value = true
  const previous = status.value.enabled
  await runOptimisticPatch({
    apply: () => {
      status.value.enabled = enabled
      config.value.signal_scan_enabled = enabled
    },
    revert: () => {
      status.value.enabled = previous
      config.value.signal_scan_enabled = previous
    },
    payload: { signal_scan_enabled: enabled },
    successMessage: enabled ? '信号扫描已启用。' : '信号扫描已停用。',
    failLabel: '切换扫描开关失败',
    logMessage: '[前端] 信号扫描已' + (enabled ? '启用' : '停用') + '。',
  })
  savingScan.value = false
}

const saveScanScope = async (): Promise<void> => {
  if (!scopeValid.value || savingScope.value) return
  savingScope.value = true
  const payload = {
    signal_scan_static_symbols: [...scanStaticSymbols.value],
    signal_scan_top_n: Number(scopeTopN.value),
    signal_scan_timeframes: [...scopeTimeframes.value],
  }
  const result = await patchSignalsConfig(payload)
  if (result.ok) {
    scopeDirty.value = false
    useSnackbarStore().show({
      message: `扫描范围已保存（静态币 ${scanStaticSymbols.value.length} 个 / Top ${scopeTopN.value}）。`,
      color: 'success',
    })
    pushLog(
      '[前端] 扫描范围已保存：静态币 ' +
        (scanStaticSymbols.value.join(',') || '无') +
        `；Top ${scopeTopN.value}；周期 ${scopeTimeframes.value.join('/')}`,
      'success',
    )
    await fetchSignals(true)
  } else {
    useSnackbarStore().show({
      message: '保存扫描范围失败: ' + result.detail,
      color: 'error',
    })
  }
  savingScope.value = false
}

const setStaticSymbols = (value: unknown): void => {
  const list = Array.isArray(value) ? value : []
  // 顺序稳定：新选中的追加在尾部，避免 chips 顺序抖动
  scanStaticSymbols.value = [
    ...new Set(list.map((item) => normalizeSymbolInput(String(item))).filter(Boolean)),
  ]
  scopeDirty.value = true
}

const onScopeTopNChange = (value: number): void => {
  scopeTopN.value = value
  scopeDirty.value = true
}

const onScopeTimeframesChange = (value: unknown): void => {
  scopeTimeframes.value = Array.isArray(value) ? value.map(String) : []
  scopeDirty.value = true
}

// ---------------------------------------------------------------------------
// 推送（量能门槛 / 钉钉开关）
// ---------------------------------------------------------------------------
const onPushVolumeChange = (value: number): void => {
  pushVolumeInput.value = value
  pushVolumeDirty.value = true
}

const savePushVolume = async (): Promise<void> => {
  if (savingPushConfig.value) return
  const raw = Number(pushVolumeInput.value)
  const value = Number.isFinite(raw) && raw >= 0 ? Math.min(raw, 100) : 0
  savingPushConfig.value = true
  const previous = pushStatus.value.signal_push_volume_multiplier
  const ok = await runOptimisticPatch({
    apply: () => {
      pushStatus.value.signal_push_volume_multiplier = value
    },
    revert: () => {
      pushStatus.value.signal_push_volume_multiplier = previous
    },
    payload: { signal_push_volume_multiplier: value },
    successMessage: `推送量能门槛已保存（${value > 0 ? `${value}x` : '不过滤'}）。`,
    failLabel: '保存推送量能门槛失败',
    logMessage: `[前端] 推送量能门槛已保存: ${value > 0 ? `${value}x` : '不过滤'}`,
  })
  if (ok) pushVolumeDirty.value = false
  savingPushConfig.value = false
}

const onToggleDingtalkPush = async (value: unknown): Promise<void> => {
  const enabled = Boolean(value)
  if (savingDingtalkPush.value || enabled === pushStatus.value.signal_dingtalk_enabled) return
  savingDingtalkPush.value = true
  const previous = pushStatus.value.signal_dingtalk_enabled
  await runOptimisticPatch({
    apply: () => {
      pushStatus.value.signal_dingtalk_enabled = enabled
      config.value.signal_dingtalk_enabled = enabled
    },
    revert: () => {
      pushStatus.value.signal_dingtalk_enabled = previous
      config.value.signal_dingtalk_enabled = previous
    },
    payload: { signal_dingtalk_enabled: enabled },
    successMessage: enabled ? '币种信号钉钉推送已启用。' : '币种信号钉钉推送已停用。',
    failLabel: '切换钉钉推送开关失败',
    logMessage: '[前端] 币种信号钉钉推送已' + (enabled ? '启用' : '停用') + '。',
  })
  savingDingtalkPush.value = false
}

// ---------------------------------------------------------------------------
// 出场规则（纸面跟踪 / 实盘超时 / 止损巡检 / 出场模式 / 出场参数）
// ---------------------------------------------------------------------------
const onTogglePaper = async (value: unknown): Promise<void> => {
  const enabled = Boolean(value)
  if (savingPaperToggle.value || enabled === paperEnabled.value) return
  savingPaperToggle.value = true
  const previous = tracking.value.params.enabled
  await runOptimisticPatch({
    apply: () => {
      tracking.value.params.enabled = enabled
    },
    revert: () => {
      tracking.value.params.enabled = previous
    },
    payload: { signal_paper_enabled: enabled },
    successMessage: enabled ? '纸面跟踪已启用（只记录，不下单）。' : '纸面跟踪已停用。',
    failLabel: '切换纸面跟踪失败',
    logMessage: '[前端] 纸面跟踪已' + (enabled ? '启用' : '停用') + '。',
  })
  savingPaperToggle.value = false
}

const onToggleLiveTimeout = async (value: unknown): Promise<void> => {
  const enabled = Boolean(value)
  if (savingLiveTimeout.value || enabled === liveTimeoutEnabled.value) return
  savingLiveTimeout.value = true
  const previous = liveExit.value.enabled
  await runOptimisticPatch({
    apply: () => {
      liveExit.value.enabled = enabled
    },
    revert: () => {
      liveExit.value.enabled = previous
    },
    payload: { signal_live_exit_timeout_enabled: enabled },
    successMessage: enabled
      ? `实盘超时平仓已启用：自动仓持有满 ${liveExit.value.max_bars} 根将市价平掉。`
      : '实盘超时平仓已关闭（已有登记保留，仅对账）。',
    successLevel: enabled ? 'warning' : 'success',
    failLabel: '切换实盘超时平仓失败',
    logMessage: '[前端] 实盘超时平仓已' + (enabled ? '启用' : '关闭') + '。',
  })
  savingLiveTimeout.value = false
}

const onToggleSltpGuard = async (value: unknown): Promise<void> => {
  const enabled = Boolean(value)
  if (savingSltpGuard.value || enabled === sltpGuardEnabled.value) return
  savingSltpGuard.value = true
  const previous = liveExit.value.guard_enabled
  await runOptimisticPatch({
    apply: () => {
      liveExit.value.guard_enabled = enabled
    },
    revert: () => {
      liveExit.value.guard_enabled = previous
    },
    payload: { signal_live_sltp_guard_enabled: enabled },
    successMessage: enabled
      ? '止损巡检已启用：手动与自动仓位缺少止损时会自动补挂。'
      : '止损巡检已关闭：挂单失败或人为撤单后将不再自动补挂。',
    successLevel: enabled ? 'success' : 'warning',
    failLabel: '切换止损巡检失败',
    logMessage: '[前端] 止损巡检已' + (enabled ? '启用' : '关闭') + '。',
  })
  savingSltpGuard.value = false
}

const onChangeExitMode = async (value: unknown): Promise<void> => {
  const mode = value === 'atr' ? 'atr' : 'percent'
  if (savingPaperConfig.value || mode === exitMode.value) return
  savingPaperConfig.value = true
  const previous = config.value.signal_exit_mode
  await runOptimisticPatch({
    apply: () => {
      config.value.signal_exit_mode = mode
    },
    revert: () => {
      config.value.signal_exit_mode = previous
    },
    payload: { signal_exit_mode: mode },
    successMessage: mode === 'percent' ? '已改用现有止盈止损（实盘同款）。' : '已切换到 ATR 研究模式。',
    failLabel: '切换出场模式失败',
    logMessage: '[前端] 出场模式: ' + (mode === 'percent' ? '现有止盈止损' : 'ATR 研究模式'),
  })
  savingPaperConfig.value = false
}

const savePaperConfig = async (): Promise<void> => {
  if (savingPaperConfig.value || !paperFormValid.value) return
  savingPaperConfig.value = true
  const payload = {
    signal_paper_sl_atr: Number(paperForm.value.slAtr),
    signal_paper_tp_r: Number(paperForm.value.tpR),
    signal_paper_max_bars: Number(paperForm.value.maxBars),
    signal_live_exit_timeframe: paperForm.value.atrTimeframe,
  }
  const result = await patchSignalsConfig(payload)
  if (result.ok) {
    paperDirty.value = false
    useSnackbarStore().show({
      message: '出场参数已保存（实盘与纸面同时生效）。',
      color: 'success',
    })
    pushLog(
      `[前端] 出场参数: 止损 ${payload.signal_paper_sl_atr} ATR / 止盈 ${payload.signal_paper_tp_r}R / 最多 ${payload.signal_paper_max_bars} 根 / ATR 周期 ${payload.signal_live_exit_timeframe}`,
      'success',
    )
    await fetchSignals(true)
  } else {
    useSnackbarStore().show({
      message: '保存纸面出场参数失败: ' + result.detail,
      color: 'error',
    })
  }
  savingPaperConfig.value = false
}

// ---------------------------------------------------------------------------
// 自动开仓（开关走 auto-trade 端点，表单保存走 signals/config patch）
// ---------------------------------------------------------------------------
const onToggleAutoTrade = async (value: unknown): Promise<void> => {
  const enabled = Boolean(value)
  if (savingAutoTrade.value || enabled === config.value.signal_auto_trade_enabled) return
  savingAutoTrade.value = true
  const previous = config.value.signal_auto_trade_enabled
  config.value.signal_auto_trade_enabled = enabled
  const result = await toggleSignalAutoTrade(enabled)
  if (result.ok) {
    useSnackbarStore().show({
      message: enabled ? '自动开仓已启用。' : '自动开仓已停用。',
      color: 'success',
    })
    pushLog('[前端] 信号自动开仓已' + (enabled ? '启用' : '停用') + '。', 'info')
    await fetchSignals(true)
  } else {
    config.value.signal_auto_trade_enabled = previous
    useSnackbarStore().show({
      message: '切换自动开仓开关失败: ' + result.detail,
      color: 'error',
    })
  }
  savingAutoTrade.value = false
}

const saveAutoConfig = async (): Promise<void> => {
  if (!autoFormValid.value || savingAuto.value) return
  savingAuto.value = true
  const payload: Record<string, unknown> = {
    signal_auto_trade_enabled: config.value.signal_auto_trade_enabled,
    signal_auto_trade_directions: [...autoForm.value.directions],
    signal_auto_trade_strategies: [...autoForm.value.strategies],
    signal_auto_trade_timeframes: [...autoForm.value.timeframes],
    signal_auto_trade_confirmations: Number(autoForm.value.confirmations),
    signal_auto_trade_confirmation_window_seconds: Number(autoForm.value.confirmationWindowSeconds),
    signal_auto_trade_cooldown_seconds: Number(autoForm.value.cooldownSeconds),
    signal_auto_trade_value_usd: Number(autoForm.value.valueUsd),
    signal_auto_trade_max_positions: Number(autoForm.value.maxPositions),
  }
  const result = await patchSignalsConfig(payload)
  if (result.ok) {
    autoFormDirty.value = false
    syncAutoForm(config.value)
    useSnackbarStore().show({ message: '自动开仓配置已保存。', color: 'success' })
    pushLog('[前端] 信号自动开仓配置已保存。', 'success')
  } else {
    useSnackbarStore().show({
      message: '保存自动开仓配置失败: ' + result.detail,
      color: 'error',
    })
  }
  savingAuto.value = false
}

/** 信号配置域业务动作（依赖 core 写路径原语 + formState 表单状态） */
export function useSignalsActions() {
  return {
    // 扫描开关与范围
    onToggleScan,
    saveScanScope,
    setStaticSymbols,
    onScopeTopNChange,
    onScopeTimeframesChange,
    // 推送
    onPushVolumeChange,
    savePushVolume,
    onToggleDingtalkPush,
    // 出场规则
    onTogglePaper,
    onToggleLiveTimeout,
    onToggleSltpGuard,
    onChangeExitMode,
    savePaperConfig,
    // 自动开仓
    onToggleAutoTrade,
    saveAutoConfig,
  }
}
