import { onMounted, onUnmounted, reactive, ref } from 'vue';
import api from '@/services/api';
import { useSnackbarStore } from '@/stores/snackbar';
import { getErrorMessage } from '@/utils/errors';
import { formatNumberOrDash as formatNumber } from '@/utils/format';
import SmartSelect from '@/components/SmartSelect.vue';
import PageCard from '@/components/PageCard.vue';
const snackbarStore = useSnackbarStore();
const timeframes = ['15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d'];
const emptyStatus = () => ({
    enabled: false,
    running: false,
    started_at: null,
    last_error: null,
    timeframe: null,
    positions: [],
    api: {
        request_count: 0,
        error_count: 0,
        failures: 0,
        circuit_open: false,
        circuit_open_until: 0,
        cooldown_until: 0,
    },
    config: {},
});
const status = ref(emptyStatus());
const saving = ref(false);
const form = reactive({
    timeframe: '2h',
    tp1_r_multiple: 1,
    tp2_r_multiple: 2,
    tp3_r_multiple: 3,
    t1_structure_lookback: 7,
    t2_structure_lookback: 26,
    t3_structure_lookback: 83,
    structure_buffer_atr: 0.5,
    profit_protection_enabled: true,
    emergency_enabled: true,
    exchange_hard_stop_enabled: true,
    hard_stop_min_distance_pct: 0.05,
});
let pollTimer;
const hasTriggered = (row) => row.tp1_done || row.tp2_done || row.tp3_done || row.t1_done || row.t2_done || row.t3_done;
const applyConfig = (config) => {
    if (typeof config.timeframe === 'string')
        form.timeframe = config.timeframe;
    for (const key of [
        'tp1_r_multiple',
        'tp2_r_multiple',
        'tp3_r_multiple',
        't1_structure_lookback',
        't2_structure_lookback',
        't3_structure_lookback',
        'structure_buffer_atr',
        'hard_stop_min_distance_pct',
    ]) {
        const value = Number(config[key]);
        if (Number.isFinite(value))
            form[key] = value;
    }
    for (const key of [
        'profit_protection_enabled',
        'emergency_enabled',
        'exchange_hard_stop_enabled',
    ]) {
        if (typeof config[key] === 'boolean')
            form[key] = config[key];
    }
};
const fetchStatus = async () => {
    try {
        const response = await api.get('/api/protection');
        status.value = response.data;
        applyConfig(response.data.config ?? {});
    }
    catch (error) {
        console.warn('获取仓位保护状态失败:', getErrorMessage(error));
    }
};
const saveConfig = async () => {
    saving.value = true;
    try {
        await api.post('/api/protection/config', { ...form });
        snackbarStore.show({ message: '仓位保护参数已保存并生效。', color: 'success' });
        await fetchStatus();
    }
    catch (error) {
        snackbarStore.show({ message: getErrorMessage(error), color: 'error' });
    }
    finally {
        saving.value = false;
    }
};
const onToggleEnabled = async (value) => {
    saving.value = true;
    try {
        await api.post('/api/protection/config', { enabled: value === true });
        snackbarStore.show({
            message: value ? '仓位保护已启用，引擎将在数秒内启动。' : '仓位保护已停用。',
            color: 'success',
        });
        await fetchStatus();
    }
    catch (error) {
        snackbarStore.show({ message: getErrorMessage(error), color: 'error' });
    }
    finally {
        saving.value = false;
    }
};
onMounted(async () => {
    await fetchStatus();
    pollTimer = window.setInterval(() => {
        void fetchStatus();
    }, 10000);
});
onUnmounted(() => {
    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = undefined;
    }
});
const __VLS_ctx = {};
let __VLS_components;
let __VLS_intrinsics;
let __VLS_directives;
void __VLS_ctx, __VLS_components, __VLS_intrinsics, __VLS_directives;
const __VLS_template = () => {
    __VLS_withDotValue(status, {});
    __VLS_withDotValue(form, {});
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
    const __VLS_0 = PageCard || PageCard;
    // @ts-ignore
    const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
        // @ts-ignore
        icon: "mdi-shield-check-outline", title: "仓位保护（实时风控）", error: (status.value.last_error),
    }));
    const __VLS_2 = __VLS_1({
        icon: "mdi-shield-check-outline",
        title: "仓位保护（实时风控）",
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
            size: "small", variant: "tonal", color: (status.value.running ? 'success' : 'grey'),
        }));
        const __VLS_9 = __VLS_8({
            size: "small",
            variant: "tonal",
            color: (status.value.running ? 'success' : 'grey'),
        }, ...__VLS_functionalComponentArgsRest(__VLS_8));
        var __VLS_10;
        const { default: __VLS_12 } = __VLS_nonNull(__VLS_10.slots);
        (status.value.running ? '守护中' : '未运行');
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
        (status.value.enabled ? '已启用' : '已停用');
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
        cols: "12", md: "4",
    }));
    const __VLS_27 = __VLS_26({
        cols: "12",
        md: "4",
    }, ...__VLS_functionalComponentArgsRest(__VLS_26));
    var __VLS_28;
    const { default: __VLS_30 } = __VLS_nonNull(__VLS_28.slots);
    let __VLS_31;
    /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch'] | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
    vSwitch;
    // @ts-ignore
    const __VLS_32 = __VLS_asFunctionalComponent1(__VLS_31, new __VLS_31({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (status.value.enabled), loading: (__VLS_unwrap(saving, {})), label: "启用仓位保护", color: "primary", inset: true, hideDetails: true,
    }));
    const __VLS_33 = __VLS_32({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (status.value.enabled),
        loading: (__VLS_unwrap(saving, {})),
        label: "启用仓位保护",
        color: "primary",
        inset: true,
        hideDetails: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_32));
    let __VLS_36;
    const __VLS_37 = {
        /** @type {typeof __VLS_36.'update:modelValue'} */
        'onUpdate:modelValue': (__VLS_unwrap(onToggleEnabled, {})),
    };
    void __VLS_37;
    var __VLS_34;
    var __VLS_35;
    // @ts-ignore
    [status, saving, onToggleEnabled,];
    let __VLS_38;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_39 = __VLS_asFunctionalComponent1(__VLS_38, new __VLS_38({
        // @ts-ignore
        cols: "12", md: "8",
    }));
    const __VLS_40 = __VLS_39({
        cols: "12",
        md: "8",
    }, ...__VLS_functionalComponentArgsRest(__VLS_39));
    var __VLS_41;
    const { default: __VLS_43 } = __VLS_nonNull(__VLS_41.slots);
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "d-flex flex-wrap ga-2" },
    });
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['flex-wrap']} */ ;
    /** @type {__VLS_StyleScopedClasses['ga-2']} */ ;
    let __VLS_44;
    /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
    vChip;
    // @ts-ignore
    const __VLS_45 = __VLS_asFunctionalComponent1(__VLS_44, new __VLS_44({
        // @ts-ignore
        size: "small", variant: "tonal", prependIcon: "mdi-timer-sand",
    }));
    const __VLS_46 = __VLS_45({
        size: "small",
        variant: "tonal",
        prependIcon: "mdi-timer-sand",
    }, ...__VLS_functionalComponentArgsRest(__VLS_45));
    var __VLS_47;
    const { default: __VLS_49 } = __VLS_nonNull(__VLS_47.slots);
    (status.value.timeframe ?? '—');
    // @ts-ignore
    [status,];
    let __VLS_50;
    /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
    vChip;
    // @ts-ignore
    const __VLS_51 = __VLS_asFunctionalComponent1(__VLS_50, new __VLS_50({
        // @ts-ignore
        size: "small", variant: "tonal", prependIcon: "mdi-account-multiple-check",
    }));
    const __VLS_52 = __VLS_51({
        size: "small",
        variant: "tonal",
        prependIcon: "mdi-account-multiple-check",
    }, ...__VLS_functionalComponentArgsRest(__VLS_51));
    var __VLS_53;
    const { default: __VLS_55 } = __VLS_nonNull(__VLS_53.slots);
    (status.value.positions.length);
    // @ts-ignore
    [status,];
    let __VLS_56;
    /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
    vChip;
    // @ts-ignore
    const __VLS_57 = __VLS_asFunctionalComponent1(__VLS_56, new __VLS_56({
        // @ts-ignore
        size: "small", variant: "tonal", prependIcon: "mdi-api", color: (status.value.api.error_count > 0 ? 'warning' : 'default'),
    }));
    const __VLS_58 = __VLS_57({
        size: "small",
        variant: "tonal",
        prependIcon: "mdi-api",
        color: (status.value.api.error_count > 0 ? 'warning' : 'default'),
    }, ...__VLS_functionalComponentArgsRest(__VLS_57));
    var __VLS_59;
    const { default: __VLS_61 } = __VLS_nonNull(__VLS_59.slots);
    (status.value.api.request_count);
    (status.value.api.error_count);
    // @ts-ignore
    [status, status, status,];
    let __VLS_62;
    /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
    vChip;
    // @ts-ignore
    const __VLS_63 = __VLS_asFunctionalComponent1(__VLS_62, new __VLS_62({
        // @ts-ignore
        size: "small", variant: "tonal", prependIcon: "mdi-flash-alert", color: (status.value.api.circuit_open ? 'error' : 'default'),
    }));
    const __VLS_64 = __VLS_63({
        size: "small",
        variant: "tonal",
        prependIcon: "mdi-flash-alert",
        color: (status.value.api.circuit_open ? 'error' : 'default'),
    }, ...__VLS_functionalComponentArgsRest(__VLS_63));
    var __VLS_65;
    const { default: __VLS_67 } = __VLS_nonNull(__VLS_65.slots);
    (status.value.api.circuit_open ? '接口限流熔断中' : '接口正常');
    // @ts-ignore
    [status, status,];
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    let __VLS_68;
    /** @ts-ignore @type { | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert'] | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert']} */
    vAlert;
    // @ts-ignore
    const __VLS_69 = __VLS_asFunctionalComponent1(__VLS_68, new __VLS_68({
        // @ts-ignore
        type: "info", variant: "tonal", density: "compact", ...{ class: "mt-3 text-caption" },
    }));
    const __VLS_70 = __VLS_69({
        type: "info",
        variant: "tonal",
        density: "compact",
        ...{ class: "mt-3 text-caption" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_69));
    /** @type {__VLS_StyleScopedClasses['mt-3']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
    var __VLS_71;
    const { default: __VLS_73 } = __VLS_nonNull(__VLS_71.slots);
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    const __VLS_74 = PageCard || PageCard;
    // @ts-ignore
    const __VLS_75 = __VLS_asFunctionalComponent1(__VLS_74, new __VLS_74({
        // @ts-ignore
        icon: "mdi-tune", title: "核心参数", spaced: true,
    }));
    const __VLS_76 = __VLS_75({
        icon: "mdi-tune",
        title: "核心参数",
        spaced: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_75));
    var __VLS_77;
    const { default: __VLS_79 } = __VLS_nonNull(__VLS_77.slots);
    {
        const { badges: __VLS_80 } = __VLS_nonNull(__VLS_77.slots);
        let __VLS_81;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_82 = __VLS_asFunctionalComponent1(__VLS_81, new __VLS_81({
            // @ts-ignore
            ...{ 'onClick': {} }, size: "small", color: "primary", variant: "tonal", prependIcon: "mdi-content-save", loading: (__VLS_unwrap(saving, {})),
        }));
        const __VLS_83 = __VLS_82({
            ...{ 'onClick': {} },
            size: "small",
            color: "primary",
            variant: "tonal",
            prependIcon: "mdi-content-save",
            loading: (__VLS_unwrap(saving, {})),
        }, ...__VLS_functionalComponentArgsRest(__VLS_82));
        let __VLS_86;
        const __VLS_87 = {
            /** @type {typeof __VLS_86.click} */
            onClick: (__VLS_unwrap(saveConfig, {})),
        };
        void __VLS_87;
        var __VLS_84;
        var __VLS_85;
        const { default: __VLS_88 } = __VLS_nonNull(__VLS_84.slots);
        // @ts-ignore
        [saving, saveConfig,];
        // @ts-ignore
        [];
    }
    let __VLS_89;
    /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
    vRow;
    // @ts-ignore
    const __VLS_90 = __VLS_asFunctionalComponent1(__VLS_89, new __VLS_89({
        // @ts-ignore
        dense: true,
    }));
    const __VLS_91 = __VLS_90({
        dense: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_90));
    var __VLS_92;
    const { default: __VLS_94 } = __VLS_nonNull(__VLS_92.slots);
    let __VLS_95;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_96 = __VLS_asFunctionalComponent1(__VLS_95, new __VLS_95({
        // @ts-ignore
        cols: "12", sm: "6", md: "3",
    }));
    const __VLS_97 = __VLS_96({
        cols: "12",
        sm: "6",
        md: "3",
    }, ...__VLS_functionalComponentArgsRest(__VLS_96));
    var __VLS_98;
    const { default: __VLS_100 } = __VLS_nonNull(__VLS_98.slots);
    const __VLS_101 = SmartSelect || SmartSelect;
    // @ts-ignore
    const __VLS_102 = __VLS_asFunctionalComponent1(__VLS_101, new __VLS_101({
        // @ts-ignore
        modelValue: (form.value.timeframe), items: (__VLS_unwrap(timeframes, {})), label: "结构判定周期",
    }));
    const __VLS_103 = __VLS_102({
        modelValue: (form.value.timeframe),
        items: (__VLS_unwrap(timeframes, {})),
        label: "结构判定周期",
    }, ...__VLS_functionalComponentArgsRest(__VLS_102));
    // @ts-ignore
    [form, timeframes,];
    let __VLS_106;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_107 = __VLS_asFunctionalComponent1(__VLS_106, new __VLS_106({
        // @ts-ignore
        cols: "12", sm: "6", md: "3",
    }));
    const __VLS_108 = __VLS_107({
        cols: "12",
        sm: "6",
        md: "3",
    }, ...__VLS_functionalComponentArgsRest(__VLS_107));
    var __VLS_109;
    const { default: __VLS_111 } = __VLS_nonNull(__VLS_109.slots);
    let __VLS_112;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_113 = __VLS_asFunctionalComponent1(__VLS_112, new __VLS_112({
        // @ts-ignore
        modelValue: (form.value.tp1_r_multiple), modelModifiers: { number: true, }, type: "number", step: "0.1", min: "0.1", label: "TP1 (R 倍数)", density: "compact", variant: "outlined", hideDetails: true,
    }));
    const __VLS_114 = __VLS_113({
        modelValue: (form.value.tp1_r_multiple),
        modelModifiers: { number: true, },
        type: "number",
        step: "0.1",
        min: "0.1",
        label: "TP1 (R 倍数)",
        density: "compact",
        variant: "outlined",
        hideDetails: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_113));
    // @ts-ignore
    [form,];
    let __VLS_117;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_118 = __VLS_asFunctionalComponent1(__VLS_117, new __VLS_117({
        // @ts-ignore
        cols: "12", sm: "6", md: "3",
    }));
    const __VLS_119 = __VLS_118({
        cols: "12",
        sm: "6",
        md: "3",
    }, ...__VLS_functionalComponentArgsRest(__VLS_118));
    var __VLS_120;
    const { default: __VLS_122 } = __VLS_nonNull(__VLS_120.slots);
    let __VLS_123;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_124 = __VLS_asFunctionalComponent1(__VLS_123, new __VLS_123({
        // @ts-ignore
        modelValue: (form.value.tp2_r_multiple), modelModifiers: { number: true, }, type: "number", step: "0.1", min: "0.1", label: "TP2 (R 倍数)", density: "compact", variant: "outlined", hideDetails: true,
    }));
    const __VLS_125 = __VLS_124({
        modelValue: (form.value.tp2_r_multiple),
        modelModifiers: { number: true, },
        type: "number",
        step: "0.1",
        min: "0.1",
        label: "TP2 (R 倍数)",
        density: "compact",
        variant: "outlined",
        hideDetails: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_124));
    // @ts-ignore
    [form,];
    let __VLS_128;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_129 = __VLS_asFunctionalComponent1(__VLS_128, new __VLS_128({
        // @ts-ignore
        cols: "12", sm: "6", md: "3",
    }));
    const __VLS_130 = __VLS_129({
        cols: "12",
        sm: "6",
        md: "3",
    }, ...__VLS_functionalComponentArgsRest(__VLS_129));
    var __VLS_131;
    const { default: __VLS_133 } = __VLS_nonNull(__VLS_131.slots);
    let __VLS_134;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_135 = __VLS_asFunctionalComponent1(__VLS_134, new __VLS_134({
        // @ts-ignore
        modelValue: (form.value.tp3_r_multiple), modelModifiers: { number: true, }, type: "number", step: "0.1", min: "0.1", label: "躺平 (R 倍数)", density: "compact", variant: "outlined", hideDetails: true,
    }));
    const __VLS_136 = __VLS_135({
        modelValue: (form.value.tp3_r_multiple),
        modelModifiers: { number: true, },
        type: "number",
        step: "0.1",
        min: "0.1",
        label: "躺平 (R 倍数)",
        density: "compact",
        variant: "outlined",
        hideDetails: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_135));
    // @ts-ignore
    [form,];
    let __VLS_139;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_140 = __VLS_asFunctionalComponent1(__VLS_139, new __VLS_139({
        // @ts-ignore
        cols: "12", sm: "6", md: "3",
    }));
    const __VLS_141 = __VLS_140({
        cols: "12",
        sm: "6",
        md: "3",
    }, ...__VLS_functionalComponentArgsRest(__VLS_140));
    var __VLS_142;
    const { default: __VLS_144 } = __VLS_nonNull(__VLS_142.slots);
    let __VLS_145;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_146 = __VLS_asFunctionalComponent1(__VLS_145, new __VLS_145({
        // @ts-ignore
        modelValue: (form.value.t1_structure_lookback), modelModifiers: { number: true, }, type: "number", min: "2", label: "T1 结构回看(根)", density: "compact", variant: "outlined", hideDetails: true,
    }));
    const __VLS_147 = __VLS_146({
        modelValue: (form.value.t1_structure_lookback),
        modelModifiers: { number: true, },
        type: "number",
        min: "2",
        label: "T1 结构回看(根)",
        density: "compact",
        variant: "outlined",
        hideDetails: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_146));
    // @ts-ignore
    [form,];
    let __VLS_150;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_151 = __VLS_asFunctionalComponent1(__VLS_150, new __VLS_150({
        // @ts-ignore
        cols: "12", sm: "6", md: "3",
    }));
    const __VLS_152 = __VLS_151({
        cols: "12",
        sm: "6",
        md: "3",
    }, ...__VLS_functionalComponentArgsRest(__VLS_151));
    var __VLS_153;
    const { default: __VLS_155 } = __VLS_nonNull(__VLS_153.slots);
    let __VLS_156;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_157 = __VLS_asFunctionalComponent1(__VLS_156, new __VLS_156({
        // @ts-ignore
        modelValue: (form.value.t2_structure_lookback), modelModifiers: { number: true, }, type: "number", min: "2", label: "T2 结构回看(根)", density: "compact", variant: "outlined", hideDetails: true,
    }));
    const __VLS_158 = __VLS_157({
        modelValue: (form.value.t2_structure_lookback),
        modelModifiers: { number: true, },
        type: "number",
        min: "2",
        label: "T2 结构回看(根)",
        density: "compact",
        variant: "outlined",
        hideDetails: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_157));
    // @ts-ignore
    [form,];
    let __VLS_161;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_162 = __VLS_asFunctionalComponent1(__VLS_161, new __VLS_161({
        // @ts-ignore
        cols: "12", sm: "6", md: "3",
    }));
    const __VLS_163 = __VLS_162({
        cols: "12",
        sm: "6",
        md: "3",
    }, ...__VLS_functionalComponentArgsRest(__VLS_162));
    var __VLS_164;
    const { default: __VLS_166 } = __VLS_nonNull(__VLS_164.slots);
    let __VLS_167;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_168 = __VLS_asFunctionalComponent1(__VLS_167, new __VLS_167({
        // @ts-ignore
        modelValue: (form.value.t3_structure_lookback), modelModifiers: { number: true, }, type: "number", min: "2", label: "T3 结构回看(根)", density: "compact", variant: "outlined", hideDetails: true,
    }));
    const __VLS_169 = __VLS_168({
        modelValue: (form.value.t3_structure_lookback),
        modelModifiers: { number: true, },
        type: "number",
        min: "2",
        label: "T3 结构回看(根)",
        density: "compact",
        variant: "outlined",
        hideDetails: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_168));
    // @ts-ignore
    [form,];
    let __VLS_172;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_173 = __VLS_asFunctionalComponent1(__VLS_172, new __VLS_172({
        // @ts-ignore
        cols: "12", sm: "6", md: "3",
    }));
    const __VLS_174 = __VLS_173({
        cols: "12",
        sm: "6",
        md: "3",
    }, ...__VLS_functionalComponentArgsRest(__VLS_173));
    var __VLS_175;
    const { default: __VLS_177 } = __VLS_nonNull(__VLS_175.slots);
    let __VLS_178;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_179 = __VLS_asFunctionalComponent1(__VLS_178, new __VLS_178({
        // @ts-ignore
        modelValue: (form.value.structure_buffer_atr), modelModifiers: { number: true, }, type: "number", step: "0.1", min: "0", label: "结构缓冲 (ATR)", density: "compact", variant: "outlined", hideDetails: true,
    }));
    const __VLS_180 = __VLS_179({
        modelValue: (form.value.structure_buffer_atr),
        modelModifiers: { number: true, },
        type: "number",
        step: "0.1",
        min: "0",
        label: "结构缓冲 (ATR)",
        density: "compact",
        variant: "outlined",
        hideDetails: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_179));
    // @ts-ignore
    [form,];
    // @ts-ignore
    [];
    let __VLS_183;
    /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
    vRow;
    // @ts-ignore
    const __VLS_184 = __VLS_asFunctionalComponent1(__VLS_183, new __VLS_183({
        // @ts-ignore
        dense: true, ...{ class: "mt-2" },
    }));
    const __VLS_185 = __VLS_184({
        dense: true,
        ...{ class: "mt-2" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_184));
    /** @type {__VLS_StyleScopedClasses['mt-2']} */ ;
    var __VLS_186;
    const { default: __VLS_188 } = __VLS_nonNull(__VLS_186.slots);
    let __VLS_189;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_190 = __VLS_asFunctionalComponent1(__VLS_189, new __VLS_189({
        // @ts-ignore
        cols: "12", sm: "6", md: "3",
    }));
    const __VLS_191 = __VLS_190({
        cols: "12",
        sm: "6",
        md: "3",
    }, ...__VLS_functionalComponentArgsRest(__VLS_190));
    var __VLS_192;
    const { default: __VLS_194 } = __VLS_nonNull(__VLS_192.slots);
    let __VLS_195;
    /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch'] | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
    vSwitch;
    // @ts-ignore
    const __VLS_196 = __VLS_asFunctionalComponent1(__VLS_195, new __VLS_195({
        // @ts-ignore
        modelValue: (form.value.profit_protection_enabled), label: "浮盈保护（上移止损）", color: "primary", density: "compact", inset: true, hideDetails: true,
    }));
    const __VLS_197 = __VLS_196({
        modelValue: (form.value.profit_protection_enabled),
        label: "浮盈保护（上移止损）",
        color: "primary",
        density: "compact",
        inset: true,
        hideDetails: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_196));
    // @ts-ignore
    [form,];
    let __VLS_200;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_201 = __VLS_asFunctionalComponent1(__VLS_200, new __VLS_200({
        // @ts-ignore
        cols: "12", sm: "6", md: "3",
    }));
    const __VLS_202 = __VLS_201({
        cols: "12",
        sm: "6",
        md: "3",
    }, ...__VLS_functionalComponentArgsRest(__VLS_201));
    var __VLS_203;
    const { default: __VLS_205 } = __VLS_nonNull(__VLS_203.slots);
    let __VLS_206;
    /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch'] | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
    vSwitch;
    // @ts-ignore
    const __VLS_207 = __VLS_asFunctionalComponent1(__VLS_206, new __VLS_206({
        // @ts-ignore
        modelValue: (form.value.emergency_enabled), label: "紧急结构止损", color: "primary", density: "compact", inset: true, hideDetails: true,
    }));
    const __VLS_208 = __VLS_207({
        modelValue: (form.value.emergency_enabled),
        label: "紧急结构止损",
        color: "primary",
        density: "compact",
        inset: true,
        hideDetails: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_207));
    // @ts-ignore
    [form,];
    let __VLS_211;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_212 = __VLS_asFunctionalComponent1(__VLS_211, new __VLS_211({
        // @ts-ignore
        cols: "12", sm: "6", md: "3",
    }));
    const __VLS_213 = __VLS_212({
        cols: "12",
        sm: "6",
        md: "3",
    }, ...__VLS_functionalComponentArgsRest(__VLS_212));
    var __VLS_214;
    const { default: __VLS_216 } = __VLS_nonNull(__VLS_214.slots);
    let __VLS_217;
    /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch'] | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
    vSwitch;
    // @ts-ignore
    const __VLS_218 = __VLS_asFunctionalComponent1(__VLS_217, new __VLS_217({
        // @ts-ignore
        modelValue: (form.value.exchange_hard_stop_enabled), label: "交易所灾难止损单", color: "primary", density: "compact", inset: true, hideDetails: true,
    }));
    const __VLS_219 = __VLS_218({
        modelValue: (form.value.exchange_hard_stop_enabled),
        label: "交易所灾难止损单",
        color: "primary",
        density: "compact",
        inset: true,
        hideDetails: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_218));
    // @ts-ignore
    [form,];
    let __VLS_222;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_223 = __VLS_asFunctionalComponent1(__VLS_222, new __VLS_222({
        // @ts-ignore
        cols: "12", sm: "6", md: "3",
    }));
    const __VLS_224 = __VLS_223({
        cols: "12",
        sm: "6",
        md: "3",
    }, ...__VLS_functionalComponentArgsRest(__VLS_223));
    var __VLS_225;
    const { default: __VLS_227 } = __VLS_nonNull(__VLS_225.slots);
    let __VLS_228;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_229 = __VLS_asFunctionalComponent1(__VLS_228, new __VLS_228({
        // @ts-ignore
        modelValue: (form.value.hard_stop_min_distance_pct), modelModifiers: { number: true, }, type: "number", step: "0.01", min: "0", max: "1", label: "灾难止损最小距离 (比例)", density: "compact", variant: "outlined", hideDetails: true,
    }));
    const __VLS_230 = __VLS_229({
        modelValue: (form.value.hard_stop_min_distance_pct),
        modelModifiers: { number: true, },
        type: "number",
        step: "0.01",
        min: "0",
        max: "1",
        label: "灾难止损最小距离 (比例)",
        density: "compact",
        variant: "outlined",
        hideDetails: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_229));
    // @ts-ignore
    [form,];
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    const __VLS_233 = PageCard || PageCard;
    // @ts-ignore
    const __VLS_234 = __VLS_asFunctionalComponent1(__VLS_233, new __VLS_233({
        // @ts-ignore
        icon: "mdi-shield-account", title: "守卫中的仓位", spaced: true,
    }));
    const __VLS_235 = __VLS_234({
        icon: "mdi-shield-account",
        title: "守卫中的仓位",
        spaced: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_234));
    var __VLS_236;
    const { default: __VLS_238 } = __VLS_nonNull(__VLS_236.slots);
    {
        const { badges: __VLS_239 } = __VLS_nonNull(__VLS_236.slots);
        let __VLS_240;
        /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
        vChip;
        // @ts-ignore
        const __VLS_241 = __VLS_asFunctionalComponent1(__VLS_240, new __VLS_240({
            // @ts-ignore
            size: "small", variant: "tonal",
        }));
        const __VLS_242 = __VLS_241({
            size: "small",
            variant: "tonal",
        }, ...__VLS_functionalComponentArgsRest(__VLS_241));
        var __VLS_243;
        const { default: __VLS_245 } = __VLS_nonNull(__VLS_243.slots);
        (status.value.positions.length);
        // @ts-ignore
        [status,];
        let __VLS_246;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_247 = __VLS_asFunctionalComponent1(__VLS_246, new __VLS_246({
            // @ts-ignore
            ...{ 'onClick': {} }, size: "small", variant: "text", prependIcon: "mdi-refresh",
        }));
        const __VLS_248 = __VLS_247({
            ...{ 'onClick': {} },
            size: "small",
            variant: "text",
            prependIcon: "mdi-refresh",
        }, ...__VLS_functionalComponentArgsRest(__VLS_247));
        let __VLS_251;
        const __VLS_252 = {
            /** @type {typeof __VLS_251.click} */
            onClick: (__VLS_unwrap(fetchStatus, {})),
        };
        void __VLS_252;
        var __VLS_249;
        var __VLS_250;
        const { default: __VLS_253 } = __VLS_nonNull(__VLS_249.slots);
        // @ts-ignore
        [fetchStatus,];
        // @ts-ignore
        [];
    }
    if (!status.value.enabled) {
        let __VLS_254;
        /** @ts-ignore @type { | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert'] | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert']} */
        vAlert;
        // @ts-ignore
        const __VLS_255 = __VLS_asFunctionalComponent1(__VLS_254, new __VLS_254({
            // @ts-ignore
            type: "warning", variant: "tonal", density: "compact", ...{ class: "text-caption" },
        }));
        const __VLS_256 = __VLS_255({
            type: "warning",
            variant: "tonal",
            density: "compact",
            ...{ class: "text-caption" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_255));
        /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
        var __VLS_257;
        const { default: __VLS_259 } = __VLS_nonNull(__VLS_257.slots);
        // @ts-ignore
        [status,];
    }
    else if (status.value.positions.length > 0) {
        let __VLS_260;
        /** @ts-ignore @type { | typeof __VLS_components.vTable | typeof __VLS_components.VTable | typeof __VLS_components['v-table'] | typeof __VLS_components.vTable | typeof __VLS_components.VTable | typeof __VLS_components['v-table']} */
        vTable;
        // @ts-ignore
        const __VLS_261 = __VLS_asFunctionalComponent1(__VLS_260, new __VLS_260({
            // @ts-ignore
            density: "compact",
        }));
        const __VLS_262 = __VLS_261({
            density: "compact",
        }, ...__VLS_functionalComponentArgsRest(__VLS_261));
        var __VLS_263;
        const { default: __VLS_265 } = __VLS_nonNull(__VLS_263.slots);
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
            ...{ class: "text-right" },
        });
        /** @type {__VLS_StyleScopedClasses['text-right']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-right" },
        });
        /** @type {__VLS_StyleScopedClasses['text-right']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-right" },
        });
        /** @type {__VLS_StyleScopedClasses['text-right']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-right" },
        });
        /** @type {__VLS_StyleScopedClasses['text-right']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-right" },
        });
        /** @type {__VLS_StyleScopedClasses['text-right']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
            ...{ class: "text-left" },
        });
        /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.tbody, __VLS_intrinsics.tbody)({});
        const __VLS_266 = __VLS_tryAsConstant((status.value.positions));
        for (const [row] of __VLS_vFor(__VLS_nonNull(__VLS_266))) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.tr, __VLS_intrinsics.tr)({
                key: (`${row.symbol}-${row.side}`),
            });
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                ...{ class: "font-weight-medium" },
            });
            /** @type {__VLS_StyleScopedClasses['font-weight-medium']} */ ;
            (row.symbol);
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({});
            let __VLS_267;
            /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
            vChip;
            // @ts-ignore
            const __VLS_268 = __VLS_asFunctionalComponent1(__VLS_267, new __VLS_267({
                // @ts-ignore
                size: "x-small", variant: "tonal", color: (row.side === 'long' ? 'success' : 'error'),
            }));
            const __VLS_269 = __VLS_268({
                size: "x-small",
                variant: "tonal",
                color: (row.side === 'long' ? 'success' : 'error'),
            }, ...__VLS_functionalComponentArgsRest(__VLS_268));
            var __VLS_270;
            const { default: __VLS_272 } = __VLS_nonNull(__VLS_270.slots);
            (row.side === 'long' ? '多' : '空');
            // @ts-ignore
            [status, status,];
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                ...{ class: "text-right" },
            });
            /** @type {__VLS_StyleScopedClasses['text-right']} */ ;
            (__VLS_unwrap(formatNumber, {})(row.contracts, 4));
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                ...{ class: "text-right" },
            });
            /** @type {__VLS_StyleScopedClasses['text-right']} */ ;
            (__VLS_unwrap(formatNumber, {})(row.entry_price));
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                ...{ class: "text-right" },
            });
            /** @type {__VLS_StyleScopedClasses['text-right']} */ ;
            (__VLS_unwrap(formatNumber, {})(row.mark_price));
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                ...{ class: "text-right" },
            });
            /** @type {__VLS_StyleScopedClasses['text-right']} */ ;
            if (row.protected_stop) {
                __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
                (__VLS_unwrap(formatNumber, {})(row.protected_stop));
            }
            else if (row.stop_price) {
                __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
                (__VLS_unwrap(formatNumber, {})(row.stop_price));
            }
            else {
                __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
                    ...{ class: "text-grey" },
                });
                /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
            }
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                ...{ class: "text-right text-caption" },
            });
            /** @type {__VLS_StyleScopedClasses['text-right']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
            (__VLS_unwrap(formatNumber, {})(row.tp1_price));
            (__VLS_unwrap(formatNumber, {})(row.tp2_price));
            (__VLS_unwrap(formatNumber, {})(row.tp3_price));
            __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({});
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                ...{ class: "d-flex flex-wrap ga-1" },
            });
            /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
            /** @type {__VLS_StyleScopedClasses['flex-wrap']} */ ;
            /** @type {__VLS_StyleScopedClasses['ga-1']} */ ;
            if (row.tp1_done) {
                let __VLS_273;
                /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
                vChip;
                // @ts-ignore
                const __VLS_274 = __VLS_asFunctionalComponent1(__VLS_273, new __VLS_273({
                    // @ts-ignore
                    size: "x-small", variant: "tonal", color: "info",
                }));
                const __VLS_275 = __VLS_274({
                    size: "x-small",
                    variant: "tonal",
                    color: "info",
                }, ...__VLS_functionalComponentArgsRest(__VLS_274));
                var __VLS_276;
                const { default: __VLS_278 } = __VLS_nonNull(__VLS_276.slots);
                // @ts-ignore
                [formatNumber, formatNumber, formatNumber, formatNumber, formatNumber, formatNumber, formatNumber, formatNumber,];
            }
            if (row.tp2_done) {
                let __VLS_279;
                /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
                vChip;
                // @ts-ignore
                const __VLS_280 = __VLS_asFunctionalComponent1(__VLS_279, new __VLS_279({
                    // @ts-ignore
                    size: "x-small", variant: "tonal", color: "info",
                }));
                const __VLS_281 = __VLS_280({
                    size: "x-small",
                    variant: "tonal",
                    color: "info",
                }, ...__VLS_functionalComponentArgsRest(__VLS_280));
                var __VLS_282;
                const { default: __VLS_284 } = __VLS_nonNull(__VLS_282.slots);
                // @ts-ignore
                [];
            }
            if (row.tp3_done) {
                let __VLS_285;
                /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
                vChip;
                // @ts-ignore
                const __VLS_286 = __VLS_asFunctionalComponent1(__VLS_285, new __VLS_285({
                    // @ts-ignore
                    size: "x-small", variant: "tonal", color: "info",
                }));
                const __VLS_287 = __VLS_286({
                    size: "x-small",
                    variant: "tonal",
                    color: "info",
                }, ...__VLS_functionalComponentArgsRest(__VLS_286));
                var __VLS_288;
                const { default: __VLS_290 } = __VLS_nonNull(__VLS_288.slots);
                // @ts-ignore
                [];
            }
            if (row.t1_done) {
                let __VLS_291;
                /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
                vChip;
                // @ts-ignore
                const __VLS_292 = __VLS_asFunctionalComponent1(__VLS_291, new __VLS_291({
                    // @ts-ignore
                    size: "x-small", variant: "tonal", color: "warning",
                }));
                const __VLS_293 = __VLS_292({
                    size: "x-small",
                    variant: "tonal",
                    color: "warning",
                }, ...__VLS_functionalComponentArgsRest(__VLS_292));
                var __VLS_294;
                const { default: __VLS_296 } = __VLS_nonNull(__VLS_294.slots);
                // @ts-ignore
                [];
            }
            if (row.t2_done) {
                let __VLS_297;
                /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
                vChip;
                // @ts-ignore
                const __VLS_298 = __VLS_asFunctionalComponent1(__VLS_297, new __VLS_297({
                    // @ts-ignore
                    size: "x-small", variant: "tonal", color: "warning",
                }));
                const __VLS_299 = __VLS_298({
                    size: "x-small",
                    variant: "tonal",
                    color: "warning",
                }, ...__VLS_functionalComponentArgsRest(__VLS_298));
                var __VLS_300;
                const { default: __VLS_302 } = __VLS_nonNull(__VLS_300.slots);
                // @ts-ignore
                [];
            }
            if (row.t3_done) {
                let __VLS_303;
                /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
                vChip;
                // @ts-ignore
                const __VLS_304 = __VLS_asFunctionalComponent1(__VLS_303, new __VLS_303({
                    // @ts-ignore
                    size: "x-small", variant: "tonal", color: "warning",
                }));
                const __VLS_305 = __VLS_304({
                    size: "x-small",
                    variant: "tonal",
                    color: "warning",
                }, ...__VLS_functionalComponentArgsRest(__VLS_304));
                var __VLS_306;
                const { default: __VLS_308 } = __VLS_nonNull(__VLS_306.slots);
                // @ts-ignore
                [];
            }
            if (!__VLS_unwrap(hasTriggered, {})(row)) {
                __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
                    ...{ class: "text-caption text-grey" },
                });
                /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
                /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
            }
            // @ts-ignore
            [hasTriggered,];
        }
        // @ts-ignore
        [];
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
    return {};
};
void [__VLS_template];
const __VLS_export = (await import('vue')).defineComponent({});
export default {};
