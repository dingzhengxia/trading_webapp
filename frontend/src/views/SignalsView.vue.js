import { computed, onMounted, onUnmounted, ref } from 'vue';
import api from '@/services/api';
import { useSnackbarStore } from '@/stores/snackbar';
import { useUiStore } from '@/stores/uiStore';
import { getErrorMessage, getErrorStatus } from '@/utils/errors';
import { formatIsoTime as formatTime } from '@/utils/format';
import SmartSelect from '@/components/SmartSelect.vue';
import PageCard from '@/components/PageCard.vue';
const POLL_INTERVAL_MS = 10000;
const directionOptions = [
    { title: '做多', value: 'long' },
    { title: '做空', value: 'short' },
];
const timeframeOptions = ['15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d'];
const strategyOptions = [
    { value: 'ema_cross', title: 'EMA 交叉' },
    { value: 'ma_breakout', title: '均线突破' },
    { value: 'kdj_cross', title: 'KDJ 交叉' },
    { value: 'level_breakout', title: '关键位突破 (BOS)' },
    { value: 'rsi_divergence', title: 'RSI 背离' },
    { value: 'trend_channel_breakout', title: '趋势通道突破' },
    { value: 'ob_luxalgo', title: '订单块 (LuxAlgo)' },
    { value: 'ob_fluxcharts', title: '订单块 (FluxCharts)' },
    { value: 'volatility_breakout', title: '波动率突破（观望，不开仓）' },
    { value: 'consecutive_candles', title: '连续 K 线警示（观望，不开仓）' },
];
const strategyTitleMap = new Map(strategyOptions.map((option) => [option.value, option.title]));
const defaultSignalStatus = {
    enabled: false,
    running: false,
    last_scan_at: null,
    next_scan_at: null,
    scanned_symbols: 0,
    emitted_count: 0,
    error_count: 0,
    last_error: null,
    auto_trade_enabled: false,
    last_auto_open: null,
};
const defaultSignalConfig = {
    signal_scan_enabled: false,
    signal_scan_interval_seconds: 300,
    signal_scan_static_symbols: [],
    signal_scan_top_n: 20,
    signal_scan_timeframes: ['1h', '4h'],
    signal_auto_trade_enabled: false,
    signal_auto_trade_directions: ['long', 'short'],
    signal_auto_trade_strategies: [
        'ema_cross',
        'ma_breakout',
        'kdj_cross',
        'level_breakout',
        'rsi_divergence',
        'trend_channel_breakout',
        'ob_luxalgo',
        'ob_fluxcharts',
    ],
    signal_auto_trade_timeframes: ['1h', '4h'],
    signal_auto_trade_confirmations: 1,
    signal_auto_trade_confirmation_window_seconds: 300,
    signal_auto_trade_cooldown_seconds: 3600,
    signal_auto_trade_max_positions: 5,
    signal_auto_trade_value_usd: 100,
    signal_ticker_cache_seconds: 30,
    signal_ohlcv_cache_seconds: 300,
    signal_dingtalk_enabled: true,
    signal_paper_enabled: false,
    signal_exit_mode: 'percent',
    signal_paper_sl_atr: 1.5,
    signal_paper_tp_r: 2,
    signal_paper_max_bars: 6,
    signal_live_exit_timeframe: '4h',
    signal_live_exit_timeout_enabled: false,
    signal_live_sltp_guard_enabled: true,
    signal_forward_bars: [4, 12],
};
const DIRECTION_FILTERS = ['all', 'long', 'short', 'neutral'];
const snackbarStore = useSnackbarStore();
const uiStore = useUiStore();
const status = ref({ ...defaultSignalStatus });
const signals = ref([]);
const config = ref({ ...defaultSignalConfig });
const loading = ref(false);
const scanning = ref(false);
const clearing = ref(false);
const savingScan = ref(false);
const savingAutoTrade = ref(false);
const savingAuto = ref(false);
const directionFilter = ref('all');
const savingDingtalkPush = ref(false);
const pushStatus = ref({
    dingtalk_configured: false,
    dingtalk_enabled: false,
    signal_dingtalk_enabled: true,
    signal_push_volume_multiplier: 2,
    static_symbols: [],
});
const savingPushConfig = ref(false);
const pushVolumeInput = ref(2);
const pushVolumeDirty = ref(false);
// ------------------------------------------------- 纸面跟踪（只记录不下单）
const emptyTracking = () => ({
    params: {
        enabled: false,
        exit_mode: 'percent',
        sl_atr: 1.5,
        tp_r: 2,
        max_bars: 6,
        value_usd: 100,
        forward_bars: [4, 12],
    },
    open_positions: [],
    trades: [],
    paper_stats: {
        total: 0,
        win_rate: null,
        avg_pnl_pct: null,
        avg_bars: null,
        sum_pnl_pct: null,
        by_reason: {},
    },
    forward_stats: [],
});
const tracking = ref(emptyTracking());
const savingPaperConfig = ref(false);
const savingPaperToggle = ref(false);
const paperDirty = ref(false);
const ATR_TIMEFRAMES = ['15m', '1h', '4h', '1d'];
const paperForm = ref({ slAtr: 1.5, tpR: 2, maxBars: 6, atrTimeframe: '4h' });
const paperEnabled = computed(() => tracking.value.params.enabled);
// ------------------------------------------------- 实盘出场层（超时平仓 + 登记）
const liveExit = ref({ enabled: false, guard_enabled: true, max_bars: 6, positions: [] });
const savingLiveTimeout = ref(false);
const savingSltpGuard = ref(false);
const liveTimeoutEnabled = computed(() => liveExit.value.enabled);
const sltpGuardEnabled = computed(() => liveExit.value.guard_enabled);
const exitMode = computed(() => config.value.signal_exit_mode);
const paperFormValid = computed(() => Number(paperForm.value.slAtr) >= 0.2 &&
    Number(paperForm.value.slAtr) <= 10 &&
    Number(paperForm.value.tpR) >= 0.5 &&
    Number(paperForm.value.tpR) <= 10 &&
    Number(paperForm.value.maxBars) >= 1 &&
    Number(paperForm.value.maxBars) <= 100);
// ------------------------------------------------- 扫描范围（静态币 / TopN / 周期）
const savingScope = ref(false);
const scopeDirty = ref(false);
const staticSymbolInput = ref('');
const scanStaticSymbols = ref([...defaultSignalConfig.signal_scan_static_symbols]);
const scopeTopN = ref(defaultSignalConfig.signal_scan_top_n);
const scopeTimeframes = ref([...defaultSignalConfig.signal_scan_timeframes]);
const autoForm = ref({
    directions: [...defaultSignalConfig.signal_auto_trade_directions],
    strategies: [...defaultSignalConfig.signal_auto_trade_strategies],
    timeframes: [...defaultSignalConfig.signal_auto_trade_timeframes],
    confirmations: defaultSignalConfig.signal_auto_trade_confirmations,
    confirmationWindowSeconds: defaultSignalConfig.signal_auto_trade_confirmation_window_seconds,
    cooldownSeconds: defaultSignalConfig.signal_auto_trade_cooldown_seconds,
    valueUsd: defaultSignalConfig.signal_auto_trade_value_usd,
    maxPositions: defaultSignalConfig.signal_auto_trade_max_positions,
});
const autoFormDirty = ref(false);
let pollTimer;
const autoTradeEnabled = computed(() => config.value.signal_auto_trade_enabled);
const scopeValid = computed(() => scopeTimeframes.value.length > 0 &&
    Number(scopeTopN.value) >= 1 &&
    Number(scopeTopN.value) <= 500);
const autoFormValid = computed(() => {
    const form = autoForm.value;
    return (form.directions.length > 0 &&
        form.strategies.length > 0 &&
        form.timeframes.length > 0 &&
        Number(form.confirmations) >= 1 &&
        Number(form.confirmationWindowSeconds) > 0 &&
        Number(form.cooldownSeconds) >= 0 &&
        Number(form.valueUsd) > 0 &&
        Number(form.maxPositions) >= 1);
});
const filteredSignals = computed(() => {
    const list = directionFilter.value === 'all'
        ? signals.value
        : signals.value.filter((signal) => signal.direction === directionFilter.value);
    return list.slice(0, 200);
});
const lastAutoOpenText = computed(() => {
    const value = status.value.last_auto_open;
    if (!value)
        return '—';
    if (typeof value === 'string')
        return value;
    const symbol = typeof value.symbol === 'string' ? value.symbol : '';
    const direction = typeof value.direction === 'string' ? value.direction : '';
    const at = typeof value.at === 'string' ? value.at : '';
    if (symbol) {
        const directionText = direction ? directionLabel(direction) : '';
        const atText = at ? formatTime(at) : '';
        return [symbol, directionText, atText].filter((part) => part.length > 0).join(' ');
    }
    return JSON.stringify(value);
});
const toNumber = (value, fallback) => {
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
};
const toStringArray = (value, fallback) => {
    if (!Array.isArray(value))
        return [...fallback];
    return value.filter((item) => typeof item === 'string');
};
const normalizeDirection = (value) => value === 'long' || value === 'short' || value === 'neutral' ? value : 'neutral';
const normalizeLastAutoOpen = (value) => {
    if (typeof value === 'string')
        return value;
    if (value !== null && typeof value === 'object')
        return value;
    return null;
};
const mergePushStatus = (raw) => {
    if (raw === null || typeof raw !== 'object') {
        return {
            dingtalk_configured: false,
            dingtalk_enabled: false,
            signal_dingtalk_enabled: true,
            signal_push_volume_multiplier: 2,
            static_symbols: [],
        };
    }
    const source = raw;
    return {
        dingtalk_configured: source.dingtalk_configured === true,
        dingtalk_enabled: source.dingtalk_enabled === true,
        signal_dingtalk_enabled: source.signal_dingtalk_enabled !== false,
        signal_push_volume_multiplier: toNumber(source.signal_push_volume_multiplier, 2),
        static_symbols: toStringArray(source.static_symbols, []),
    };
};
const mergeStatus = (raw) => {
    if (raw === null || typeof raw !== 'object')
        return { ...defaultSignalStatus };
    const source = raw;
    return {
        enabled: source.enabled === true,
        running: source.running === true,
        last_scan_at: typeof source.last_scan_at === 'string' ? source.last_scan_at : null,
        next_scan_at: typeof source.next_scan_at === 'string' ? source.next_scan_at : null,
        scanned_symbols: toNumber(source.scanned_symbols, 0),
        emitted_count: toNumber(source.emitted_count, 0),
        error_count: toNumber(source.error_count, 0),
        last_error: typeof source.last_error === 'string' ? source.last_error : null,
        auto_trade_enabled: source.auto_trade_enabled === true,
        last_auto_open: normalizeLastAutoOpen(source.last_auto_open),
    };
};
const mergeConfig = (raw) => {
    const source = (raw ?? {});
    const fallback = defaultSignalConfig;
    return {
        signal_scan_enabled: source.signal_scan_enabled === true,
        signal_scan_interval_seconds: toNumber(source.signal_scan_interval_seconds, fallback.signal_scan_interval_seconds),
        signal_scan_static_symbols: toStringArray(source.signal_scan_static_symbols, fallback.signal_scan_static_symbols),
        signal_scan_top_n: toNumber(source.signal_scan_top_n, fallback.signal_scan_top_n),
        signal_scan_timeframes: toStringArray(source.signal_scan_timeframes, fallback.signal_scan_timeframes),
        signal_auto_trade_enabled: source.signal_auto_trade_enabled === true,
        signal_auto_trade_directions: toStringArray(source.signal_auto_trade_directions, fallback.signal_auto_trade_directions),
        signal_auto_trade_strategies: toStringArray(source.signal_auto_trade_strategies, fallback.signal_auto_trade_strategies),
        signal_auto_trade_timeframes: toStringArray(source.signal_auto_trade_timeframes, fallback.signal_auto_trade_timeframes),
        signal_auto_trade_confirmations: toNumber(source.signal_auto_trade_confirmations, fallback.signal_auto_trade_confirmations),
        signal_auto_trade_confirmation_window_seconds: toNumber(source.signal_auto_trade_confirmation_window_seconds, fallback.signal_auto_trade_confirmation_window_seconds),
        signal_auto_trade_cooldown_seconds: toNumber(source.signal_auto_trade_cooldown_seconds, fallback.signal_auto_trade_cooldown_seconds),
        signal_auto_trade_max_positions: toNumber(source.signal_auto_trade_max_positions, fallback.signal_auto_trade_max_positions),
        signal_auto_trade_value_usd: toNumber(source.signal_auto_trade_value_usd, fallback.signal_auto_trade_value_usd),
        signal_ticker_cache_seconds: toNumber(source.signal_ticker_cache_seconds, fallback.signal_ticker_cache_seconds),
        signal_ohlcv_cache_seconds: toNumber(source.signal_ohlcv_cache_seconds, fallback.signal_ohlcv_cache_seconds),
        signal_dingtalk_enabled: source.signal_dingtalk_enabled !== false,
        signal_paper_enabled: source.signal_paper_enabled === true,
        signal_exit_mode: source.signal_exit_mode === 'atr' ? 'atr' : 'percent',
        signal_paper_sl_atr: toNumber(source.signal_paper_sl_atr, fallback.signal_paper_sl_atr),
        signal_paper_tp_r: toNumber(source.signal_paper_tp_r, fallback.signal_paper_tp_r),
        signal_paper_max_bars: toNumber(source.signal_paper_max_bars, fallback.signal_paper_max_bars),
        signal_live_exit_timeframe: ATR_TIMEFRAMES.includes(String(source.signal_live_exit_timeframe))
            ? source.signal_live_exit_timeframe
            : fallback.signal_live_exit_timeframe,
        signal_live_exit_timeout_enabled: source.signal_live_exit_timeout_enabled === true,
        signal_live_sltp_guard_enabled: source.signal_live_sltp_guard_enabled !== false,
        signal_forward_bars: Array.isArray(source.signal_forward_bars)
            ? source.signal_forward_bars.map((bar) => toNumber(bar, 4))
            : [...fallback.signal_forward_bars],
    };
};
const normalizeSignals = (raw) => {
    if (!Array.isArray(raw))
        return [];
    const result = [];
    for (const item of raw) {
        if (item === null || typeof item !== 'object')
            continue;
        const record = item;
        if (typeof record.symbol !== 'string')
            continue;
        result.push({
            id: typeof record.id === 'string'
                ? record.id
                : String(record.symbol) + '-' + String(record.created_at ?? result.length),
            created_at: typeof record.created_at === 'string' ? record.created_at : null,
            symbol: record.symbol,
            full_symbol: typeof record.full_symbol === 'string' ? record.full_symbol : null,
            timeframe: typeof record.timeframe === 'string' ? record.timeframe : '',
            strategy: typeof record.strategy === 'string' ? record.strategy : '',
            strategy_index: toNumber(record.strategy_index, 0),
            direction: normalizeDirection(record.direction),
            price: toNumber(record.price, 0),
            volume_ratio: typeof record.volume_ratio === 'number' && Number.isFinite(record.volume_ratio)
                ? record.volume_ratio
                : null,
            fwd: record.fwd !== null && typeof record.fwd === 'object'
                ? Object.fromEntries(Object.entries(record.fwd)
                    .map(([key, value]) => [key, Number(value)])
                    .filter(([, value]) => Number.isFinite(value)))
                : null,
            title: typeof record.title === 'string' ? record.title : '',
            message: typeof record.message === 'string' ? record.message : '',
        });
    }
    return result;
};
const mergeTracking = (raw) => {
    const base = emptyTracking();
    if (raw === null || typeof raw !== 'object')
        return base;
    const data = raw;
    const params = (data.params ?? {});
    return {
        params: {
            enabled: params.enabled === true,
            exit_mode: params.exit_mode === 'atr' ? 'atr' : 'percent',
            sl_atr: toNumber(params.sl_atr, base.params.sl_atr),
            tp_r: toNumber(params.tp_r, base.params.tp_r),
            max_bars: toNumber(params.max_bars, base.params.max_bars),
            value_usd: toNumber(params.value_usd, base.params.value_usd),
            forward_bars: Array.isArray(params.forward_bars)
                ? params.forward_bars.map((bar) => toNumber(bar, 4))
                : base.params.forward_bars,
        },
        open_positions: Array.isArray(data.open_positions)
            ? data.open_positions
            : [],
        trades: Array.isArray(data.trades) ? data.trades : [],
        paper_stats: {
            ...base.paper_stats,
            ...(data.paper_stats ?? {}),
        },
        forward_stats: Array.isArray(data.forward_stats)
            ? data.forward_stats
            : [],
    };
};
const syncPaperForm = (next) => {
    if (paperDirty.value)
        return;
    paperForm.value = {
        slAtr: next.params.sl_atr,
        tpR: next.params.tp_r,
        maxBars: next.params.max_bars,
        atrTimeframe: config.value.signal_live_exit_timeframe,
    };
};
const syncAutoForm = (nextConfig) => {
    if (autoFormDirty.value)
        return;
    autoForm.value = {
        directions: [...nextConfig.signal_auto_trade_directions],
        strategies: [...nextConfig.signal_auto_trade_strategies],
        timeframes: [...nextConfig.signal_auto_trade_timeframes],
        confirmations: nextConfig.signal_auto_trade_confirmations,
        confirmationWindowSeconds: nextConfig.signal_auto_trade_confirmation_window_seconds,
        cooldownSeconds: nextConfig.signal_auto_trade_cooldown_seconds,
        valueUsd: nextConfig.signal_auto_trade_value_usd,
        maxPositions: nextConfig.signal_auto_trade_max_positions,
    };
};
const markAutoFormDirty = () => {
    autoFormDirty.value = true;
};
const fetchSignals = async (silent) => {
    if (!silent)
        loading.value = true;
    try {
        const response = await api.get('/api/signals');
        const data = response.data;
        status.value = mergeStatus(data.status);
        signals.value = normalizeSignals(data.signals);
        const nextConfig = mergeConfig(data.config);
        config.value = nextConfig;
        pushStatus.value = mergePushStatus(data.push);
        if (!pushVolumeDirty.value)
            pushVolumeInput.value = pushStatus.value.signal_push_volume_multiplier;
        tracking.value = mergeTracking(data.tracking);
        liveExit.value = data.live_exit ?? { enabled: false, guard_enabled: true, max_bars: 6, positions: [] };
        syncPaperForm(tracking.value);
        syncScopeForm(nextConfig);
        syncAutoForm(nextConfig);
    }
    catch (error) {
        if (!silent) {
            snackbarStore.show({
                message: '获取信号数据失败: ' + getErrorMessage(error),
                color: 'error',
            });
        }
    }
    finally {
        if (!silent)
            loading.value = false;
    }
};
const refresh = () => {
    void fetchSignals(false);
};
const formatPrice = (value) => {
    const num = Number(value);
    if (!Number.isFinite(num))
        return '0';
    if (num >= 1000)
        return num.toLocaleString('en-US', { maximumFractionDigits: 2 });
    return num.toLocaleString('en-US', { maximumFractionDigits: 6 });
};
const directionLabel = (direction) => {
    const labels = { long: '做多', short: '做空', neutral: '观望' };
    return labels[direction] ?? direction;
};
const directionColor = (direction) => {
    // 用户偏好：红跌绿涨（做多绿、做空红）
    if (direction === 'long')
        return 'green';
    if (direction === 'short')
        return 'red';
    return 'grey';
};
const strategyLabel = (strategy) => strategyTitleMap.get(strategy) ?? strategy;
// 量能只记录不拦截：倍数照实展示，是否达到推送门槛用颜色区分（静态币始终推送）
const formatPct = (value) => {
    const num = Number(value);
    if (!Number.isFinite(num))
        return '—';
    return `${num >= 0 ? '+' : ''}${num.toFixed(2)}%`;
};
const pctClass = (value) => {
    const num = Number(value);
    if (!Number.isFinite(num))
        return 'text-grey';
    // 用户偏好：红跌绿涨
    return num >= 0 ? 'text-success' : 'text-error';
};
const exitReasonLabel = (reason) => {
    const labels = { stop: '止损', target: '止盈', time: '超时' };
    return labels[reason] ?? reason;
};
const fwdLabel = (signal) => {
    if (!signal.fwd)
        return '—';
    const bars = tracking.value.params.forward_bars;
    const parts = bars
        .map((bar) => (signal.fwd && signal.fwd[String(bar)] !== undefined
        ? `T+${bar} ${formatPct(signal.fwd[String(bar)])}`
        : ''))
        .filter((part) => part.length > 0);
    return parts.length > 0 ? parts.join(' / ') : '—';
};
const volumeLabel = (signal) => signal.volume_ratio == null ? '—' : `${signal.volume_ratio.toFixed(1)}x`;
const volumeClass = (signal) => {
    if (signal.volume_ratio == null)
        return 'text-grey';
    const threshold = pushStatus.value.signal_push_volume_multiplier || 2;
    const isStatic = pushStatus.value.static_symbols.includes(signal.symbol);
    return signal.volume_ratio >= threshold || isStatic ? 'text-success font-weight-medium' : 'text-grey';
};
const plainMessage = (value) => value
    .replace(/^#+\s*/gm, '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/^>\s*/gm, '')
    .replace(/^---+$/gm, '')
    .replace(/\n{2,}/g, '\n')
    .trim();
const isDirectionFilter = (value) => typeof value === 'string' && DIRECTION_FILTERS.includes(value);
const onDirectionFilterChange = (value) => {
    if (isDirectionFilter(value)) {
        directionFilter.value = value;
        return;
    }
    if (value === null || value === undefined) {
        directionFilter.value = 'all';
    }
};
const pushLog = (message, level) => {
    uiStore.logStore.addLog({
        message,
        level,
        timestamp: new Date().toLocaleTimeString(),
    });
};
const onToggleScan = async (value) => {
    const enabled = Boolean(value);
    if (savingScan.value || enabled === status.value.enabled)
        return;
    savingScan.value = true;
    const previous = status.value.enabled;
    status.value.enabled = enabled;
    try {
        const response = await api.post('/api/signals/config', {
            signal_scan_enabled: enabled,
        });
        if (response.data.config) {
            config.value = mergeConfig({ ...config.value, ...response.data.config });
        }
        config.value.signal_scan_enabled = enabled;
        snackbarStore.show({
            message: enabled ? '信号扫描已启用。' : '信号扫描已停用。',
            color: 'success',
        });
        pushLog('[前端] 信号扫描已' + (enabled ? '启用' : '停用') + '。', 'info');
        await fetchSignals(true);
    }
    catch (error) {
        status.value.enabled = previous;
        config.value.signal_scan_enabled = previous;
        snackbarStore.show({
            message: '切换扫描开关失败: ' + getErrorMessage(error),
            color: 'error',
        });
    }
    finally {
        savingScan.value = false;
    }
};
const syncScopeForm = (nextConfig) => {
    // 有未保存的编辑时不回填，避免 10 秒轮询覆盖用户输入
    if (scopeDirty.value)
        return;
    scanStaticSymbols.value = [...nextConfig.signal_scan_static_symbols];
    scopeTopN.value = nextConfig.signal_scan_top_n;
    scopeTimeframes.value = [...nextConfig.signal_scan_timeframes];
};
const normalizeSymbolInput = (value) => value.trim().toUpperCase().split('/')[0].split(':')[0];
const addStaticSymbol = () => {
    const symbol = normalizeSymbolInput(staticSymbolInput.value);
    if (!symbol)
        return;
    if (!scanStaticSymbols.value.includes(symbol)) {
        scanStaticSymbols.value = [...scanStaticSymbols.value, symbol];
        scopeDirty.value = true;
    }
    staticSymbolInput.value = '';
};
const removeStaticSymbol = (symbol) => {
    scanStaticSymbols.value = scanStaticSymbols.value.filter((item) => item !== symbol);
    scopeDirty.value = true;
};
const saveScanScope = async () => {
    if (!scopeValid.value || savingScope.value)
        return;
    savingScope.value = true;
    try {
        const payload = {
            signal_scan_static_symbols: [...scanStaticSymbols.value],
            signal_scan_top_n: Number(scopeTopN.value),
            signal_scan_timeframes: [...scopeTimeframes.value],
        };
        const response = await api.post('/api/signals/config', payload);
        if (response.data.config) {
            config.value = mergeConfig({ ...config.value, ...response.data.config });
        }
        scopeDirty.value = false;
        snackbarStore.show({
            message: `扫描范围已保存（静态币 ${scanStaticSymbols.value.length} 个 / Top ${scopeTopN.value}）。`,
            color: 'success',
        });
        pushLog('[前端] 扫描范围已保存：静态币 ' +
            (scanStaticSymbols.value.join(',') || '无') +
            `；Top ${scopeTopN.value}；周期 ${scopeTimeframes.value.join('/')}`, 'success');
        await fetchSignals(true);
    }
    catch (error) {
        snackbarStore.show({
            message: '保存扫描范围失败: ' + getErrorMessage(error),
            color: 'error',
        });
    }
    finally {
        savingScope.value = false;
    }
};
const onTogglePaper = async (value) => {
    const enabled = Boolean(value);
    if (savingPaperToggle.value || enabled === paperEnabled.value)
        return;
    savingPaperToggle.value = true;
    const previous = tracking.value.params.enabled;
    tracking.value.params.enabled = enabled;
    try {
        await api.post('/api/signals/config', { signal_paper_enabled: enabled });
        snackbarStore.show({
            message: enabled ? '纸面跟踪已启用（只记录，不下单）。' : '纸面跟踪已停用。',
            color: 'success',
        });
        pushLog('[前端] 纸面跟踪已' + (enabled ? '启用' : '停用') + '。', 'info');
        await fetchSignals(true);
    }
    catch (error) {
        tracking.value.params.enabled = previous;
        snackbarStore.show({
            message: '切换纸面跟踪失败: ' + getErrorMessage(error),
            color: 'error',
        });
    }
    finally {
        savingPaperToggle.value = false;
    }
};
const onToggleLiveTimeout = async (value) => {
    const enabled = Boolean(value);
    if (savingLiveTimeout.value || enabled === liveTimeoutEnabled.value)
        return;
    savingLiveTimeout.value = true;
    const previous = liveExit.value.enabled;
    liveExit.value.enabled = enabled;
    try {
        await api.post('/api/signals/config', { signal_live_exit_timeout_enabled: enabled });
        snackbarStore.show({
            message: enabled
                ? `实盘超时平仓已启用：自动仓持有满 ${liveExit.value.max_bars} 根将市价平掉。`
                : '实盘超时平仓已关闭（已有登记保留，仅对账）。',
            color: enabled ? 'warning' : 'success',
        });
        pushLog('[前端] 实盘超时平仓已' + (enabled ? '启用' : '关闭') + '。', enabled ? 'warning' : 'info');
        await fetchSignals(true);
    }
    catch (error) {
        liveExit.value.enabled = previous;
        snackbarStore.show({
            message: '切换实盘超时平仓失败: ' + getErrorMessage(error),
            color: 'error',
        });
    }
    finally {
        savingLiveTimeout.value = false;
    }
};
const onToggleSltpGuard = async (value) => {
    const enabled = Boolean(value);
    if (savingSltpGuard.value || enabled === sltpGuardEnabled.value)
        return;
    savingSltpGuard.value = true;
    const previous = liveExit.value.guard_enabled;
    liveExit.value.guard_enabled = enabled;
    try {
        await api.post('/api/signals/config', { signal_live_sltp_guard_enabled: enabled });
        snackbarStore.show({
            message: enabled
                ? '止损巡检已启用：手动与自动仓位缺少止损时会自动补挂。'
                : '止损巡检已关闭：挂单失败或人为撤单后将不再自动补挂。',
            color: enabled ? 'success' : 'warning',
        });
        pushLog('[前端] 止损巡检已' + (enabled ? '启用' : '关闭') + '。', enabled ? 'success' : 'warning');
        await fetchSignals(true);
    }
    catch (error) {
        liveExit.value.guard_enabled = previous;
        snackbarStore.show({
            message: '切换止损巡检失败: ' + getErrorMessage(error),
            color: 'error',
        });
    }
    finally {
        savingSltpGuard.value = false;
    }
};
const onChangeExitMode = async (value) => {
    const mode = value === 'atr' ? 'atr' : 'percent';
    if (savingPaperConfig.value || mode === exitMode.value)
        return;
    savingPaperConfig.value = true;
    const previous = config.value.signal_exit_mode;
    config.value.signal_exit_mode = mode;
    try {
        await api.post('/api/signals/config', { signal_exit_mode: mode });
        snackbarStore.show({
            message: mode === 'percent' ? '已改用现有止盈止损（实盘同款）。' : '已切换到 ATR 研究模式。',
            color: 'success',
        });
        pushLog('[前端] 出场模式: ' + (mode === 'percent' ? '现有止盈止损' : 'ATR 研究模式'), 'info');
        await fetchSignals(true);
    }
    catch (error) {
        config.value.signal_exit_mode = previous;
        snackbarStore.show({
            message: '切换出场模式失败: ' + getErrorMessage(error),
            color: 'error',
        });
    }
    finally {
        savingPaperConfig.value = false;
    }
};
const savePaperConfig = async () => {
    if (savingPaperConfig.value || !paperFormValid.value)
        return;
    savingPaperConfig.value = true;
    const payload = {
        signal_paper_sl_atr: Number(paperForm.value.slAtr),
        signal_paper_tp_r: Number(paperForm.value.tpR),
        signal_paper_max_bars: Number(paperForm.value.maxBars),
        signal_live_exit_timeframe: paperForm.value.atrTimeframe,
    };
    try {
        await api.post('/api/signals/config', payload);
        paperDirty.value = false;
        snackbarStore.show({ message: '出场参数已保存（实盘与纸面同时生效）。', color: 'success' });
        pushLog(`[前端] 出场参数: 止损 ${payload.signal_paper_sl_atr} ATR / 止盈 ${payload.signal_paper_tp_r}R / 最多 ${payload.signal_paper_max_bars} 根 / ATR 周期 ${payload.signal_live_exit_timeframe}`, 'success');
        await fetchSignals(true);
    }
    catch (error) {
        snackbarStore.show({
            message: '保存纸面出场参数失败: ' + getErrorMessage(error),
            color: 'error',
        });
    }
    finally {
        savingPaperConfig.value = false;
    }
};
const savePushVolume = async () => {
    if (savingPushConfig.value)
        return;
    const raw = Number(pushVolumeInput.value);
    const value = Number.isFinite(raw) && raw >= 0 ? Math.min(raw, 100) : 0;
    savingPushConfig.value = true;
    const previous = pushStatus.value.signal_push_volume_multiplier;
    try {
        await api.post('/api/signals/config', { signal_push_volume_multiplier: value });
        pushStatus.value.signal_push_volume_multiplier = value;
        pushVolumeDirty.value = false;
        const label = value > 0 ? `${value}x` : '不过滤';
        snackbarStore.show({ message: `推送量能门槛已保存（${label}）。`, color: 'success' });
        pushLog(`[前端] 推送量能门槛已保存: ${label}`, 'success');
        await fetchSignals(true);
    }
    catch (error) {
        pushStatus.value.signal_push_volume_multiplier = previous;
        snackbarStore.show({
            message: '保存推送量能门槛失败: ' + getErrorMessage(error),
            color: 'error',
        });
    }
    finally {
        savingPushConfig.value = false;
    }
};
const onToggleDingtalkPush = async (value) => {
    const enabled = Boolean(value);
    if (savingDingtalkPush.value || enabled === pushStatus.value.signal_dingtalk_enabled)
        return;
    savingDingtalkPush.value = true;
    const previous = pushStatus.value.signal_dingtalk_enabled;
    pushStatus.value.signal_dingtalk_enabled = enabled;
    config.value.signal_dingtalk_enabled = enabled;
    try {
        await api.post('/api/signals/config', { signal_dingtalk_enabled: enabled });
        snackbarStore.show({
            message: enabled ? '币种信号钉钉推送已启用。' : '币种信号钉钉推送已停用。',
            color: 'success',
        });
        pushLog('[前端] 币种信号钉钉推送已' + (enabled ? '启用' : '停用') + '。', 'info');
        await fetchSignals(true);
    }
    catch (error) {
        pushStatus.value.signal_dingtalk_enabled = previous;
        config.value.signal_dingtalk_enabled = previous;
        snackbarStore.show({
            message: '切换钉钉推送开关失败: ' + getErrorMessage(error),
            color: 'error',
        });
    }
    finally {
        savingDingtalkPush.value = false;
    }
};
const onToggleAutoTrade = async (value) => {
    const enabled = Boolean(value);
    if (savingAutoTrade.value || enabled === config.value.signal_auto_trade_enabled)
        return;
    savingAutoTrade.value = true;
    const previous = config.value.signal_auto_trade_enabled;
    config.value.signal_auto_trade_enabled = enabled;
    try {
        await api.post('/api/signals/auto-trade', { enabled });
        snackbarStore.show({
            message: enabled ? '自动开仓已启用。' : '自动开仓已停用。',
            color: 'success',
        });
        pushLog('[前端] 信号自动开仓已' + (enabled ? '启用' : '停用') + '。', 'info');
        await fetchSignals(true);
    }
    catch (error) {
        config.value.signal_auto_trade_enabled = previous;
        snackbarStore.show({
            message: '切换自动开仓开关失败: ' + getErrorMessage(error),
            color: 'error',
        });
    }
    finally {
        savingAutoTrade.value = false;
    }
};
const buildAutoConfigPayload = () => ({
    signal_auto_trade_enabled: config.value.signal_auto_trade_enabled,
    signal_auto_trade_directions: [...autoForm.value.directions],
    signal_auto_trade_strategies: [...autoForm.value.strategies],
    signal_auto_trade_timeframes: [...autoForm.value.timeframes],
    signal_auto_trade_confirmations: Number(autoForm.value.confirmations),
    signal_auto_trade_confirmation_window_seconds: Number(autoForm.value.confirmationWindowSeconds),
    signal_auto_trade_cooldown_seconds: Number(autoForm.value.cooldownSeconds),
    signal_auto_trade_value_usd: Number(autoForm.value.valueUsd),
    signal_auto_trade_max_positions: Number(autoForm.value.maxPositions),
});
const saveAutoConfig = async () => {
    if (!autoFormValid.value || savingAuto.value)
        return;
    savingAuto.value = true;
    try {
        const response = await api.post('/api/signals/config', buildAutoConfigPayload());
        if (response.data.config) {
            config.value = mergeConfig({ ...config.value, ...response.data.config });
        }
        autoFormDirty.value = false;
        syncAutoForm(config.value);
        snackbarStore.show({ message: '自动开仓配置已保存。', color: 'success' });
        pushLog('[前端] 信号自动开仓配置已保存。', 'success');
    }
    catch (error) {
        snackbarStore.show({
            message: '保存自动开仓配置失败: ' + getErrorMessage(error),
            color: 'error',
        });
    }
    finally {
        savingAuto.value = false;
    }
};
const scanNow = async () => {
    if (scanning.value)
        return;
    scanning.value = true;
    try {
        const response = await api.post('/api/signals/scan');
        snackbarStore.show({
            message: response.data?.message ?? '扫描任务已提交。',
            color: 'success',
        });
        pushLog('[前端] 已提交信号扫描任务。', 'info');
        await fetchSignals(true);
    }
    catch (error) {
        const statusCode = getErrorStatus(error);
        const isConflict = statusCode === 409;
        snackbarStore.show({
            message: isConflict
                ? '已有扫描任务正在运行，请稍后再试。'
                : '提交扫描失败: ' + getErrorMessage(error),
            color: isConflict ? 'warning' : 'error',
        });
    }
    finally {
        scanning.value = false;
    }
};
const clearSignals = async () => {
    if (clearing.value)
        return;
    clearing.value = true;
    try {
        await api.post('/api/signals/clear');
        signals.value = [];
        snackbarStore.show({ message: '信号已清空。', color: 'success' });
        pushLog('[前端] 已清空信号列表。', 'info');
        await fetchSignals(true);
    }
    catch (error) {
        snackbarStore.show({
            message: '清空信号失败: ' + getErrorMessage(error),
            color: 'error',
        });
    }
    finally {
        clearing.value = false;
    }
};
const stopPolling = () => {
    if (pollTimer !== undefined) {
        window.clearInterval(pollTimer);
        pollTimer = undefined;
    }
};
const startPolling = () => {
    stopPolling();
    pollTimer = window.setInterval(() => {
        if (document.visibilityState === 'visible') {
            void fetchSignals(true);
        }
    }, POLL_INTERVAL_MS);
};
const onVisibilityChange = () => {
    if (document.visibilityState === 'visible') {
        void fetchSignals(true);
    }
};
onMounted(() => {
    void fetchSignals(true);
    startPolling();
    document.addEventListener('visibilitychange', onVisibilityChange);
});
onUnmounted(() => {
    stopPolling();
    document.removeEventListener('visibilitychange', onVisibilityChange);
});
const __VLS_ctx = {};
let __VLS_components;
let __VLS_intrinsics;
let __VLS_directives;
void __VLS_ctx, __VLS_components, __VLS_intrinsics, __VLS_directives;
const __VLS_template = () => {
    __VLS_withDotValue(status, {});
    __VLS_withDotValue(clearing, {});
    __VLS_withDotValue(signals, {});
    __VLS_withDotValue(scanStaticSymbols, {});
    __VLS_withDotValue(staticSymbolInput, {});
    __VLS_withDotValue(scopeDirty, {});
    __VLS_withDotValue(scopeValid, {});
    __VLS_withDotValue(autoTradeEnabled, {});
    __VLS_withDotValue(pushStatus, {});
    __VLS_withDotValue(pushVolumeDirty, {});
    __VLS_withDotValue(autoForm, {});
    __VLS_withDotValue(autoFormValid, {});
    __VLS_withDotValue(paperEnabled, {});
    __VLS_withDotValue(liveTimeoutEnabled, {});
    __VLS_withDotValue(tracking, {});
    __VLS_withDotValue(exitMode, {});
    __VLS_withDotValue(paperForm, {});
    __VLS_withDotValue(paperDirty, {});
    __VLS_withDotValue(paperFormValid, {});
    __VLS_withDotValue(liveExit, {});
    __VLS_withDotValue(filteredSignals, {});
    void {};
    /** @type {__VLS_StyleScopedClasses['signal-table']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
    const __VLS_0 = PageCard || PageCard;
    // @ts-ignore
    const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
        // @ts-ignore
        icon: "mdi-radar", title: "信号扫描", error: (status.value.last_error),
    }));
    const __VLS_2 = __VLS_1({
        icon: "mdi-radar",
        title: "信号扫描",
        error: (status.value.last_error),
    }, ...__VLS_functionalComponentArgsRest(__VLS_1));
    var __VLS_3;
    const { default: __VLS_5 } = __VLS_nonNull(__VLS_3.slots);
    {
        const { badges: __VLS_6 } = __VLS_nonNull(__VLS_3.slots);
        let __VLS_7;
        /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
        vChip;
        // @ts-ignore
        const __VLS_8 = __VLS_asFunctionalComponent1(__VLS_7, new __VLS_7({
            // @ts-ignore
            size: "small", variant: "tonal", color: (status.value.running ? 'warning' : 'success'),
        }));
        const __VLS_9 = __VLS_8({
            size: "small",
            variant: "tonal",
            color: (status.value.running ? 'warning' : 'success'),
        }, ...__VLS_functionalComponentArgsRest(__VLS_8));
        var __VLS_10;
        const { default: __VLS_12 } = __VLS_nonNull(__VLS_10.slots);
        (status.value.running ? '扫描中' : '空闲');
        // @ts-ignore
        [status, status, status,];
        let __VLS_13;
        /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
        vChip;
        // @ts-ignore
        const __VLS_14 = __VLS_asFunctionalComponent1(__VLS_13, new __VLS_13({
            // @ts-ignore
            size: "small", variant: "tonal", color: (status.value.enabled ? 'success' : 'grey'),
        }));
        const __VLS_15 = __VLS_14({
            size: "small",
            variant: "tonal",
            color: (status.value.enabled ? 'success' : 'grey'),
        }, ...__VLS_functionalComponentArgsRest(__VLS_14));
        var __VLS_16;
        const { default: __VLS_18 } = __VLS_nonNull(__VLS_16.slots);
        (status.value.enabled ? '扫描已启用' : '扫描已停用');
        // @ts-ignore
        [status, status,];
        // @ts-ignore
        [];
    }
    let __VLS_19;
    /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
    vRow;
    // @ts-ignore
    const __VLS_20 = __VLS_asFunctionalComponent1(__VLS_19, new __VLS_19({
        // @ts-ignore
        dense: true, align: "center",
    }));
    const __VLS_21 = __VLS_20({
        dense: true,
        align: "center",
    }, ...__VLS_functionalComponentArgsRest(__VLS_20));
    var __VLS_22;
    const { default: __VLS_24 } = __VLS_nonNull(__VLS_22.slots);
    let __VLS_25;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_26 = __VLS_asFunctionalComponent1(__VLS_25, new __VLS_25({
        // @ts-ignore
        cols: "12", sm: "6", md: "3",
    }));
    const __VLS_27 = __VLS_26({
        cols: "12",
        sm: "6",
        md: "3",
    }, ...__VLS_functionalComponentArgsRest(__VLS_26));
    var __VLS_28;
    const { default: __VLS_30 } = __VLS_nonNull(__VLS_28.slots);
    let __VLS_31;
    /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch'] | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
    vSwitch;
    // @ts-ignore
    const __VLS_32 = __VLS_asFunctionalComponent1(__VLS_31, new __VLS_31({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (status.value.enabled), loading: (__VLS_unwrap(savingScan, {})), label: "启用信号扫描", color: "primary", inset: true, hideDetails: true,
    }));
    const __VLS_33 = __VLS_32({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (status.value.enabled),
        loading: (__VLS_unwrap(savingScan, {})),
        label: "启用信号扫描",
        color: "primary",
        inset: true,
        hideDetails: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_32));
    let __VLS_36;
    const __VLS_37 = {
        /** @type {typeof __VLS_36.'update:modelValue'} */
        'onUpdate:modelValue': (__VLS_unwrap(onToggleScan, {})),
    };
    void __VLS_37;
    var __VLS_34;
    var __VLS_35;
    // @ts-ignore
    [status, savingScan, onToggleScan,];
    let __VLS_38;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_39 = __VLS_asFunctionalComponent1(__VLS_38, new __VLS_38({
        // @ts-ignore
        cols: "12", md: "9",
    }));
    const __VLS_40 = __VLS_39({
        cols: "12",
        md: "9",
    }, ...__VLS_functionalComponentArgsRest(__VLS_39));
    var __VLS_41;
    const { default: __VLS_43 } = __VLS_nonNull(__VLS_41.slots);
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "d-flex flex-wrap ga-2 align-center" },
    });
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['flex-wrap']} */ ;
    /** @type {__VLS_StyleScopedClasses['ga-2']} */ ;
    /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
    let __VLS_44;
    /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
    vChip;
    // @ts-ignore
    const __VLS_45 = __VLS_asFunctionalComponent1(__VLS_44, new __VLS_44({
        // @ts-ignore
        size: "small", variant: "tonal", prependIcon: "mdi-clock-outline",
    }));
    const __VLS_46 = __VLS_45({
        size: "small",
        variant: "tonal",
        prependIcon: "mdi-clock-outline",
    }, ...__VLS_functionalComponentArgsRest(__VLS_45));
    var __VLS_47;
    const { default: __VLS_49 } = __VLS_nonNull(__VLS_47.slots);
    (__VLS_unwrap(formatTime, {})(status.value.last_scan_at));
    // @ts-ignore
    [status, formatTime,];
    let __VLS_50;
    /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
    vChip;
    // @ts-ignore
    const __VLS_51 = __VLS_asFunctionalComponent1(__VLS_50, new __VLS_50({
        // @ts-ignore
        size: "small", variant: "tonal", prependIcon: "mdi-timer-outline",
    }));
    const __VLS_52 = __VLS_51({
        size: "small",
        variant: "tonal",
        prependIcon: "mdi-timer-outline",
    }, ...__VLS_functionalComponentArgsRest(__VLS_51));
    var __VLS_53;
    const { default: __VLS_55 } = __VLS_nonNull(__VLS_53.slots);
    (__VLS_unwrap(formatTime, {})(status.value.next_scan_at));
    // @ts-ignore
    [status, formatTime,];
    let __VLS_56;
    /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
    vChip;
    // @ts-ignore
    const __VLS_57 = __VLS_asFunctionalComponent1(__VLS_56, new __VLS_56({
        // @ts-ignore
        size: "small", variant: "tonal", prependIcon: "mdi-format-list-bulleted",
    }));
    const __VLS_58 = __VLS_57({
        size: "small",
        variant: "tonal",
        prependIcon: "mdi-format-list-bulleted",
    }, ...__VLS_functionalComponentArgsRest(__VLS_57));
    var __VLS_59;
    const { default: __VLS_61 } = __VLS_nonNull(__VLS_59.slots);
    (status.value.scanned_symbols);
    // @ts-ignore
    [status,];
    let __VLS_62;
    /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
    vChip;
    // @ts-ignore
    const __VLS_63 = __VLS_asFunctionalComponent1(__VLS_62, new __VLS_62({
        // @ts-ignore
        size: "small", variant: "tonal", prependIcon: "mdi-signal",
    }));
    const __VLS_64 = __VLS_63({
        size: "small",
        variant: "tonal",
        prependIcon: "mdi-signal",
    }, ...__VLS_functionalComponentArgsRest(__VLS_63));
    var __VLS_65;
    const { default: __VLS_67 } = __VLS_nonNull(__VLS_65.slots);
    (status.value.emitted_count);
    // @ts-ignore
    [status,];
    let __VLS_68;
    /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
    vChip;
    // @ts-ignore
    const __VLS_69 = __VLS_asFunctionalComponent1(__VLS_68, new __VLS_68({
        // @ts-ignore
        size: "small", variant: "tonal", prependIcon: "mdi-robot", color: (status.value.auto_trade_enabled ? 'success' : 'grey'),
    }));
    const __VLS_70 = __VLS_69({
        size: "small",
        variant: "tonal",
        prependIcon: "mdi-robot",
        color: (status.value.auto_trade_enabled ? 'success' : 'grey'),
    }, ...__VLS_functionalComponentArgsRest(__VLS_69));
    var __VLS_71;
    const { default: __VLS_73 } = __VLS_nonNull(__VLS_71.slots);
    (status.value.auto_trade_enabled ? '已启用' : '已停用');
    // @ts-ignore
    [status, status,];
    let __VLS_74;
    /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
    vChip;
    // @ts-ignore
    const __VLS_75 = __VLS_asFunctionalComponent1(__VLS_74, new __VLS_74({
        // @ts-ignore
        size: "small", variant: "tonal", color: (status.value.error_count > 0 ? 'error' : undefined), prependIcon: "mdi-alert-circle-outline",
    }));
    const __VLS_76 = __VLS_75({
        size: "small",
        variant: "tonal",
        color: (status.value.error_count > 0 ? 'error' : undefined),
        prependIcon: "mdi-alert-circle-outline",
    }, ...__VLS_functionalComponentArgsRest(__VLS_75));
    var __VLS_77;
    const { default: __VLS_79 } = __VLS_nonNull(__VLS_77.slots);
    (status.value.error_count);
    // @ts-ignore
    [status, status,];
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "d-flex flex-wrap align-center ga-2 mt-3" },
    });
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['flex-wrap']} */ ;
    /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
    /** @type {__VLS_StyleScopedClasses['ga-2']} */ ;
    /** @type {__VLS_StyleScopedClasses['mt-3']} */ ;
    let __VLS_80;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_81 = __VLS_asFunctionalComponent1(__VLS_80, new __VLS_80({
        // @ts-ignore
        ...{ 'onClick': {} }, color: "primary", variant: "tonal", prependIcon: "mdi-magnify-scan", loading: (__VLS_unwrap(scanning, {})), disabled: (__VLS_unwrap(scanning, {})),
    }));
    const __VLS_82 = __VLS_81({
        ...{ 'onClick': {} },
        color: "primary",
        variant: "tonal",
        prependIcon: "mdi-magnify-scan",
        loading: (__VLS_unwrap(scanning, {})),
        disabled: (__VLS_unwrap(scanning, {})),
    }, ...__VLS_functionalComponentArgsRest(__VLS_81));
    let __VLS_85;
    const __VLS_86 = {
        /** @type {typeof __VLS_85.click} */
        onClick: (__VLS_unwrap(scanNow, {})),
    };
    void __VLS_86;
    var __VLS_83;
    var __VLS_84;
    const { default: __VLS_87 } = __VLS_nonNull(__VLS_83.slots);
    // @ts-ignore
    [scanning, scanning, scanNow,];
    let __VLS_88;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_89 = __VLS_asFunctionalComponent1(__VLS_88, new __VLS_88({
        // @ts-ignore
        ...{ 'onClick': {} }, color: "warning", variant: "tonal", prependIcon: "mdi-broom", loading: (clearing.value), disabled: (clearing.value || signals.value.length === 0),
    }));
    const __VLS_90 = __VLS_89({
        ...{ 'onClick': {} },
        color: "warning",
        variant: "tonal",
        prependIcon: "mdi-broom",
        loading: (clearing.value),
        disabled: (clearing.value || signals.value.length === 0),
    }, ...__VLS_functionalComponentArgsRest(__VLS_89));
    let __VLS_93;
    const __VLS_94 = {
        /** @type {typeof __VLS_93.click} */
        onClick: (__VLS_unwrap(clearSignals, {})),
    };
    void __VLS_94;
    var __VLS_91;
    var __VLS_92;
    const { default: __VLS_95 } = __VLS_nonNull(__VLS_91.slots);
    // @ts-ignore
    [clearing, clearing, signals, clearSignals,];
    let __VLS_96;
    /** @ts-ignore @type { | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer'] | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer']} */
    vSpacer;
    // @ts-ignore
    const __VLS_97 = __VLS_asFunctionalComponent1(__VLS_96, new __VLS_96({
    // @ts-ignore
    }));
    const __VLS_98 = __VLS_97({}, ...__VLS_functionalComponentArgsRest(__VLS_97));
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
        ...{ class: "text-caption text-grey" },
    });
    /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
    let __VLS_101;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_102 = __VLS_asFunctionalComponent1(__VLS_101, new __VLS_101({
        // @ts-ignore
        ...{ 'onClick': {} }, variant: "text", prependIcon: "mdi-refresh", loading: (__VLS_unwrap(loading, {})),
    }));
    const __VLS_103 = __VLS_102({
        ...{ 'onClick': {} },
        variant: "text",
        prependIcon: "mdi-refresh",
        loading: (__VLS_unwrap(loading, {})),
    }, ...__VLS_functionalComponentArgsRest(__VLS_102));
    let __VLS_106;
    const __VLS_107 = {
        /** @type {typeof __VLS_106.click} */
        onClick: (__VLS_unwrap(refresh, {})),
    };
    void __VLS_107;
    var __VLS_104;
    var __VLS_105;
    const { default: __VLS_108 } = __VLS_nonNull(__VLS_104.slots);
    // @ts-ignore
    [loading, refresh,];
    let __VLS_109;
    /** @ts-ignore @type { | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider'] | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider']} */
    vDivider;
    // @ts-ignore
    const __VLS_110 = __VLS_asFunctionalComponent1(__VLS_109, new __VLS_109({
        // @ts-ignore
        ...{ class: "my-4" },
    }));
    const __VLS_111 = __VLS_110({
        ...{ class: "my-4" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_110));
    /** @type {__VLS_StyleScopedClasses['my-4']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "d-flex align-center flex-wrap ga-2 mb-3" },
    });
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
    /** @type {__VLS_StyleScopedClasses['flex-wrap']} */ ;
    /** @type {__VLS_StyleScopedClasses['ga-2']} */ ;
    /** @type {__VLS_StyleScopedClasses['mb-3']} */ ;
    let __VLS_114;
    /** @ts-ignore @type { | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon'] | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon']} */
    vIcon;
    // @ts-ignore
    const __VLS_115 = __VLS_asFunctionalComponent1(__VLS_114, new __VLS_114({
        // @ts-ignore
        size: "18", color: "primary",
    }));
    const __VLS_116 = __VLS_115({
        size: "18",
        color: "primary",
    }, ...__VLS_functionalComponentArgsRest(__VLS_115));
    var __VLS_117;
    const { default: __VLS_119 } = __VLS_nonNull(__VLS_117.slots);
    // @ts-ignore
    [];
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
        ...{ class: "text-subtitle-1 font-weight-medium" },
    });
    /** @type {__VLS_StyleScopedClasses['text-subtitle-1']} */ ;
    /** @type {__VLS_StyleScopedClasses['font-weight-medium']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
        ...{ class: "text-caption text-grey" },
    });
    /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
    let __VLS_120;
    /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
    vRow;
    // @ts-ignore
    const __VLS_121 = __VLS_asFunctionalComponent1(__VLS_120, new __VLS_120({
        // @ts-ignore
        dense: true,
    }));
    const __VLS_122 = __VLS_121({
        dense: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_121));
    var __VLS_123;
    const { default: __VLS_125 } = __VLS_nonNull(__VLS_123.slots);
    let __VLS_126;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_127 = __VLS_asFunctionalComponent1(__VLS_126, new __VLS_126({
        // @ts-ignore
        cols: "12", md: "5",
    }));
    const __VLS_128 = __VLS_127({
        cols: "12",
        md: "5",
    }, ...__VLS_functionalComponentArgsRest(__VLS_127));
    var __VLS_129;
    const { default: __VLS_131 } = __VLS_nonNull(__VLS_129.slots);
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "text-caption text-grey mb-1" },
    });
    /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
    /** @type {__VLS_StyleScopedClasses['mb-1']} */ ;
    (scanStaticSymbols.value.length);
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "d-flex flex-wrap align-center ga-1 mb-2 static-symbol-chips" },
    });
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['flex-wrap']} */ ;
    /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
    /** @type {__VLS_StyleScopedClasses['ga-1']} */ ;
    /** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
    /** @type {__VLS_StyleScopedClasses['static-symbol-chips']} */ ;
    const __VLS_132 = __VLS_tryAsConstant((scanStaticSymbols.value));
    for (const [symbol] of __VLS_vFor(__VLS_nonNull(__VLS_132))) {
        let __VLS_133;
        /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
        vChip;
        // @ts-ignore
        const __VLS_134 = __VLS_asFunctionalComponent1(__VLS_133, new __VLS_133({
            // @ts-ignore
            ...{ 'onClick:close': {} }, key: (symbol), size: "small", variant: "tonal", closable: true,
        }));
        const __VLS_135 = __VLS_134({
            ...{ 'onClick:close': {} },
            key: (symbol),
            size: "small",
            variant: "tonal",
            closable: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_134));
        let __VLS_138;
        const __VLS_139 = {
            /** @type {typeof __VLS_138.'click:close'} */
            'onClick:close': (...[$event]) => {
                void $event;
                return (__VLS_unwrap(removeStaticSymbol, {})(symbol));
                // @ts-ignore
                [scanStaticSymbols, scanStaticSymbols, removeStaticSymbol,];
            },
        };
        void __VLS_139;
        var __VLS_136;
        var __VLS_137;
        const { default: __VLS_140 } = __VLS_nonNull(__VLS_136.slots);
        (symbol);
        // @ts-ignore
        [];
        // @ts-ignore
        [];
    }
    if (scanStaticSymbols.value.length === 0) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
            ...{ class: "text-caption text-grey" },
        });
        /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
    }
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "d-flex ga-2" },
    });
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['ga-2']} */ ;
    let __VLS_141;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_142 = __VLS_asFunctionalComponent1(__VLS_141, new __VLS_141({
        // @ts-ignore
        ...{ 'onKeydown': {} }, modelValue: (staticSymbolInput.value), density: "compact", variant: "outlined", hideDetails: true, placeholder: "输入币种（如 SOL），回车添加",
    }));
    const __VLS_143 = __VLS_142({
        ...{ 'onKeydown': {} },
        modelValue: (staticSymbolInput.value),
        density: "compact",
        variant: "outlined",
        hideDetails: true,
        placeholder: "输入币种（如 SOL），回车添加",
    }, ...__VLS_functionalComponentArgsRest(__VLS_142));
    let __VLS_146;
    const __VLS_147 = {
        /** @type {typeof __VLS_146.keydown} */
        onKeydown: (__VLS_unwrap(addStaticSymbol, {})),
    };
    void __VLS_147;
    var __VLS_144;
    var __VLS_145;
    let __VLS_148;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_149 = __VLS_asFunctionalComponent1(__VLS_148, new __VLS_148({
        // @ts-ignore
        ...{ 'onClick': {} }, color: "primary", variant: "tonal", height: "40", disabled: (!staticSymbolInput.value.trim()),
    }));
    const __VLS_150 = __VLS_149({
        ...{ 'onClick': {} },
        color: "primary",
        variant: "tonal",
        height: "40",
        disabled: (!staticSymbolInput.value.trim()),
    }, ...__VLS_functionalComponentArgsRest(__VLS_149));
    let __VLS_153;
    const __VLS_154 = {
        /** @type {typeof __VLS_153.click} */
        onClick: (__VLS_unwrap(addStaticSymbol, {})),
    };
    void __VLS_154;
    var __VLS_151;
    var __VLS_152;
    const { default: __VLS_155 } = __VLS_nonNull(__VLS_151.slots);
    // @ts-ignore
    [scanStaticSymbols, staticSymbolInput, staticSymbolInput, addStaticSymbol, addStaticSymbol,];
    // @ts-ignore
    [];
    let __VLS_156;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_157 = __VLS_asFunctionalComponent1(__VLS_156, new __VLS_156({
        // @ts-ignore
        cols: "12", sm: "6", md: "2",
    }));
    const __VLS_158 = __VLS_157({
        cols: "12",
        sm: "6",
        md: "2",
    }, ...__VLS_functionalComponentArgsRest(__VLS_157));
    var __VLS_159;
    const { default: __VLS_161 } = __VLS_nonNull(__VLS_159.slots);
    let __VLS_162;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_163 = __VLS_asFunctionalComponent1(__VLS_162, new __VLS_162({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (__VLS_unwrap(scopeTopN, {})), modelModifiers: { number: true, }, label: "Top N 补足", type: "number", min: "1", max: "500", density: "compact", variant: "outlined", hideDetails: true, hint: "按成交额排名补足", persistentHint: true,
    }));
    const __VLS_164 = __VLS_163({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (__VLS_unwrap(scopeTopN, {})),
        modelModifiers: { number: true, },
        label: "Top N 补足",
        type: "number",
        min: "1",
        max: "500",
        density: "compact",
        variant: "outlined",
        hideDetails: true,
        hint: "按成交额排名补足",
        persistentHint: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_163));
    let __VLS_167;
    const __VLS_168 = {
        /** @type {typeof __VLS_167.'update:modelValue'} */
        'onUpdate:modelValue': (...[$event]) => {
            void $event;
            return (scopeDirty.value = true);
            // @ts-ignore
            [scopeTopN, scopeDirty,];
        },
    };
    void __VLS_168;
    var __VLS_165;
    var __VLS_166;
    // @ts-ignore
    [];
    let __VLS_169;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_170 = __VLS_asFunctionalComponent1(__VLS_169, new __VLS_169({
        // @ts-ignore
        cols: "12", sm: "6", md: "3",
    }));
    const __VLS_171 = __VLS_170({
        cols: "12",
        sm: "6",
        md: "3",
    }, ...__VLS_functionalComponentArgsRest(__VLS_170));
    var __VLS_172;
    const { default: __VLS_174 } = __VLS_nonNull(__VLS_172.slots);
    const __VLS_175 = SmartSelect || SmartSelect;
    // @ts-ignore
    const __VLS_176 = __VLS_asFunctionalComponent1(__VLS_175, new __VLS_175({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (__VLS_unwrap(scopeTimeframes, {})), items: (__VLS_unwrap(timeframeOptions, {})), label: "扫描周期", multiple: true,
    }));
    const __VLS_177 = __VLS_176({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (__VLS_unwrap(scopeTimeframes, {})),
        items: (__VLS_unwrap(timeframeOptions, {})),
        label: "扫描周期",
        multiple: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_176));
    let __VLS_180;
    const __VLS_181 = {
        /** @type {typeof __VLS_180.'update:modelValue'} */
        'onUpdate:modelValue': (...[$event]) => {
            void $event;
            return (scopeDirty.value = true);
            // @ts-ignore
            [scopeDirty, scopeTimeframes, timeframeOptions,];
        },
    };
    void __VLS_181;
    var __VLS_178;
    var __VLS_179;
    // @ts-ignore
    [];
    let __VLS_182;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_183 = __VLS_asFunctionalComponent1(__VLS_182, new __VLS_182({
        // @ts-ignore
        cols: "12", md: "2", ...{ class: "d-flex justify-end align-center" },
    }));
    const __VLS_184 = __VLS_183({
        cols: "12",
        md: "2",
        ...{ class: "d-flex justify-end align-center" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_183));
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['justify-end']} */ ;
    /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
    var __VLS_185;
    const { default: __VLS_187 } = __VLS_nonNull(__VLS_185.slots);
    let __VLS_188;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_189 = __VLS_asFunctionalComponent1(__VLS_188, new __VLS_188({
        // @ts-ignore
        ...{ 'onClick': {} }, color: "primary", variant: "tonal", prependIcon: "mdi-content-save", loading: (__VLS_unwrap(savingScope, {})), disabled: (!scopeValid.value || __VLS_unwrap(savingScope, {})),
    }));
    const __VLS_190 = __VLS_189({
        ...{ 'onClick': {} },
        color: "primary",
        variant: "tonal",
        prependIcon: "mdi-content-save",
        loading: (__VLS_unwrap(savingScope, {})),
        disabled: (!scopeValid.value || __VLS_unwrap(savingScope, {})),
    }, ...__VLS_functionalComponentArgsRest(__VLS_189));
    let __VLS_193;
    const __VLS_194 = {
        /** @type {typeof __VLS_193.click} */
        onClick: (__VLS_unwrap(saveScanScope, {})),
    };
    void __VLS_194;
    var __VLS_191;
    var __VLS_192;
    const { default: __VLS_195 } = __VLS_nonNull(__VLS_191.slots);
    // @ts-ignore
    [savingScope, savingScope, scopeValid, saveScanScope,];
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    const __VLS_196 = PageCard || PageCard;
    // @ts-ignore
    const __VLS_197 = __VLS_asFunctionalComponent1(__VLS_196, new __VLS_196({
        // @ts-ignore
        icon: "mdi-bell-ring-outline", title: "推送与开仓", spaced: true,
    }));
    const __VLS_198 = __VLS_197({
        icon: "mdi-bell-ring-outline",
        title: "推送与开仓",
        spaced: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_197));
    var __VLS_199;
    const { default: __VLS_201 } = __VLS_nonNull(__VLS_199.slots);
    {
        const { badges: __VLS_202 } = __VLS_nonNull(__VLS_199.slots);
        let __VLS_203;
        /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
        vChip;
        // @ts-ignore
        const __VLS_204 = __VLS_asFunctionalComponent1(__VLS_203, new __VLS_203({
            // @ts-ignore
            size: "small", variant: "tonal", color: (autoTradeEnabled.value ? 'success' : 'grey'),
        }));
        const __VLS_205 = __VLS_204({
            size: "small",
            variant: "tonal",
            color: (autoTradeEnabled.value ? 'success' : 'grey'),
        }, ...__VLS_functionalComponentArgsRest(__VLS_204));
        var __VLS_206;
        const { default: __VLS_208 } = __VLS_nonNull(__VLS_206.slots);
        (autoTradeEnabled.value ? '自动开仓已启用' : '自动开仓已停用');
        // @ts-ignore
        [autoTradeEnabled, autoTradeEnabled,];
        // @ts-ignore
        [];
    }
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "d-flex align-center flex-wrap ga-2 mb-3" },
    });
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
    /** @type {__VLS_StyleScopedClasses['flex-wrap']} */ ;
    /** @type {__VLS_StyleScopedClasses['ga-2']} */ ;
    /** @type {__VLS_StyleScopedClasses['mb-3']} */ ;
    let __VLS_209;
    /** @ts-ignore @type { | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon'] | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon']} */
    vIcon;
    // @ts-ignore
    const __VLS_210 = __VLS_asFunctionalComponent1(__VLS_209, new __VLS_209({
        // @ts-ignore
        size: "18", color: "primary",
    }));
    const __VLS_211 = __VLS_210({
        size: "18",
        color: "primary",
    }, ...__VLS_functionalComponentArgsRest(__VLS_210));
    var __VLS_212;
    const { default: __VLS_214 } = __VLS_nonNull(__VLS_212.slots);
    // @ts-ignore
    [];
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
        ...{ class: "text-subtitle-1 font-weight-medium" },
    });
    /** @type {__VLS_StyleScopedClasses['text-subtitle-1']} */ ;
    /** @type {__VLS_StyleScopedClasses['font-weight-medium']} */ ;
    let __VLS_215;
    /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
    vChip;
    // @ts-ignore
    const __VLS_216 = __VLS_asFunctionalComponent1(__VLS_215, new __VLS_215({
        // @ts-ignore
        size: "x-small", variant: "tonal", color: (pushStatus.value.dingtalk_configured ? 'success' : 'warning'),
    }));
    const __VLS_217 = __VLS_216({
        size: "x-small",
        variant: "tonal",
        color: (pushStatus.value.dingtalk_configured ? 'success' : 'warning'),
    }, ...__VLS_functionalComponentArgsRest(__VLS_216));
    var __VLS_218;
    const { default: __VLS_220 } = __VLS_nonNull(__VLS_218.slots);
    (pushStatus.value.dingtalk_configured ? 'Webhook 已配置' : '未配置 DINGTALK_WEBHOOK_URL');
    // @ts-ignore
    [pushStatus, pushStatus,];
    let __VLS_221;
    /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
    vRow;
    // @ts-ignore
    const __VLS_222 = __VLS_asFunctionalComponent1(__VLS_221, new __VLS_221({
        // @ts-ignore
        dense: true, align: "center",
    }));
    const __VLS_223 = __VLS_222({
        dense: true,
        align: "center",
    }, ...__VLS_functionalComponentArgsRest(__VLS_222));
    var __VLS_224;
    const { default: __VLS_226 } = __VLS_nonNull(__VLS_224.slots);
    let __VLS_227;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_228 = __VLS_asFunctionalComponent1(__VLS_227, new __VLS_227({
        // @ts-ignore
        cols: "12", sm: "6", md: "3",
    }));
    const __VLS_229 = __VLS_228({
        cols: "12",
        sm: "6",
        md: "3",
    }, ...__VLS_functionalComponentArgsRest(__VLS_228));
    var __VLS_230;
    const { default: __VLS_232 } = __VLS_nonNull(__VLS_230.slots);
    let __VLS_233;
    /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch'] | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
    vSwitch;
    // @ts-ignore
    const __VLS_234 = __VLS_asFunctionalComponent1(__VLS_233, new __VLS_233({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (pushStatus.value.signal_dingtalk_enabled), loading: (__VLS_unwrap(savingDingtalkPush, {})), disabled: (!pushStatus.value.dingtalk_configured || !pushStatus.value.dingtalk_enabled), label: "币种信号推送", color: "primary", inset: true, hideDetails: true,
    }));
    const __VLS_235 = __VLS_234({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (pushStatus.value.signal_dingtalk_enabled),
        loading: (__VLS_unwrap(savingDingtalkPush, {})),
        disabled: (!pushStatus.value.dingtalk_configured || !pushStatus.value.dingtalk_enabled),
        label: "币种信号推送",
        color: "primary",
        inset: true,
        hideDetails: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_234));
    let __VLS_238;
    const __VLS_239 = {
        /** @type {typeof __VLS_238.'update:modelValue'} */
        'onUpdate:modelValue': (__VLS_unwrap(onToggleDingtalkPush, {})),
    };
    void __VLS_239;
    var __VLS_236;
    var __VLS_237;
    // @ts-ignore
    [pushStatus, pushStatus, pushStatus, savingDingtalkPush, onToggleDingtalkPush,];
    let __VLS_240;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_241 = __VLS_asFunctionalComponent1(__VLS_240, new __VLS_240({
        // @ts-ignore
        cols: "12", sm: "6", md: "3",
    }));
    const __VLS_242 = __VLS_241({
        cols: "12",
        sm: "6",
        md: "3",
    }, ...__VLS_functionalComponentArgsRest(__VLS_241));
    var __VLS_243;
    const { default: __VLS_245 } = __VLS_nonNull(__VLS_243.slots);
    let __VLS_246;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_247 = __VLS_asFunctionalComponent1(__VLS_246, new __VLS_246({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (__VLS_unwrap(pushVolumeInput, {})), modelModifiers: { number: true, }, label: "非静态币推送量能倍数", type: "number", min: "0", max: "100", step: "0.5", hint: "当前量/动态基准 ≥ 该倍数才推送；0 = 不过滤", persistentHint: true,
    }));
    const __VLS_248 = __VLS_247({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (__VLS_unwrap(pushVolumeInput, {})),
        modelModifiers: { number: true, },
        label: "非静态币推送量能倍数",
        type: "number",
        min: "0",
        max: "100",
        step: "0.5",
        hint: "当前量/动态基准 ≥ 该倍数才推送；0 = 不过滤",
        persistentHint: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_247));
    let __VLS_251;
    const __VLS_252 = {
        /** @type {typeof __VLS_251.'update:modelValue'} */
        'onUpdate:modelValue': (...[$event]) => {
            void $event;
            return (pushVolumeDirty.value = true);
            // @ts-ignore
            [pushVolumeInput, pushVolumeDirty,];
        },
    };
    void __VLS_252;
    var __VLS_249;
    var __VLS_250;
    // @ts-ignore
    [];
    let __VLS_253;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_254 = __VLS_asFunctionalComponent1(__VLS_253, new __VLS_253({
        // @ts-ignore
        cols: "12", sm: "6", md: "2", ...{ class: "d-flex justify-end" },
    }));
    const __VLS_255 = __VLS_254({
        cols: "12",
        sm: "6",
        md: "2",
        ...{ class: "d-flex justify-end" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_254));
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['justify-end']} */ ;
    var __VLS_256;
    const { default: __VLS_258 } = __VLS_nonNull(__VLS_256.slots);
    let __VLS_259;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_260 = __VLS_asFunctionalComponent1(__VLS_259, new __VLS_259({
        // @ts-ignore
        ...{ 'onClick': {} }, color: "primary", variant: "tonal", prependIcon: "mdi-content-save", loading: (__VLS_unwrap(savingPushConfig, {})),
    }));
    const __VLS_261 = __VLS_260({
        ...{ 'onClick': {} },
        color: "primary",
        variant: "tonal",
        prependIcon: "mdi-content-save",
        loading: (__VLS_unwrap(savingPushConfig, {})),
    }, ...__VLS_functionalComponentArgsRest(__VLS_260));
    let __VLS_264;
    const __VLS_265 = {
        /** @type {typeof __VLS_264.click} */
        onClick: (__VLS_unwrap(savePushVolume, {})),
    };
    void __VLS_265;
    var __VLS_262;
    var __VLS_263;
    const { default: __VLS_266 } = __VLS_nonNull(__VLS_262.slots);
    // @ts-ignore
    [savingPushConfig, savePushVolume,];
    // @ts-ignore
    [];
    let __VLS_267;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_268 = __VLS_asFunctionalComponent1(__VLS_267, new __VLS_267({
        // @ts-ignore
        cols: "12", md: "4",
    }));
    const __VLS_269 = __VLS_268({
        cols: "12",
        md: "4",
    }, ...__VLS_functionalComponentArgsRest(__VLS_268));
    var __VLS_270;
    const { default: __VLS_272 } = __VLS_nonNull(__VLS_270.slots);
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "text-caption text-grey" },
    });
    /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
    (pushStatus.value.static_symbols.join(' / ') || '无');
    // @ts-ignore
    [pushStatus,];
    // @ts-ignore
    [];
    let __VLS_273;
    /** @ts-ignore @type { | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider'] | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider']} */
    vDivider;
    // @ts-ignore
    const __VLS_274 = __VLS_asFunctionalComponent1(__VLS_273, new __VLS_273({
        // @ts-ignore
        ...{ class: "my-4" },
    }));
    const __VLS_275 = __VLS_274({
        ...{ class: "my-4" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_274));
    /** @type {__VLS_StyleScopedClasses['my-4']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "d-flex align-center flex-wrap ga-2 mb-3" },
    });
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
    /** @type {__VLS_StyleScopedClasses['flex-wrap']} */ ;
    /** @type {__VLS_StyleScopedClasses['ga-2']} */ ;
    /** @type {__VLS_StyleScopedClasses['mb-3']} */ ;
    let __VLS_278;
    /** @ts-ignore @type { | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon'] | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon']} */
    vIcon;
    // @ts-ignore
    const __VLS_279 = __VLS_asFunctionalComponent1(__VLS_278, new __VLS_278({
        // @ts-ignore
        size: "18", color: "primary",
    }));
    const __VLS_280 = __VLS_279({
        size: "18",
        color: "primary",
    }, ...__VLS_functionalComponentArgsRest(__VLS_279));
    var __VLS_281;
    const { default: __VLS_283 } = __VLS_nonNull(__VLS_281.slots);
    // @ts-ignore
    [];
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
        ...{ class: "text-subtitle-1 font-weight-medium" },
    });
    /** @type {__VLS_StyleScopedClasses['text-subtitle-1']} */ ;
    /** @type {__VLS_StyleScopedClasses['font-weight-medium']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
        ...{ class: "text-caption text-grey" },
    });
    /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
    (__VLS_unwrap(lastAutoOpenText, {}));
    let __VLS_284;
    /** @ts-ignore @type { | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert'] | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert']} */
    vAlert;
    // @ts-ignore
    const __VLS_285 = __VLS_asFunctionalComponent1(__VLS_284, new __VLS_284({
        // @ts-ignore
        type: "warning", variant: "tonal", density: "compact", ...{ class: "mb-4 text-caption" },
    }));
    const __VLS_286 = __VLS_285({
        type: "warning",
        variant: "tonal",
        density: "compact",
        ...{ class: "mb-4 text-caption" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_285));
    /** @type {__VLS_StyleScopedClasses['mb-4']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
    var __VLS_287;
    const { default: __VLS_289 } = __VLS_nonNull(__VLS_287.slots);
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
    // @ts-ignore
    [lastAutoOpenText,];
    let __VLS_290;
    /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
    vRow;
    // @ts-ignore
    const __VLS_291 = __VLS_asFunctionalComponent1(__VLS_290, new __VLS_290({
        // @ts-ignore
        dense: true, align: "center", ...{ class: "mb-1" },
    }));
    const __VLS_292 = __VLS_291({
        dense: true,
        align: "center",
        ...{ class: "mb-1" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_291));
    /** @type {__VLS_StyleScopedClasses['mb-1']} */ ;
    var __VLS_293;
    const { default: __VLS_295 } = __VLS_nonNull(__VLS_293.slots);
    let __VLS_296;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_297 = __VLS_asFunctionalComponent1(__VLS_296, new __VLS_296({
        // @ts-ignore
        cols: "12", sm: "6", md: "3",
    }));
    const __VLS_298 = __VLS_297({
        cols: "12",
        sm: "6",
        md: "3",
    }, ...__VLS_functionalComponentArgsRest(__VLS_297));
    var __VLS_299;
    const { default: __VLS_301 } = __VLS_nonNull(__VLS_299.slots);
    let __VLS_302;
    /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch'] | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
    vSwitch;
    // @ts-ignore
    const __VLS_303 = __VLS_asFunctionalComponent1(__VLS_302, new __VLS_302({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (autoTradeEnabled.value), loading: (__VLS_unwrap(savingAutoTrade, {})), label: "启用自动开仓", color: "primary", inset: true, hideDetails: true,
    }));
    const __VLS_304 = __VLS_303({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (autoTradeEnabled.value),
        loading: (__VLS_unwrap(savingAutoTrade, {})),
        label: "启用自动开仓",
        color: "primary",
        inset: true,
        hideDetails: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_303));
    let __VLS_307;
    const __VLS_308 = {
        /** @type {typeof __VLS_307.'update:modelValue'} */
        'onUpdate:modelValue': (__VLS_unwrap(onToggleAutoTrade, {})),
    };
    void __VLS_308;
    var __VLS_305;
    var __VLS_306;
    // @ts-ignore
    [autoTradeEnabled, savingAutoTrade, onToggleAutoTrade,];
    // @ts-ignore
    [];
    let __VLS_309;
    /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
    vRow;
    // @ts-ignore
    const __VLS_310 = __VLS_asFunctionalComponent1(__VLS_309, new __VLS_309({
        // @ts-ignore
        dense: true,
    }));
    const __VLS_311 = __VLS_310({
        dense: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_310));
    var __VLS_312;
    const { default: __VLS_314 } = __VLS_nonNull(__VLS_312.slots);
    let __VLS_315;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_316 = __VLS_asFunctionalComponent1(__VLS_315, new __VLS_315({
        // @ts-ignore
        cols: "12", md: "6",
    }));
    const __VLS_317 = __VLS_316({
        cols: "12",
        md: "6",
    }, ...__VLS_functionalComponentArgsRest(__VLS_316));
    var __VLS_318;
    const { default: __VLS_320 } = __VLS_nonNull(__VLS_318.slots);
    const __VLS_321 = SmartSelect || SmartSelect;
    // @ts-ignore
    const __VLS_322 = __VLS_asFunctionalComponent1(__VLS_321, new __VLS_321({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (autoForm.value.directions), items: (__VLS_unwrap(directionOptions, {})), itemTitle: "title", itemValue: "value", label: "允许方向", multiple: true,
    }));
    const __VLS_323 = __VLS_322({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (autoForm.value.directions),
        items: (__VLS_unwrap(directionOptions, {})),
        itemTitle: "title",
        itemValue: "value",
        label: "允许方向",
        multiple: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_322));
    let __VLS_326;
    const __VLS_327 = {
        /** @type {typeof __VLS_326.'update:modelValue'} */
        'onUpdate:modelValue': (__VLS_unwrap(markAutoFormDirty, {})),
    };
    void __VLS_327;
    var __VLS_324;
    var __VLS_325;
    // @ts-ignore
    [autoForm, directionOptions, markAutoFormDirty,];
    let __VLS_328;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_329 = __VLS_asFunctionalComponent1(__VLS_328, new __VLS_328({
        // @ts-ignore
        cols: "12", md: "6",
    }));
    const __VLS_330 = __VLS_329({
        cols: "12",
        md: "6",
    }, ...__VLS_functionalComponentArgsRest(__VLS_329));
    var __VLS_331;
    const { default: __VLS_333 } = __VLS_nonNull(__VLS_331.slots);
    const __VLS_334 = SmartSelect || SmartSelect;
    // @ts-ignore
    const __VLS_335 = __VLS_asFunctionalComponent1(__VLS_334, new __VLS_334({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (autoForm.value.timeframes), items: (__VLS_unwrap(timeframeOptions, {})), label: "允许周期", multiple: true,
    }));
    const __VLS_336 = __VLS_335({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (autoForm.value.timeframes),
        items: (__VLS_unwrap(timeframeOptions, {})),
        label: "允许周期",
        multiple: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_335));
    let __VLS_339;
    const __VLS_340 = {
        /** @type {typeof __VLS_339.'update:modelValue'} */
        'onUpdate:modelValue': (__VLS_unwrap(markAutoFormDirty, {})),
    };
    void __VLS_340;
    var __VLS_337;
    var __VLS_338;
    // @ts-ignore
    [timeframeOptions, autoForm, markAutoFormDirty,];
    let __VLS_341;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_342 = __VLS_asFunctionalComponent1(__VLS_341, new __VLS_341({
        // @ts-ignore
        cols: "12",
    }));
    const __VLS_343 = __VLS_342({
        cols: "12",
    }, ...__VLS_functionalComponentArgsRest(__VLS_342));
    var __VLS_344;
    const { default: __VLS_346 } = __VLS_nonNull(__VLS_344.slots);
    const __VLS_347 = SmartSelect || SmartSelect;
    // @ts-ignore
    const __VLS_348 = __VLS_asFunctionalComponent1(__VLS_347, new __VLS_347({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (autoForm.value.strategies), items: (__VLS_unwrap(strategyOptions, {})), itemTitle: "title", itemValue: "value", label: "策略白名单（观望类策略不会自动开仓）", multiple: true,
    }));
    const __VLS_349 = __VLS_348({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (autoForm.value.strategies),
        items: (__VLS_unwrap(strategyOptions, {})),
        itemTitle: "title",
        itemValue: "value",
        label: "策略白名单（观望类策略不会自动开仓）",
        multiple: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_348));
    let __VLS_352;
    const __VLS_353 = {
        /** @type {typeof __VLS_352.'update:modelValue'} */
        'onUpdate:modelValue': (__VLS_unwrap(markAutoFormDirty, {})),
    };
    void __VLS_353;
    var __VLS_350;
    var __VLS_351;
    // @ts-ignore
    [autoForm, markAutoFormDirty, strategyOptions,];
    // @ts-ignore
    [];
    let __VLS_354;
    /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
    vRow;
    // @ts-ignore
    const __VLS_355 = __VLS_asFunctionalComponent1(__VLS_354, new __VLS_354({
        // @ts-ignore
        dense: true, ...{ class: "mt-1" },
    }));
    const __VLS_356 = __VLS_355({
        dense: true,
        ...{ class: "mt-1" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_355));
    /** @type {__VLS_StyleScopedClasses['mt-1']} */ ;
    var __VLS_357;
    const { default: __VLS_359 } = __VLS_nonNull(__VLS_357.slots);
    let __VLS_360;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_361 = __VLS_asFunctionalComponent1(__VLS_360, new __VLS_360({
        // @ts-ignore
        cols: "12", sm: "6", md: "4",
    }));
    const __VLS_362 = __VLS_361({
        cols: "12",
        sm: "6",
        md: "4",
    }, ...__VLS_functionalComponentArgsRest(__VLS_361));
    var __VLS_363;
    const { default: __VLS_365 } = __VLS_nonNull(__VLS_363.slots);
    let __VLS_366;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_367 = __VLS_asFunctionalComponent1(__VLS_366, new __VLS_366({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (autoForm.value.confirmations), modelModifiers: { number: true, }, label: "确认数", type: "number", min: "1", density: "compact", variant: "outlined", hideDetails: true, hint: "同方向不同信号族数达到该值才开仓", persistentHint: true,
    }));
    const __VLS_368 = __VLS_367({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (autoForm.value.confirmations),
        modelModifiers: { number: true, },
        label: "确认数",
        type: "number",
        min: "1",
        density: "compact",
        variant: "outlined",
        hideDetails: true,
        hint: "同方向不同信号族数达到该值才开仓",
        persistentHint: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_367));
    let __VLS_371;
    const __VLS_372 = {
        /** @type {typeof __VLS_371.'update:modelValue'} */
        'onUpdate:modelValue': (__VLS_unwrap(markAutoFormDirty, {})),
    };
    void __VLS_372;
    var __VLS_369;
    var __VLS_370;
    // @ts-ignore
    [autoForm, markAutoFormDirty,];
    let __VLS_373;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_374 = __VLS_asFunctionalComponent1(__VLS_373, new __VLS_373({
        // @ts-ignore
        cols: "12", sm: "6", md: "4",
    }));
    const __VLS_375 = __VLS_374({
        cols: "12",
        sm: "6",
        md: "4",
    }, ...__VLS_functionalComponentArgsRest(__VLS_374));
    var __VLS_376;
    const { default: __VLS_378 } = __VLS_nonNull(__VLS_376.slots);
    let __VLS_379;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_380 = __VLS_asFunctionalComponent1(__VLS_379, new __VLS_379({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (autoForm.value.confirmationWindowSeconds), modelModifiers: { number: true, }, label: "确认窗口 (秒)", type: "number", min: "1", density: "compact", variant: "outlined", hideDetails: true, hint: "统计确认数的回溯窗口", persistentHint: true,
    }));
    const __VLS_381 = __VLS_380({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (autoForm.value.confirmationWindowSeconds),
        modelModifiers: { number: true, },
        label: "确认窗口 (秒)",
        type: "number",
        min: "1",
        density: "compact",
        variant: "outlined",
        hideDetails: true,
        hint: "统计确认数的回溯窗口",
        persistentHint: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_380));
    let __VLS_384;
    const __VLS_385 = {
        /** @type {typeof __VLS_384.'update:modelValue'} */
        'onUpdate:modelValue': (__VLS_unwrap(markAutoFormDirty, {})),
    };
    void __VLS_385;
    var __VLS_382;
    var __VLS_383;
    // @ts-ignore
    [autoForm, markAutoFormDirty,];
    let __VLS_386;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_387 = __VLS_asFunctionalComponent1(__VLS_386, new __VLS_386({
        // @ts-ignore
        cols: "12", sm: "6", md: "4",
    }));
    const __VLS_388 = __VLS_387({
        cols: "12",
        sm: "6",
        md: "4",
    }, ...__VLS_functionalComponentArgsRest(__VLS_387));
    var __VLS_389;
    const { default: __VLS_391 } = __VLS_nonNull(__VLS_389.slots);
    let __VLS_392;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_393 = __VLS_asFunctionalComponent1(__VLS_392, new __VLS_392({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (autoForm.value.cooldownSeconds), modelModifiers: { number: true, }, label: "冷却时间 (秒)", type: "number", min: "0", density: "compact", variant: "outlined", hideDetails: true, hint: "同币种自动开仓最小间隔", persistentHint: true,
    }));
    const __VLS_394 = __VLS_393({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (autoForm.value.cooldownSeconds),
        modelModifiers: { number: true, },
        label: "冷却时间 (秒)",
        type: "number",
        min: "0",
        density: "compact",
        variant: "outlined",
        hideDetails: true,
        hint: "同币种自动开仓最小间隔",
        persistentHint: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_393));
    let __VLS_397;
    const __VLS_398 = {
        /** @type {typeof __VLS_397.'update:modelValue'} */
        'onUpdate:modelValue': (__VLS_unwrap(markAutoFormDirty, {})),
    };
    void __VLS_398;
    var __VLS_395;
    var __VLS_396;
    // @ts-ignore
    [autoForm, markAutoFormDirty,];
    let __VLS_399;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_400 = __VLS_asFunctionalComponent1(__VLS_399, new __VLS_399({
        // @ts-ignore
        cols: "12", sm: "6", md: "4",
    }));
    const __VLS_401 = __VLS_400({
        cols: "12",
        sm: "6",
        md: "4",
    }, ...__VLS_functionalComponentArgsRest(__VLS_400));
    var __VLS_402;
    const { default: __VLS_404 } = __VLS_nonNull(__VLS_402.slots);
    let __VLS_405;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_406 = __VLS_asFunctionalComponent1(__VLS_405, new __VLS_405({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (autoForm.value.valueUsd), modelModifiers: { number: true, }, label: "单笔金额 (USD)", type: "number", min: "1", density: "compact", variant: "outlined", hideDetails: true, hint: "每次自动开仓的目标名义价值", persistentHint: true,
    }));
    const __VLS_407 = __VLS_406({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (autoForm.value.valueUsd),
        modelModifiers: { number: true, },
        label: "单笔金额 (USD)",
        type: "number",
        min: "1",
        density: "compact",
        variant: "outlined",
        hideDetails: true,
        hint: "每次自动开仓的目标名义价值",
        persistentHint: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_406));
    let __VLS_410;
    const __VLS_411 = {
        /** @type {typeof __VLS_410.'update:modelValue'} */
        'onUpdate:modelValue': (__VLS_unwrap(markAutoFormDirty, {})),
    };
    void __VLS_411;
    var __VLS_408;
    var __VLS_409;
    // @ts-ignore
    [autoForm, markAutoFormDirty,];
    let __VLS_412;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_413 = __VLS_asFunctionalComponent1(__VLS_412, new __VLS_412({
        // @ts-ignore
        cols: "12", sm: "6", md: "4",
    }));
    const __VLS_414 = __VLS_413({
        cols: "12",
        sm: "6",
        md: "4",
    }, ...__VLS_functionalComponentArgsRest(__VLS_413));
    var __VLS_415;
    const { default: __VLS_417 } = __VLS_nonNull(__VLS_415.slots);
    let __VLS_418;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_419 = __VLS_asFunctionalComponent1(__VLS_418, new __VLS_418({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (autoForm.value.maxPositions), modelModifiers: { number: true, }, label: "最大持仓数", type: "number", min: "1", density: "compact", variant: "outlined", hideDetails: true, hint: "当前持仓达到该值后不再自动开仓", persistentHint: true,
    }));
    const __VLS_420 = __VLS_419({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (autoForm.value.maxPositions),
        modelModifiers: { number: true, },
        label: "最大持仓数",
        type: "number",
        min: "1",
        density: "compact",
        variant: "outlined",
        hideDetails: true,
        hint: "当前持仓达到该值后不再自动开仓",
        persistentHint: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_419));
    let __VLS_423;
    const __VLS_424 = {
        /** @type {typeof __VLS_423.'update:modelValue'} */
        'onUpdate:modelValue': (__VLS_unwrap(markAutoFormDirty, {})),
    };
    void __VLS_424;
    var __VLS_421;
    var __VLS_422;
    // @ts-ignore
    [autoForm, markAutoFormDirty,];
    // @ts-ignore
    [];
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "d-flex align-center mt-4" },
    });
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
    /** @type {__VLS_StyleScopedClasses['mt-4']} */ ;
    if (!autoFormValid.value) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
            ...{ class: "text-caption text-error" },
        });
        /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-error']} */ ;
    }
    let __VLS_425;
    /** @ts-ignore @type { | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer'] | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer']} */
    vSpacer;
    // @ts-ignore
    const __VLS_426 = __VLS_asFunctionalComponent1(__VLS_425, new __VLS_425({
    // @ts-ignore
    }));
    const __VLS_427 = __VLS_426({}, ...__VLS_functionalComponentArgsRest(__VLS_426));
    let __VLS_430;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_431 = __VLS_asFunctionalComponent1(__VLS_430, new __VLS_430({
        // @ts-ignore
        ...{ 'onClick': {} }, color: "primary", variant: "tonal", prependIcon: "mdi-content-save", loading: (__VLS_unwrap(savingAuto, {})), disabled: (!autoFormValid.value || __VLS_unwrap(savingAuto, {})),
    }));
    const __VLS_432 = __VLS_431({
        ...{ 'onClick': {} },
        color: "primary",
        variant: "tonal",
        prependIcon: "mdi-content-save",
        loading: (__VLS_unwrap(savingAuto, {})),
        disabled: (!autoFormValid.value || __VLS_unwrap(savingAuto, {})),
    }, ...__VLS_functionalComponentArgsRest(__VLS_431));
    let __VLS_435;
    const __VLS_436 = {
        /** @type {typeof __VLS_435.click} */
        onClick: (__VLS_unwrap(saveAutoConfig, {})),
    };
    void __VLS_436;
    var __VLS_433;
    var __VLS_434;
    const { default: __VLS_437 } = __VLS_nonNull(__VLS_433.slots);
    // @ts-ignore
    [autoFormValid, autoFormValid, savingAuto, savingAuto, saveAutoConfig,];
    // @ts-ignore
    [];
    const __VLS_438 = PageCard || PageCard;
    // @ts-ignore
    const __VLS_439 = __VLS_asFunctionalComponent1(__VLS_438, new __VLS_438({
        // @ts-ignore
        icon: "mdi-chart-timeline-variant", title: "出场层（实盘与纸面共用）", spaced: true,
    }));
    const __VLS_440 = __VLS_439({
        icon: "mdi-chart-timeline-variant",
        title: "出场层（实盘与纸面共用）",
        spaced: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_439));
    var __VLS_441;
    const { default: __VLS_443 } = __VLS_nonNull(__VLS_441.slots);
    {
        const { badges: __VLS_444 } = __VLS_nonNull(__VLS_441.slots);
        let __VLS_445;
        /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
        vChip;
        // @ts-ignore
        const __VLS_446 = __VLS_asFunctionalComponent1(__VLS_445, new __VLS_445({
            // @ts-ignore
            size: "small", variant: "tonal", color: (paperEnabled.value ? 'success' : 'grey'),
        }));
        const __VLS_447 = __VLS_446({
            size: "small",
            variant: "tonal",
            color: (paperEnabled.value ? 'success' : 'grey'),
        }, ...__VLS_functionalComponentArgsRest(__VLS_446));
        var __VLS_448;
        const { default: __VLS_450 } = __VLS_nonNull(__VLS_448.slots);
        (paperEnabled.value ? '纸面跟踪中' : '纸面未启用');
        // @ts-ignore
        [paperEnabled, paperEnabled,];
        let __VLS_451;
        /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
        vChip;
        // @ts-ignore
        const __VLS_452 = __VLS_asFunctionalComponent1(__VLS_451, new __VLS_451({
            // @ts-ignore
            size: "small", variant: "tonal", color: (liveTimeoutEnabled.value ? 'warning' : 'grey'),
        }));
        const __VLS_453 = __VLS_452({
            size: "small",
            variant: "tonal",
            color: (liveTimeoutEnabled.value ? 'warning' : 'grey'),
        }, ...__VLS_functionalComponentArgsRest(__VLS_452));
        var __VLS_454;
        const { default: __VLS_456 } = __VLS_nonNull(__VLS_454.slots);
        (liveTimeoutEnabled.value ? '实盘超时平仓' : '实盘不超时');
        // @ts-ignore
        [liveTimeoutEnabled, liveTimeoutEnabled,];
        if (tracking.value.paper_stats.total > 0) {
            let __VLS_457;
            /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
            vChip;
            // @ts-ignore
            const __VLS_458 = __VLS_asFunctionalComponent1(__VLS_457, new __VLS_457({
                // @ts-ignore
                size: "small", variant: "tonal", color: "info",
            }));
            const __VLS_459 = __VLS_458({
                size: "small",
                variant: "tonal",
                color: "info",
            }, ...__VLS_functionalComponentArgsRest(__VLS_458));
            var __VLS_460;
            const { default: __VLS_462 } = __VLS_nonNull(__VLS_460.slots);
            (tracking.value.paper_stats.total);
            (tracking.value.paper_stats.win_rate);
            // @ts-ignore
            [tracking, tracking, tracking,];
        }
        // @ts-ignore
        [];
    }
    let __VLS_463;
    /** @ts-ignore @type { | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert'] | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert']} */
    vAlert;
    // @ts-ignore
    const __VLS_464 = __VLS_asFunctionalComponent1(__VLS_463, new __VLS_463({
        // @ts-ignore
        type: "info", variant: "tonal", density: "compact", ...{ class: "mb-3 text-caption" },
    }));
    const __VLS_465 = __VLS_464({
        type: "info",
        variant: "tonal",
        density: "compact",
        ...{ class: "mb-3 text-caption" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_464));
    /** @type {__VLS_StyleScopedClasses['mb-3']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
    var __VLS_466;
    const { default: __VLS_468 } = __VLS_nonNull(__VLS_466.slots);
    __VLS_asFunctionalElement1(__VLS_intrinsics.code, __VLS_intrinsics.code)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.b, __VLS_intrinsics.b)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.b, __VLS_intrinsics.b)({});
    // @ts-ignore
    [];
    let __VLS_469;
    /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
    vRow;
    // @ts-ignore
    const __VLS_470 = __VLS_asFunctionalComponent1(__VLS_469, new __VLS_469({
        // @ts-ignore
        dense: true, align: "center", ...{ class: "mb-2" },
    }));
    const __VLS_471 = __VLS_470({
        dense: true,
        align: "center",
        ...{ class: "mb-2" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_470));
    /** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
    var __VLS_472;
    const { default: __VLS_474 } = __VLS_nonNull(__VLS_472.slots);
    let __VLS_475;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_476 = __VLS_asFunctionalComponent1(__VLS_475, new __VLS_475({
        // @ts-ignore
        cols: "12", md: "4",
    }));
    const __VLS_477 = __VLS_476({
        cols: "12",
        md: "4",
    }, ...__VLS_functionalComponentArgsRest(__VLS_476));
    var __VLS_478;
    const { default: __VLS_480 } = __VLS_nonNull(__VLS_478.slots);
    let __VLS_481;
    /** @ts-ignore @type { | typeof __VLS_components.vBtnToggle | typeof __VLS_components.VBtnToggle | typeof __VLS_components['v-btn-toggle'] | typeof __VLS_components.vBtnToggle | typeof __VLS_components.VBtnToggle | typeof __VLS_components['v-btn-toggle']} */
    vBtnToggle;
    // @ts-ignore
    const __VLS_482 = __VLS_asFunctionalComponent1(__VLS_481, new __VLS_481({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (exitMode.value), mandatory: true, divided: true, density: "compact", variant: "outlined",
    }));
    const __VLS_483 = __VLS_482({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (exitMode.value),
        mandatory: true,
        divided: true,
        density: "compact",
        variant: "outlined",
    }, ...__VLS_functionalComponentArgsRest(__VLS_482));
    let __VLS_486;
    const __VLS_487 = {
        /** @type {typeof __VLS_486.'update:modelValue'} */
        'onUpdate:modelValue': (__VLS_unwrap(onChangeExitMode, {})),
    };
    void __VLS_487;
    var __VLS_484;
    var __VLS_485;
    const { default: __VLS_488 } = __VLS_nonNull(__VLS_484.slots);
    let __VLS_489;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_490 = __VLS_asFunctionalComponent1(__VLS_489, new __VLS_489({
        // @ts-ignore
        value: "percent", size: "small",
    }));
    const __VLS_491 = __VLS_490({
        value: "percent",
        size: "small",
    }, ...__VLS_functionalComponentArgsRest(__VLS_490));
    var __VLS_492;
    const { default: __VLS_494 } = __VLS_nonNull(__VLS_492.slots);
    // @ts-ignore
    [exitMode, onChangeExitMode,];
    let __VLS_495;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_496 = __VLS_asFunctionalComponent1(__VLS_495, new __VLS_495({
        // @ts-ignore
        value: "atr", size: "small",
    }));
    const __VLS_497 = __VLS_496({
        value: "atr",
        size: "small",
    }, ...__VLS_functionalComponentArgsRest(__VLS_496));
    var __VLS_498;
    const { default: __VLS_500 } = __VLS_nonNull(__VLS_498.slots);
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    let __VLS_501;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_502 = __VLS_asFunctionalComponent1(__VLS_501, new __VLS_501({
        // @ts-ignore
        cols: "12", md: "8", ...{ class: "text-caption text-grey" },
    }));
    const __VLS_503 = __VLS_502({
        cols: "12",
        md: "8",
        ...{ class: "text-caption text-grey" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_502));
    /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
    var __VLS_504;
    const { default: __VLS_506 } = __VLS_nonNull(__VLS_504.slots);
    (exitMode.value === 'percent'
        ? '价格距离 = 设置页的保证金百分比 ÷ 杠杆；实盘条件单与纸面模拟用的是同一套价格。'
        : '止损 = N × ATR，止盈 = R × 止损距离；实盘条件单也按这个挂（ATR 取下方周期），拿不到 ATR 时回退百分比。');
    // @ts-ignore
    [exitMode,];
    // @ts-ignore
    [];
    let __VLS_507;
    /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
    vRow;
    // @ts-ignore
    const __VLS_508 = __VLS_asFunctionalComponent1(__VLS_507, new __VLS_507({
        // @ts-ignore
        dense: true, align: "center",
    }));
    const __VLS_509 = __VLS_508({
        dense: true,
        align: "center",
    }, ...__VLS_functionalComponentArgsRest(__VLS_508));
    var __VLS_510;
    const { default: __VLS_512 } = __VLS_nonNull(__VLS_510.slots);
    let __VLS_513;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_514 = __VLS_asFunctionalComponent1(__VLS_513, new __VLS_513({
        // @ts-ignore
        cols: "12", sm: "6", md: "3",
    }));
    const __VLS_515 = __VLS_514({
        cols: "12",
        sm: "6",
        md: "3",
    }, ...__VLS_functionalComponentArgsRest(__VLS_514));
    var __VLS_516;
    const { default: __VLS_518 } = __VLS_nonNull(__VLS_516.slots);
    let __VLS_519;
    /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch'] | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
    vSwitch;
    // @ts-ignore
    const __VLS_520 = __VLS_asFunctionalComponent1(__VLS_519, new __VLS_519({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (paperEnabled.value), loading: (__VLS_unwrap(savingPaperToggle, {})), label: "启用纸面跟踪", color: "primary", inset: true, hideDetails: true,
    }));
    const __VLS_521 = __VLS_520({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (paperEnabled.value),
        loading: (__VLS_unwrap(savingPaperToggle, {})),
        label: "启用纸面跟踪",
        color: "primary",
        inset: true,
        hideDetails: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_520));
    let __VLS_524;
    const __VLS_525 = {
        /** @type {typeof __VLS_524.'update:modelValue'} */
        'onUpdate:modelValue': (__VLS_unwrap(onTogglePaper, {})),
    };
    void __VLS_525;
    var __VLS_522;
    var __VLS_523;
    // @ts-ignore
    [paperEnabled, savingPaperToggle, onTogglePaper,];
    let __VLS_526;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_527 = __VLS_asFunctionalComponent1(__VLS_526, new __VLS_526({
        // @ts-ignore
        cols: "12", sm: "4", md: "2",
    }));
    const __VLS_528 = __VLS_527({
        cols: "12",
        sm: "4",
        md: "2",
    }, ...__VLS_functionalComponentArgsRest(__VLS_527));
    var __VLS_529;
    const { default: __VLS_531 } = __VLS_nonNull(__VLS_529.slots);
    let __VLS_532;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_533 = __VLS_asFunctionalComponent1(__VLS_532, new __VLS_532({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (paperForm.value.slAtr), modelModifiers: { number: true, }, label: "止损 (ATR 倍数)", type: "number", min: "0.2", max: "10", step: "0.1", density: "compact", variant: "outlined", hideDetails: true, disabled: (exitMode.value !== 'atr'), hint: (exitMode.value === 'atr' ? undefined : '仅在 ATR 模式生效'), persistentHint: true,
    }));
    const __VLS_534 = __VLS_533({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (paperForm.value.slAtr),
        modelModifiers: { number: true, },
        label: "止损 (ATR 倍数)",
        type: "number",
        min: "0.2",
        max: "10",
        step: "0.1",
        density: "compact",
        variant: "outlined",
        hideDetails: true,
        disabled: (exitMode.value !== 'atr'),
        hint: (exitMode.value === 'atr' ? undefined : '仅在 ATR 模式生效'),
        persistentHint: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_533));
    let __VLS_537;
    const __VLS_538 = {
        /** @type {typeof __VLS_537.'update:modelValue'} */
        'onUpdate:modelValue': (...[$event]) => {
            void $event;
            return (paperDirty.value = true);
            // @ts-ignore
            [exitMode, exitMode, paperForm, paperDirty,];
        },
    };
    void __VLS_538;
    var __VLS_535;
    var __VLS_536;
    // @ts-ignore
    [];
    let __VLS_539;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_540 = __VLS_asFunctionalComponent1(__VLS_539, new __VLS_539({
        // @ts-ignore
        cols: "12", sm: "4", md: "2",
    }));
    const __VLS_541 = __VLS_540({
        cols: "12",
        sm: "4",
        md: "2",
    }, ...__VLS_functionalComponentArgsRest(__VLS_540));
    var __VLS_542;
    const { default: __VLS_544 } = __VLS_nonNull(__VLS_542.slots);
    let __VLS_545;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_546 = __VLS_asFunctionalComponent1(__VLS_545, new __VLS_545({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (paperForm.value.tpR), modelModifiers: { number: true, }, label: "止盈 (R 倍数)", type: "number", min: "0.5", max: "10", step: "0.5", density: "compact", variant: "outlined", hideDetails: true, disabled: (exitMode.value !== 'atr'), hint: (exitMode.value === 'atr' ? undefined : '仅在 ATR 模式生效'), persistentHint: true,
    }));
    const __VLS_547 = __VLS_546({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (paperForm.value.tpR),
        modelModifiers: { number: true, },
        label: "止盈 (R 倍数)",
        type: "number",
        min: "0.5",
        max: "10",
        step: "0.5",
        density: "compact",
        variant: "outlined",
        hideDetails: true,
        disabled: (exitMode.value !== 'atr'),
        hint: (exitMode.value === 'atr' ? undefined : '仅在 ATR 模式生效'),
        persistentHint: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_546));
    let __VLS_550;
    const __VLS_551 = {
        /** @type {typeof __VLS_550.'update:modelValue'} */
        'onUpdate:modelValue': (...[$event]) => {
            void $event;
            return (paperDirty.value = true);
            // @ts-ignore
            [exitMode, exitMode, paperForm, paperDirty,];
        },
    };
    void __VLS_551;
    var __VLS_548;
    var __VLS_549;
    // @ts-ignore
    [];
    let __VLS_552;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_553 = __VLS_asFunctionalComponent1(__VLS_552, new __VLS_552({
        // @ts-ignore
        cols: "12", sm: "4", md: "2",
    }));
    const __VLS_554 = __VLS_553({
        cols: "12",
        sm: "4",
        md: "2",
    }, ...__VLS_functionalComponentArgsRest(__VLS_553));
    var __VLS_555;
    const { default: __VLS_557 } = __VLS_nonNull(__VLS_555.slots);
    let __VLS_558;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_559 = __VLS_asFunctionalComponent1(__VLS_558, new __VLS_558({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (paperForm.value.maxBars), modelModifiers: { number: true, }, label: "最大持有 (根)", type: "number", min: "1", max: "100", density: "compact", variant: "outlined", hideDetails: true,
    }));
    const __VLS_560 = __VLS_559({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (paperForm.value.maxBars),
        modelModifiers: { number: true, },
        label: "最大持有 (根)",
        type: "number",
        min: "1",
        max: "100",
        density: "compact",
        variant: "outlined",
        hideDetails: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_559));
    let __VLS_563;
    const __VLS_564 = {
        /** @type {typeof __VLS_563.'update:modelValue'} */
        'onUpdate:modelValue': (...[$event]) => {
            void $event;
            return (paperDirty.value = true);
            // @ts-ignore
            [paperForm, paperDirty,];
        },
    };
    void __VLS_564;
    var __VLS_561;
    var __VLS_562;
    // @ts-ignore
    [];
    let __VLS_565;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_566 = __VLS_asFunctionalComponent1(__VLS_565, new __VLS_565({
        // @ts-ignore
        cols: "12", md: "3", ...{ class: "d-flex justify-end" },
    }));
    const __VLS_567 = __VLS_566({
        cols: "12",
        md: "3",
        ...{ class: "d-flex justify-end" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_566));
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['justify-end']} */ ;
    var __VLS_568;
    const { default: __VLS_570 } = __VLS_nonNull(__VLS_568.slots);
    let __VLS_571;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_572 = __VLS_asFunctionalComponent1(__VLS_571, new __VLS_571({
        // @ts-ignore
        ...{ 'onClick': {} }, color: "primary", variant: "tonal", prependIcon: "mdi-content-save", loading: (__VLS_unwrap(savingPaperConfig, {})), disabled: (!paperFormValid.value || __VLS_unwrap(savingPaperConfig, {})),
    }));
    const __VLS_573 = __VLS_572({
        ...{ 'onClick': {} },
        color: "primary",
        variant: "tonal",
        prependIcon: "mdi-content-save",
        loading: (__VLS_unwrap(savingPaperConfig, {})),
        disabled: (!paperFormValid.value || __VLS_unwrap(savingPaperConfig, {})),
    }, ...__VLS_functionalComponentArgsRest(__VLS_572));
    let __VLS_576;
    const __VLS_577 = {
        /** @type {typeof __VLS_576.click} */
        onClick: (__VLS_unwrap(savePaperConfig, {})),
    };
    void __VLS_577;
    var __VLS_574;
    var __VLS_575;
    const { default: __VLS_578 } = __VLS_nonNull(__VLS_574.slots);
    // @ts-ignore
    [savingPaperConfig, savingPaperConfig, paperFormValid, savePaperConfig,];
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    let __VLS_579;
    /** @ts-ignore @type { | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider'] | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider']} */
    vDivider;
    // @ts-ignore
    const __VLS_580 = __VLS_asFunctionalComponent1(__VLS_579, new __VLS_579({
        // @ts-ignore
        ...{ class: "my-3" },
    }));
    const __VLS_581 = __VLS_580({
        ...{ class: "my-3" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_580));
    /** @type {__VLS_StyleScopedClasses['my-3']} */ ;
    let __VLS_584;
    /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
    vRow;
    // @ts-ignore
    const __VLS_585 = __VLS_asFunctionalComponent1(__VLS_584, new __VLS_584({
        // @ts-ignore
        dense: true, align: "center",
    }));
    const __VLS_586 = __VLS_585({
        dense: true,
        align: "center",
    }, ...__VLS_functionalComponentArgsRest(__VLS_585));
    var __VLS_587;
    const { default: __VLS_589 } = __VLS_nonNull(__VLS_587.slots);
    let __VLS_590;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_591 = __VLS_asFunctionalComponent1(__VLS_590, new __VLS_590({
        // @ts-ignore
        cols: "12", sm: "6", md: "3",
    }));
    const __VLS_592 = __VLS_591({
        cols: "12",
        sm: "6",
        md: "3",
    }, ...__VLS_functionalComponentArgsRest(__VLS_591));
    var __VLS_593;
    const { default: __VLS_595 } = __VLS_nonNull(__VLS_593.slots);
    let __VLS_596;
    /** @ts-ignore @type { | typeof __VLS_components.vSelect | typeof __VLS_components.VSelect | typeof __VLS_components['v-select'] | typeof __VLS_components.vSelect | typeof __VLS_components.VSelect | typeof __VLS_components['v-select']} */
    vSelect;
    // @ts-ignore
    const __VLS_597 = __VLS_asFunctionalComponent1(__VLS_596, new __VLS_596({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (paperForm.value.atrTimeframe), items: (__VLS_unwrap(ATR_TIMEFRAMES, {})), label: "实盘 ATR 周期", density: "compact", variant: "outlined", hideDetails: true, disabled: (exitMode.value !== 'atr'), hint: (exitMode.value === 'atr' ? undefined : '仅 ATR 模式生效'), persistentHint: true,
    }));
    const __VLS_598 = __VLS_597({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (paperForm.value.atrTimeframe),
        items: (__VLS_unwrap(ATR_TIMEFRAMES, {})),
        label: "实盘 ATR 周期",
        density: "compact",
        variant: "outlined",
        hideDetails: true,
        disabled: (exitMode.value !== 'atr'),
        hint: (exitMode.value === 'atr' ? undefined : '仅 ATR 模式生效'),
        persistentHint: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_597));
    let __VLS_601;
    const __VLS_602 = {
        /** @type {typeof __VLS_601.'update:modelValue'} */
        'onUpdate:modelValue': (...[$event]) => {
            void $event;
            return (paperDirty.value = true);
            // @ts-ignore
            [exitMode, exitMode, paperForm, paperDirty, ATR_TIMEFRAMES,];
        },
    };
    void __VLS_602;
    var __VLS_599;
    var __VLS_600;
    // @ts-ignore
    [];
    let __VLS_603;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_604 = __VLS_asFunctionalComponent1(__VLS_603, new __VLS_603({
        // @ts-ignore
        cols: "12", sm: "6", md: "4",
    }));
    const __VLS_605 = __VLS_604({
        cols: "12",
        sm: "6",
        md: "4",
    }, ...__VLS_functionalComponentArgsRest(__VLS_604));
    var __VLS_606;
    const { default: __VLS_608 } = __VLS_nonNull(__VLS_606.slots);
    let __VLS_609;
    /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch'] | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
    vSwitch;
    // @ts-ignore
    const __VLS_610 = __VLS_asFunctionalComponent1(__VLS_609, new __VLS_609({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (liveTimeoutEnabled.value), loading: (__VLS_unwrap(savingLiveTimeout, {})), label: "实盘超时平仓", color: "warning", inset: true, hideDetails: true,
    }));
    const __VLS_611 = __VLS_610({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (liveTimeoutEnabled.value),
        loading: (__VLS_unwrap(savingLiveTimeout, {})),
        label: "实盘超时平仓",
        color: "warning",
        inset: true,
        hideDetails: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_610));
    let __VLS_614;
    const __VLS_615 = {
        /** @type {typeof __VLS_614.'update:modelValue'} */
        'onUpdate:modelValue': (__VLS_unwrap(onToggleLiveTimeout, {})),
    };
    void __VLS_615;
    var __VLS_612;
    var __VLS_613;
    // @ts-ignore
    [liveTimeoutEnabled, savingLiveTimeout, onToggleLiveTimeout,];
    let __VLS_616;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_617 = __VLS_asFunctionalComponent1(__VLS_616, new __VLS_616({
        // @ts-ignore
        cols: "12", md: "5", ...{ class: "text-caption text-grey" },
    }));
    const __VLS_618 = __VLS_617({
        cols: "12",
        md: "5",
        ...{ class: "text-caption text-grey" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_617));
    /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
    var __VLS_619;
    const { default: __VLS_621 } = __VLS_nonNull(__VLS_619.slots);
    __VLS_asFunctionalElement1(__VLS_intrinsics.b, __VLS_intrinsics.b)({});
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    let __VLS_622;
    /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
    vRow;
    // @ts-ignore
    const __VLS_623 = __VLS_asFunctionalComponent1(__VLS_622, new __VLS_622({
        // @ts-ignore
        dense: true, align: "center", ...{ class: "mt-1" },
    }));
    const __VLS_624 = __VLS_623({
        dense: true,
        align: "center",
        ...{ class: "mt-1" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_623));
    /** @type {__VLS_StyleScopedClasses['mt-1']} */ ;
    var __VLS_625;
    const { default: __VLS_627 } = __VLS_nonNull(__VLS_625.slots);
    let __VLS_628;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_629 = __VLS_asFunctionalComponent1(__VLS_628, new __VLS_628({
        // @ts-ignore
        cols: "12", sm: "6", md: "4",
    }));
    const __VLS_630 = __VLS_629({
        cols: "12",
        sm: "6",
        md: "4",
    }, ...__VLS_functionalComponentArgsRest(__VLS_629));
    var __VLS_631;
    const { default: __VLS_633 } = __VLS_nonNull(__VLS_631.slots);
    let __VLS_634;
    /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch'] | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
    vSwitch;
    // @ts-ignore
    const __VLS_635 = __VLS_asFunctionalComponent1(__VLS_634, new __VLS_634({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (__VLS_unwrap(sltpGuardEnabled, {})), loading: (__VLS_unwrap(savingSltpGuard, {})), label: "止损巡检（缺单自动补挂）", color: "success", inset: true, hideDetails: true,
    }));
    const __VLS_636 = __VLS_635({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (__VLS_unwrap(sltpGuardEnabled, {})),
        loading: (__VLS_unwrap(savingSltpGuard, {})),
        label: "止损巡检（缺单自动补挂）",
        color: "success",
        inset: true,
        hideDetails: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_635));
    let __VLS_639;
    const __VLS_640 = {
        /** @type {typeof __VLS_639.'update:modelValue'} */
        'onUpdate:modelValue': (__VLS_unwrap(onToggleSltpGuard, {})),
    };
    void __VLS_640;
    var __VLS_637;
    var __VLS_638;
    // @ts-ignore
    [sltpGuardEnabled, savingSltpGuard, onToggleSltpGuard,];
    let __VLS_641;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_642 = __VLS_asFunctionalComponent1(__VLS_641, new __VLS_641({
        // @ts-ignore
        cols: "12", md: "8", ...{ class: "text-caption text-grey" },
    }));
    const __VLS_643 = __VLS_642({
        cols: "12",
        md: "8",
        ...{ class: "text-caption text-grey" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_642));
    /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
    var __VLS_644;
    const { default: __VLS_646 } = __VLS_nonNull(__VLS_644.slots);
    __VLS_asFunctionalElement1(__VLS_intrinsics.b, __VLS_intrinsics.b)({});
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    if (liveExit.value.positions.length > 0) {
        let __VLS_647;
        /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
        vRow;
        // @ts-ignore
        const __VLS_648 = __VLS_asFunctionalComponent1(__VLS_647, new __VLS_647({
            // @ts-ignore
            dense: true, ...{ class: "mt-2" },
        }));
        const __VLS_649 = __VLS_648({
            dense: true,
            ...{ class: "mt-2" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_648));
        /** @type {__VLS_StyleScopedClasses['mt-2']} */ ;
        var __VLS_650;
        const { default: __VLS_652 } = __VLS_nonNull(__VLS_650.slots);
        let __VLS_653;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_654 = __VLS_asFunctionalComponent1(__VLS_653, new __VLS_653({
            // @ts-ignore
            cols: "12",
        }));
        const __VLS_655 = __VLS_654({
            cols: "12",
        }, ...__VLS_functionalComponentArgsRest(__VLS_654));
        var __VLS_656;
        const { default: __VLS_658 } = __VLS_nonNull(__VLS_656.slots);
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "text-subtitle-2 mb-1" },
        });
        /** @type {__VLS_StyleScopedClasses['text-subtitle-2']} */ ;
        /** @type {__VLS_StyleScopedClasses['mb-1']} */ ;
        (liveExit.value.positions.length);
        let __VLS_659;
        /** @ts-ignore @type { | typeof __VLS_components.vTable | typeof __VLS_components.VTable | typeof __VLS_components['v-table'] | typeof __VLS_components.vTable | typeof __VLS_components.VTable | typeof __VLS_components['v-table']} */
        vTable;
        // @ts-ignore
        const __VLS_660 = __VLS_asFunctionalComponent1(__VLS_659, new __VLS_659({
            // @ts-ignore
            density: "compact",
        }));
        const __VLS_661 = __VLS_660({
            density: "compact",
        }, ...__VLS_functionalComponentArgsRest(__VLS_660));
        var __VLS_662;
        const { default: __VLS_664 } = __VLS_nonNull(__VLS_662.slots);
        __VLS_asFunctionalElement1(__VLS_intrinsics.thead, __VLS_intrinsics.thead)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.tr, __VLS_intrinsics.tr)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.tbody, __VLS_intrinsics.tbody)({});
        const __VLS_665 = __VLS_tryAsConstant((liveExit.value.positions));
        for (const [row] of __VLS_vFor(__VLS_nonNull(__VLS_665))) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.tr, __VLS_intrinsics.tr)({
                key: (row.full_symbol || row.symbol),
            });
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({});
            (row.symbol);
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                ...{ class: (__VLS_unwrap(directionColor, {})(row.side)) },
            });
            (__VLS_unwrap(directionLabel, {})(row.side));
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({});
            (row.timeframe || '—');
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({});
            (row.bars_held ?? '—');
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({});
            (row.max_bars);
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({});
            (row.strategy || '—');
            // @ts-ignore
            [liveExit, liveExit, liveExit, directionColor, directionLabel,];
        }
        // @ts-ignore
        [];
        // @ts-ignore
        [];
        // @ts-ignore
        [];
    }
    let __VLS_666;
    /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
    vRow;
    // @ts-ignore
    const __VLS_667 = __VLS_asFunctionalComponent1(__VLS_666, new __VLS_666({
        // @ts-ignore
        dense: true, ...{ class: "mt-3" },
    }));
    const __VLS_668 = __VLS_667({
        dense: true,
        ...{ class: "mt-3" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_667));
    /** @type {__VLS_StyleScopedClasses['mt-3']} */ ;
    var __VLS_669;
    const { default: __VLS_671 } = __VLS_nonNull(__VLS_669.slots);
    let __VLS_672;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_673 = __VLS_asFunctionalComponent1(__VLS_672, new __VLS_672({
        // @ts-ignore
        cols: "12", md: "7",
    }));
    const __VLS_674 = __VLS_673({
        cols: "12",
        md: "7",
    }, ...__VLS_functionalComponentArgsRest(__VLS_673));
    var __VLS_675;
    const { default: __VLS_677 } = __VLS_nonNull(__VLS_675.slots);
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "text-subtitle-2 mb-1" },
    });
    /** @type {__VLS_StyleScopedClasses['text-subtitle-2']} */ ;
    /** @type {__VLS_StyleScopedClasses['mb-1']} */ ;
    (tracking.value.open_positions.length);
    if (tracking.value.open_positions.length > 0) {
        let __VLS_678;
        /** @ts-ignore @type { | typeof __VLS_components.vTable | typeof __VLS_components.VTable | typeof __VLS_components['v-table'] | typeof __VLS_components.vTable | typeof __VLS_components.VTable | typeof __VLS_components['v-table']} */
        vTable;
        // @ts-ignore
        const __VLS_679 = __VLS_asFunctionalComponent1(__VLS_678, new __VLS_678({
            // @ts-ignore
            density: "compact",
        }));
        const __VLS_680 = __VLS_679({
            density: "compact",
        }, ...__VLS_functionalComponentArgsRest(__VLS_679));
        var __VLS_681;
        const { default: __VLS_683 } = __VLS_nonNull(__VLS_681.slots);
        __VLS_asFunctionalElement1(__VLS_intrinsics.thead, __VLS_intrinsics.thead)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.tr, __VLS_intrinsics.tr)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.tbody, __VLS_intrinsics.tbody)({});
        const __VLS_684 = __VLS_tryAsConstant((tracking.value.open_positions));
        for (const [position] of __VLS_vFor(__VLS_nonNull(__VLS_684))) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.tr, __VLS_intrinsics.tr)({
                key: (position.id),
            });
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                ...{ class: "font-weight-medium" },
            });
            /** @type {__VLS_StyleScopedClasses['font-weight-medium']} */ ;
            (position.symbol);
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({});
            let __VLS_685;
            /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
            vChip;
            // @ts-ignore
            const __VLS_686 = __VLS_asFunctionalComponent1(__VLS_685, new __VLS_685({
                // @ts-ignore
                size: "x-small", variant: "tonal", color: (__VLS_unwrap(directionColor, {})(position.direction)),
            }));
            const __VLS_687 = __VLS_686({
                size: "x-small",
                variant: "tonal",
                color: (__VLS_unwrap(directionColor, {})(position.direction)),
            }, ...__VLS_functionalComponentArgsRest(__VLS_686));
            var __VLS_688;
            const { default: __VLS_690 } = __VLS_nonNull(__VLS_688.slots);
            (__VLS_unwrap(directionLabel, {})(position.direction));
            // @ts-ignore
            [tracking, tracking, tracking, directionColor, directionLabel,];
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({});
            (position.timeframe);
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({});
            (__VLS_unwrap(formatPrice, {})(position.entry_price));
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                ...{ class: "text-error" },
            });
            /** @type {__VLS_StyleScopedClasses['text-error']} */ ;
            (__VLS_unwrap(formatPrice, {})(position.stop_loss));
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                ...{ class: "text-success" },
            });
            /** @type {__VLS_StyleScopedClasses['text-success']} */ ;
            (__VLS_unwrap(formatPrice, {})(position.take_profit));
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                ...{ class: "text-caption text-grey" },
            });
            /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
            (__VLS_unwrap(formatTime, {})(position.opened_at));
            // @ts-ignore
            [formatTime, formatPrice, formatPrice, formatPrice,];
        }
        // @ts-ignore
        [];
    }
    else {
        let __VLS_691;
        /** @ts-ignore @type { | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert'] | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert']} */
        vAlert;
        // @ts-ignore
        const __VLS_692 = __VLS_asFunctionalComponent1(__VLS_691, new __VLS_691({
            // @ts-ignore
            type: "info", variant: "text", density: "compact", ...{ class: "text-caption" },
        }));
        const __VLS_693 = __VLS_692({
            type: "info",
            variant: "text",
            density: "compact",
            ...{ class: "text-caption" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_692));
        /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
        var __VLS_694;
        const { default: __VLS_696 } = __VLS_nonNull(__VLS_694.slots);
        // @ts-ignore
        [];
    }
    // @ts-ignore
    [];
    let __VLS_697;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_698 = __VLS_asFunctionalComponent1(__VLS_697, new __VLS_697({
        // @ts-ignore
        cols: "12", md: "5",
    }));
    const __VLS_699 = __VLS_698({
        cols: "12",
        md: "5",
    }, ...__VLS_functionalComponentArgsRest(__VLS_698));
    var __VLS_700;
    const { default: __VLS_702 } = __VLS_nonNull(__VLS_700.slots);
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "text-subtitle-2 mb-1" },
    });
    /** @type {__VLS_StyleScopedClasses['text-subtitle-2']} */ ;
    /** @type {__VLS_StyleScopedClasses['mb-1']} */ ;
    if (tracking.value.paper_stats.total > 0) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "d-flex flex-wrap ga-2 mb-2" },
        });
        /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
        /** @type {__VLS_StyleScopedClasses['flex-wrap']} */ ;
        /** @type {__VLS_StyleScopedClasses['ga-2']} */ ;
        /** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
        let __VLS_703;
        /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
        vChip;
        // @ts-ignore
        const __VLS_704 = __VLS_asFunctionalComponent1(__VLS_703, new __VLS_703({
            // @ts-ignore
            size: "small", variant: "tonal",
        }));
        const __VLS_705 = __VLS_704({
            size: "small",
            variant: "tonal",
        }, ...__VLS_functionalComponentArgsRest(__VLS_704));
        var __VLS_706;
        const { default: __VLS_708 } = __VLS_nonNull(__VLS_706.slots);
        (tracking.value.paper_stats.total);
        // @ts-ignore
        [tracking, tracking,];
        let __VLS_709;
        /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
        vChip;
        // @ts-ignore
        const __VLS_710 = __VLS_asFunctionalComponent1(__VLS_709, new __VLS_709({
            // @ts-ignore
            size: "small", variant: "tonal",
        }));
        const __VLS_711 = __VLS_710({
            size: "small",
            variant: "tonal",
        }, ...__VLS_functionalComponentArgsRest(__VLS_710));
        var __VLS_712;
        const { default: __VLS_714 } = __VLS_nonNull(__VLS_712.slots);
        (tracking.value.paper_stats.win_rate);
        // @ts-ignore
        [tracking,];
        let __VLS_715;
        /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
        vChip;
        // @ts-ignore
        const __VLS_716 = __VLS_asFunctionalComponent1(__VLS_715, new __VLS_715({
            // @ts-ignore
            size: "small", variant: "tonal",
        }));
        const __VLS_717 = __VLS_716({
            size: "small",
            variant: "tonal",
        }, ...__VLS_functionalComponentArgsRest(__VLS_716));
        var __VLS_718;
        const { default: __VLS_720 } = __VLS_nonNull(__VLS_718.slots);
        (__VLS_unwrap(formatPct, {})(tracking.value.paper_stats.avg_pnl_pct));
        // @ts-ignore
        [tracking, formatPct,];
        let __VLS_721;
        /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
        vChip;
        // @ts-ignore
        const __VLS_722 = __VLS_asFunctionalComponent1(__VLS_721, new __VLS_721({
            // @ts-ignore
            size: "small", variant: "tonal",
        }));
        const __VLS_723 = __VLS_722({
            size: "small",
            variant: "tonal",
        }, ...__VLS_functionalComponentArgsRest(__VLS_722));
        var __VLS_724;
        const { default: __VLS_726 } = __VLS_nonNull(__VLS_724.slots);
        (__VLS_unwrap(formatPct, {})(tracking.value.paper_stats.sum_pnl_pct));
        // @ts-ignore
        [tracking, formatPct,];
        let __VLS_727;
        /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
        vChip;
        // @ts-ignore
        const __VLS_728 = __VLS_asFunctionalComponent1(__VLS_727, new __VLS_727({
            // @ts-ignore
            size: "small", variant: "tonal",
        }));
        const __VLS_729 = __VLS_728({
            size: "small",
            variant: "tonal",
        }, ...__VLS_functionalComponentArgsRest(__VLS_728));
        var __VLS_730;
        const { default: __VLS_732 } = __VLS_nonNull(__VLS_730.slots);
        (tracking.value.paper_stats.avg_bars);
        // @ts-ignore
        [tracking,];
    }
    if (tracking.value.trades.length > 0) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "text-caption text-grey" },
        });
        /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
        const __VLS_733 = __VLS_tryAsConstant((tracking.value.trades.slice(0, 5)));
        for (const [trade] of __VLS_vFor(__VLS_nonNull(__VLS_733))) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
                key: (trade.id),
                ...{ class: "mr-2" },
            });
            /** @type {__VLS_StyleScopedClasses['mr-2']} */ ;
            (trade.symbol);
            (__VLS_unwrap(directionLabel, {})(trade.direction));
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
                ...{ class: (trade.pnl_pct >= 0 ? 'text-success' : 'text-error') },
            });
            (__VLS_unwrap(formatPct, {})(trade.pnl_pct));
            (__VLS_unwrap(exitReasonLabel, {})(trade.reason));
            // @ts-ignore
            [tracking, tracking, directionLabel, formatPct, exitReasonLabel,];
        }
    }
    else {
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "text-caption text-grey" },
        });
        /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
    }
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "text-subtitle-2 mt-4 mb-1" },
    });
    /** @type {__VLS_StyleScopedClasses['text-subtitle-2']} */ ;
    /** @type {__VLS_StyleScopedClasses['mt-4']} */ ;
    /** @type {__VLS_StyleScopedClasses['mb-1']} */ ;
    if (tracking.value.forward_stats.length > 0) {
        let __VLS_734;
        /** @ts-ignore @type { | typeof __VLS_components.vTable | typeof __VLS_components.VTable | typeof __VLS_components['v-table'] | typeof __VLS_components.vTable | typeof __VLS_components.VTable | typeof __VLS_components['v-table']} */
        vTable;
        // @ts-ignore
        const __VLS_735 = __VLS_asFunctionalComponent1(__VLS_734, new __VLS_734({
            // @ts-ignore
            density: "compact",
        }));
        const __VLS_736 = __VLS_735({
            density: "compact",
        }, ...__VLS_functionalComponentArgsRest(__VLS_735));
        var __VLS_737;
        const { default: __VLS_739 } = __VLS_nonNull(__VLS_737.slots);
        __VLS_asFunctionalElement1(__VLS_intrinsics.thead, __VLS_intrinsics.thead)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.tr, __VLS_intrinsics.tr)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        const __VLS_740 = __VLS_tryAsConstant((tracking.value.params.forward_bars));
        for (const [bar] of __VLS_vFor(__VLS_nonNull(__VLS_740))) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
                key: (bar),
                ...{ class: "text-left" },
            });
            /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
            (bar);
            // @ts-ignore
            [tracking, tracking,];
        }
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.tbody, __VLS_intrinsics.tbody)({});
        const __VLS_741 = __VLS_tryAsConstant((tracking.value.forward_stats));
        for (const [row] of __VLS_vFor(__VLS_nonNull(__VLS_741))) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.tr, __VLS_intrinsics.tr)({
                key: (`${row.timeframe}-${row.strategy}`),
            });
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({});
            (row.timeframe);
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({});
            (__VLS_unwrap(strategyLabel, {})(row.strategy));
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({});
            (row.samples);
            const __VLS_742 = __VLS_tryAsConstant((tracking.value.params.forward_bars));
            for (const [bar] of __VLS_vFor(__VLS_nonNull(__VLS_742))) {
                __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                    key: (bar),
                });
                __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
                    ...{ class: (__VLS_unwrap(pctClass, {})(row[`h${bar}`])) },
                });
                (__VLS_unwrap(formatPct, {})(row[`h${bar}`]));
                // @ts-ignore
                [tracking, tracking, formatPct, strategyLabel, pctClass,];
            }
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({});
            (row.h4_win ?? '—');
            // @ts-ignore
            [];
        }
        // @ts-ignore
        [];
    }
    else {
        let __VLS_743;
        /** @ts-ignore @type { | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert'] | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert']} */
        vAlert;
        // @ts-ignore
        const __VLS_744 = __VLS_asFunctionalComponent1(__VLS_743, new __VLS_743({
            // @ts-ignore
            type: "info", variant: "text", density: "compact", ...{ class: "text-caption" },
        }));
        const __VLS_745 = __VLS_744({
            type: "info",
            variant: "text",
            density: "compact",
            ...{ class: "text-caption" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_744));
        /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
        var __VLS_746;
        const { default: __VLS_748 } = __VLS_nonNull(__VLS_746.slots);
        (tracking.value.params.forward_bars.join(' / '));
        // @ts-ignore
        [tracking,];
    }
    // @ts-ignore
    [];
    const __VLS_749 = PageCard || PageCard;
    // @ts-ignore
    const __VLS_750 = __VLS_asFunctionalComponent1(__VLS_749, new __VLS_749({
        // @ts-ignore
        title: "信号列表", spaced: true,
    }));
    const __VLS_751 = __VLS_750({
        title: "信号列表",
        spaced: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_750));
    var __VLS_752;
    const { default: __VLS_754 } = __VLS_nonNull(__VLS_752.slots);
    {
        const { badges: __VLS_755 } = __VLS_nonNull(__VLS_752.slots);
        let __VLS_756;
        /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
        vChip;
        // @ts-ignore
        const __VLS_757 = __VLS_asFunctionalComponent1(__VLS_756, new __VLS_756({
            // @ts-ignore
            size: "small", variant: "tonal",
        }));
        const __VLS_758 = __VLS_757({
            size: "small",
            variant: "tonal",
        }, ...__VLS_functionalComponentArgsRest(__VLS_757));
        var __VLS_759;
        const { default: __VLS_761 } = __VLS_nonNull(__VLS_759.slots);
        (filteredSignals.value.length);
        (signals.value.length);
        // @ts-ignore
        [signals, filteredSignals,];
        let __VLS_762;
        /** @ts-ignore @type { | typeof __VLS_components.vBtnToggle | typeof __VLS_components.VBtnToggle | typeof __VLS_components['v-btn-toggle'] | typeof __VLS_components.vBtnToggle | typeof __VLS_components.VBtnToggle | typeof __VLS_components['v-btn-toggle']} */
        vBtnToggle;
        // @ts-ignore
        const __VLS_763 = __VLS_asFunctionalComponent1(__VLS_762, new __VLS_762({
            // @ts-ignore
            ...{ 'onUpdate:modelValue': {} }, modelValue: (__VLS_unwrap(directionFilter, {})), mandatory: true, density: "compact", variant: "outlined", divided: true,
        }));
        const __VLS_764 = __VLS_763({
            ...{ 'onUpdate:modelValue': {} },
            modelValue: (__VLS_unwrap(directionFilter, {})),
            mandatory: true,
            density: "compact",
            variant: "outlined",
            divided: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_763));
        let __VLS_767;
        const __VLS_768 = {
            /** @type {typeof __VLS_767.'update:modelValue'} */
            'onUpdate:modelValue': (__VLS_unwrap(onDirectionFilterChange, {})),
        };
        void __VLS_768;
        var __VLS_765;
        var __VLS_766;
        const { default: __VLS_769 } = __VLS_nonNull(__VLS_765.slots);
        let __VLS_770;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_771 = __VLS_asFunctionalComponent1(__VLS_770, new __VLS_770({
            // @ts-ignore
            value: "all", size: "small",
        }));
        const __VLS_772 = __VLS_771({
            value: "all",
            size: "small",
        }, ...__VLS_functionalComponentArgsRest(__VLS_771));
        var __VLS_773;
        const { default: __VLS_775 } = __VLS_nonNull(__VLS_773.slots);
        // @ts-ignore
        [directionFilter, onDirectionFilterChange,];
        let __VLS_776;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_777 = __VLS_asFunctionalComponent1(__VLS_776, new __VLS_776({
            // @ts-ignore
            value: "long", size: "small",
        }));
        const __VLS_778 = __VLS_777({
            value: "long",
            size: "small",
        }, ...__VLS_functionalComponentArgsRest(__VLS_777));
        var __VLS_779;
        const { default: __VLS_781 } = __VLS_nonNull(__VLS_779.slots);
        // @ts-ignore
        [];
        let __VLS_782;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_783 = __VLS_asFunctionalComponent1(__VLS_782, new __VLS_782({
            // @ts-ignore
            value: "short", size: "small",
        }));
        const __VLS_784 = __VLS_783({
            value: "short",
            size: "small",
        }, ...__VLS_functionalComponentArgsRest(__VLS_783));
        var __VLS_785;
        const { default: __VLS_787 } = __VLS_nonNull(__VLS_785.slots);
        // @ts-ignore
        [];
        let __VLS_788;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_789 = __VLS_asFunctionalComponent1(__VLS_788, new __VLS_788({
            // @ts-ignore
            value: "neutral", size: "small",
        }));
        const __VLS_790 = __VLS_789({
            value: "neutral",
            size: "small",
        }, ...__VLS_functionalComponentArgsRest(__VLS_789));
        var __VLS_791;
        const { default: __VLS_793 } = __VLS_nonNull(__VLS_791.slots);
        // @ts-ignore
        [];
        // @ts-ignore
        [];
        // @ts-ignore
        [];
    }
    if (filteredSignals.value.length > 0) {
        let __VLS_794;
        /** @ts-ignore @type { | typeof __VLS_components.vTable | typeof __VLS_components.VTable | typeof __VLS_components['v-table'] | typeof __VLS_components.vTable | typeof __VLS_components.VTable | typeof __VLS_components['v-table']} */
        vTable;
        // @ts-ignore
        const __VLS_795 = __VLS_asFunctionalComponent1(__VLS_794, new __VLS_794({
            // @ts-ignore
            density: "compact", ...{ class: "signal-table" },
        }));
        const __VLS_796 = __VLS_795({
            density: "compact",
            ...{ class: "signal-table" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_795));
        /** @type {__VLS_StyleScopedClasses['signal-table']} */ ;
        var __VLS_797;
        const { default: __VLS_799 } = __VLS_nonNull(__VLS_797.slots);
        __VLS_asFunctionalElement1(__VLS_intrinsics.thead, __VLS_intrinsics.thead)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.tr, __VLS_intrinsics.tr)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.tbody, __VLS_intrinsics.tbody)({});
        const __VLS_800 = __VLS_tryAsConstant((filteredSignals.value));
        for (const [signal] of __VLS_vFor(__VLS_nonNull(__VLS_800))) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.tr, __VLS_intrinsics.tr)({
                key: (signal.id),
            });
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                ...{ class: "text-caption text-no-wrap" },
            });
            /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-no-wrap']} */ ;
            (__VLS_unwrap(formatTime, {})(signal.created_at));
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                ...{ class: "font-weight-medium text-no-wrap" },
            });
            /** @type {__VLS_StyleScopedClasses['font-weight-medium']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-no-wrap']} */ ;
            (signal.symbol);
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({});
            let __VLS_801;
            /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
            vChip;
            // @ts-ignore
            const __VLS_802 = __VLS_asFunctionalComponent1(__VLS_801, new __VLS_801({
                // @ts-ignore
                size: "small", variant: "tonal", color: (__VLS_unwrap(directionColor, {})(signal.direction)),
            }));
            const __VLS_803 = __VLS_802({
                size: "small",
                variant: "tonal",
                color: (__VLS_unwrap(directionColor, {})(signal.direction)),
            }, ...__VLS_functionalComponentArgsRest(__VLS_802));
            var __VLS_804;
            const { default: __VLS_806 } = __VLS_nonNull(__VLS_804.slots);
            (__VLS_unwrap(directionLabel, {})(signal.direction));
            // @ts-ignore
            [formatTime, directionColor, directionLabel, filteredSignals, filteredSignals,];
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                ...{ class: "text-no-wrap" },
            });
            /** @type {__VLS_StyleScopedClasses['text-no-wrap']} */ ;
            (__VLS_unwrap(strategyLabel, {})(signal.strategy));
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                ...{ class: "text-no-wrap" },
            });
            /** @type {__VLS_StyleScopedClasses['text-no-wrap']} */ ;
            (signal.timeframe);
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                ...{ class: "text-no-wrap" },
            });
            /** @type {__VLS_StyleScopedClasses['text-no-wrap']} */ ;
            (__VLS_unwrap(formatPrice, {})(signal.price));
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                ...{ class: "text-no-wrap text-caption" },
                ...{ class: (__VLS_unwrap(volumeClass, {})(signal)) },
            });
            /** @type {__VLS_StyleScopedClasses['text-no-wrap']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
            (__VLS_unwrap(volumeLabel, {})(signal));
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                ...{ class: "text-no-wrap text-caption" },
            });
            /** @type {__VLS_StyleScopedClasses['text-no-wrap']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
            (__VLS_unwrap(fwdLabel, {})(signal));
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                ...{ class: "signal-title" },
            });
            /** @type {__VLS_StyleScopedClasses['signal-title']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                ...{ class: "text-body-2" },
            });
            /** @type {__VLS_StyleScopedClasses['text-body-2']} */ ;
            (signal.title);
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                ...{ class: "text-caption text-grey signal-message" },
            });
            /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
            /** @type {__VLS_StyleScopedClasses['signal-message']} */ ;
            (__VLS_unwrap(plainMessage, {})(signal.message));
            // @ts-ignore
            [formatPrice, strategyLabel, volumeClass, volumeLabel, fwdLabel, plainMessage,];
        }
        // @ts-ignore
        [];
    }
    else {
        let __VLS_807;
        /** @ts-ignore @type { | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert'] | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert']} */
        vAlert;
        // @ts-ignore
        const __VLS_808 = __VLS_asFunctionalComponent1(__VLS_807, new __VLS_807({
            // @ts-ignore
            type: "info", variant: "text", density: "compact", ...{ class: "text-caption" },
        }));
        const __VLS_809 = __VLS_808({
            type: "info",
            variant: "text",
            density: "compact",
            ...{ class: "text-caption" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_808));
        /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
        var __VLS_810;
        const { default: __VLS_812 } = __VLS_nonNull(__VLS_810.slots);
        // @ts-ignore
        [];
    }
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    return {};
};
void [__VLS_template];
const __VLS_export = (await import('vue')).defineComponent({});
export default {};
