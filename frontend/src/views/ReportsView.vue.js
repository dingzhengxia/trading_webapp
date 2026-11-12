import { computed, onMounted, onUnmounted, ref } from 'vue';
import api from '@/services/api';
import { useSnackbarStore } from '@/stores/snackbar';
import { getErrorMessage } from '@/utils/errors';
import { formatUnixSeconds as formatTime } from '@/utils/format';
import SmartSelect from '@/components/SmartSelect.vue';
const snackbarStore = useSnackbarStore();
const intervalOptions = [
    { title: '每小时', value: '1h' },
    { title: '每 2 小时', value: '2h' },
    { title: '每 4 小时', value: '4h' },
    { title: '每 6 小时', value: '6h' },
    { title: '每 12 小时', value: '12h' },
    { title: '每天', value: '1d' },
];
const status = ref({
    reports: [],
    dingtalk_configured: false,
    dingtalk_enabled: false,
    running: false,
    latest: {},
});
const reports = ref([]);
const dingtalkEnabled = ref(false);
const saving = ref(false);
const selectedReport = ref('');
let pollTimer;
let initialised = false;
const enabledCount = computed(() => reports.value.filter((item) => item.enabled).length);
const latestNames = computed(() => Object.keys(status.value.latest));
const currentLatest = computed(() => {
    if (!selectedReport.value)
        return undefined;
    return status.value.latest[selectedReport.value];
});
const toConfig = (row) => ({
    report_name: row.report_name,
    enabled: row.enabled,
    run_interval: row.run_interval,
    top_n_by_volume: Number(row.top_n_by_volume),
    top_n_gainers: Number(row.top_n_gainers),
    top_n_volume_ratio: Number(row.top_n_volume_ratio),
    min_consecutive_candles: Number(row.min_consecutive_candles),
    volume_ma_period: Number(row.volume_ma_period),
    market_sentiment: {
        enabled: row.market_sentiment?.enabled !== false,
        rsi_period: row.market_sentiment?.rsi_period ?? 14,
        rsi_overbought: row.market_sentiment?.rsi_overbought ?? 70,
        rsi_oversold: row.market_sentiment?.rsi_oversold ?? 30,
    },
});
const applyStatus = (data, overwriteForm = false) => {
    status.value = data;
    dingtalkEnabled.value = data.dingtalk_enabled;
    if (overwriteForm || !initialised) {
        reports.value = data.reports.map((row) => ({ ...row, market_sentiment: { ...row.market_sentiment } }));
        initialised = true;
    }
    else {
        // 轮询只同步运行态字段，避免覆盖用户正在编辑但未保存的值
        reports.value = reports.value.map((row) => {
            const fresh = data.reports.find((item) => item.report_name === row.report_name);
            return fresh
                ? { ...row, last_run: fresh.last_run, next_run: fresh.next_run, running: fresh.running, last_error: fresh.last_error, scanned: fresh.scanned, title: fresh.title }
                : row;
        });
    }
    if (!selectedReport.value && data.reports.length > 0) {
        selectedReport.value = data.reports[0].report_name;
    }
};
const fetchStatus = async (overwriteForm = false) => {
    try {
        const response = await api.get('/api/reports');
        applyStatus(response.data, overwriteForm);
    }
    catch (error) {
        console.warn('获取周期报告状态失败:', getErrorMessage(error));
    }
};
const saveConfig = async () => {
    saving.value = true;
    try {
        const response = await api.post('/api/reports/config', {
            reports: reports.value.map(toConfig),
            dingtalk_enabled: dingtalkEnabled.value,
        });
        // 保存成功后仍以后端返回为准，保证下次运行时间等信息同步
        initialised = false;
        applyStatus(response.data, true);
        snackbarStore.show({ message: '周期报告配置已保存。', color: 'success' });
    }
    catch (error) {
        snackbarStore.show({ message: getErrorMessage(error), color: 'error' });
    }
    finally {
        saving.value = false;
    }
};
const runNow = async (reportName) => {
    try {
        await api.post('/api/reports/run', { report_name: reportName });
        snackbarStore.show({ message: `已开始生成「${reportName}」，稍候刷新查看。`, color: 'info' });
        await fetchStatus();
    }
    catch (error) {
        snackbarStore.show({ message: getErrorMessage(error), color: 'error' });
    }
};
onMounted(async () => {
    await fetchStatus(true);
    pollTimer = window.setInterval(() => {
        void fetchStatus();
    }, 15000);
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
    __VLS_withDotValue(reports, {});
    __VLS_withDotValue(status, {});
    __VLS_withDotValue(selectedReport, {});
    __VLS_withDotValue(currentLatest, {});
    void {};
    /** @type {__VLS_StyleScopedClasses['reports-picker']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
    let __VLS_0;
    /** @ts-ignore @type { | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card'] | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card']} */
    vCard;
    // @ts-ignore
    const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
        // @ts-ignore
        ...{ class: "mb-4" },
    }));
    const __VLS_2 = __VLS_1({
        ...{ class: "mb-4" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_1));
    /** @type {__VLS_StyleScopedClasses['mb-4']} */ ;
    var __VLS_3;
    const { default: __VLS_5 } = __VLS_nonNull(__VLS_3.slots);
    let __VLS_6;
    /** @ts-ignore @type { | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title'] | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title']} */
    vCardTitle;
    // @ts-ignore
    const __VLS_7 = __VLS_asFunctionalComponent1(__VLS_6, new __VLS_6({
        // @ts-ignore
        ...{ class: "text-h6 d-flex align-center flex-wrap ga-2" },
    }));
    const __VLS_8 = __VLS_7({
        ...{ class: "text-h6 d-flex align-center flex-wrap ga-2" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_7));
    /** @type {__VLS_StyleScopedClasses['text-h6']} */ ;
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
    /** @type {__VLS_StyleScopedClasses['flex-wrap']} */ ;
    /** @type {__VLS_StyleScopedClasses['ga-2']} */ ;
    var __VLS_9;
    const { default: __VLS_11 } = __VLS_nonNull(__VLS_9.slots);
    let __VLS_12;
    /** @ts-ignore @type { | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon'] | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon']} */
    vIcon;
    // @ts-ignore
    const __VLS_13 = __VLS_asFunctionalComponent1(__VLS_12, new __VLS_12({
        // @ts-ignore
        start: true,
    }));
    const __VLS_14 = __VLS_13({
        start: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_13));
    var __VLS_15;
    const { default: __VLS_17 } = __VLS_nonNull(__VLS_15.slots);
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    let __VLS_18;
    /** @ts-ignore @type { | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer'] | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer']} */
    vSpacer;
    // @ts-ignore
    const __VLS_19 = __VLS_asFunctionalComponent1(__VLS_18, new __VLS_18({
    // @ts-ignore
    }));
    const __VLS_20 = __VLS_19({}, ...__VLS_functionalComponentArgsRest(__VLS_19));
    let __VLS_23;
    /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
    vChip;
    // @ts-ignore
    const __VLS_24 = __VLS_asFunctionalComponent1(__VLS_23, new __VLS_23({
        // @ts-ignore
        size: "small", variant: "tonal", color: (__VLS_unwrap(enabledCount, {}) > 0 ? 'success' : 'grey'),
    }));
    const __VLS_25 = __VLS_24({
        size: "small",
        variant: "tonal",
        color: (__VLS_unwrap(enabledCount, {}) > 0 ? 'success' : 'grey'),
    }, ...__VLS_functionalComponentArgsRest(__VLS_24));
    var __VLS_26;
    const { default: __VLS_28 } = __VLS_nonNull(__VLS_26.slots);
    (__VLS_unwrap(enabledCount, {}));
    (reports.value.length);
    // @ts-ignore
    [enabledCount, enabledCount, reports,];
    let __VLS_29;
    /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
    vChip;
    // @ts-ignore
    const __VLS_30 = __VLS_asFunctionalComponent1(__VLS_29, new __VLS_29({
        // @ts-ignore
        size: "small", variant: "tonal", color: (status.value.running ? 'info' : 'grey'),
    }));
    const __VLS_31 = __VLS_30({
        size: "small",
        variant: "tonal",
        color: (status.value.running ? 'info' : 'grey'),
    }, ...__VLS_functionalComponentArgsRest(__VLS_30));
    var __VLS_32;
    const { default: __VLS_34 } = __VLS_nonNull(__VLS_32.slots);
    (status.value.running ? '正在生成' : '空闲');
    // @ts-ignore
    [status, status,];
    let __VLS_35;
    /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
    vChip;
    // @ts-ignore
    const __VLS_36 = __VLS_asFunctionalComponent1(__VLS_35, new __VLS_35({
        // @ts-ignore
        size: "small", variant: "tonal", color: (status.value.dingtalk_configured ? 'success' : 'warning'), prependIcon: "mdi-bell-ring-outline",
    }));
    const __VLS_37 = __VLS_36({
        size: "small",
        variant: "tonal",
        color: (status.value.dingtalk_configured ? 'success' : 'warning'),
        prependIcon: "mdi-bell-ring-outline",
    }, ...__VLS_functionalComponentArgsRest(__VLS_36));
    var __VLS_38;
    const { default: __VLS_40 } = __VLS_nonNull(__VLS_38.slots);
    (status.value.dingtalk_configured ? '已配置' : '未配置');
    // @ts-ignore
    [status, status,];
    // @ts-ignore
    [];
    let __VLS_41;
    /** @ts-ignore @type { | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider'] | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider']} */
    vDivider;
    // @ts-ignore
    const __VLS_42 = __VLS_asFunctionalComponent1(__VLS_41, new __VLS_41({
    // @ts-ignore
    }));
    const __VLS_43 = __VLS_42({}, ...__VLS_functionalComponentArgsRest(__VLS_42));
    let __VLS_46;
    /** @ts-ignore @type { | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text'] | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text']} */
    vCardText;
    // @ts-ignore
    const __VLS_47 = __VLS_asFunctionalComponent1(__VLS_46, new __VLS_46({
    // @ts-ignore
    }));
    const __VLS_48 = __VLS_47({}, ...__VLS_functionalComponentArgsRest(__VLS_47));
    var __VLS_49;
    const { default: __VLS_51 } = __VLS_nonNull(__VLS_49.slots);
    let __VLS_52;
    /** @ts-ignore @type { | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert'] | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert']} */
    vAlert;
    // @ts-ignore
    const __VLS_53 = __VLS_asFunctionalComponent1(__VLS_52, new __VLS_52({
        // @ts-ignore
        type: "info", variant: "tonal", density: "compact", ...{ class: "mb-3" },
    }));
    const __VLS_54 = __VLS_53({
        type: "info",
        variant: "tonal",
        density: "compact",
        ...{ class: "mb-3" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_53));
    /** @type {__VLS_StyleScopedClasses['mb-3']} */ ;
    var __VLS_55;
    const { default: __VLS_57 } = __VLS_nonNull(__VLS_55.slots);
    __VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.code, __VLS_intrinsics.code)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.code, __VLS_intrinsics.code)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.code, __VLS_intrinsics.code)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.code, __VLS_intrinsics.code)({});
    // @ts-ignore
    [];
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "d-flex flex-wrap align-center ga-4" },
    });
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['flex-wrap']} */ ;
    /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
    /** @type {__VLS_StyleScopedClasses['ga-4']} */ ;
    let __VLS_58;
    /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch'] | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
    vSwitch;
    // @ts-ignore
    const __VLS_59 = __VLS_asFunctionalComponent1(__VLS_58, new __VLS_58({
        // @ts-ignore
        modelValue: (__VLS_unwrap(dingtalkEnabled, {})), label: "钉钉推送（报告 + 仓位保护告警）", color: "primary", inset: true, hideDetails: true, density: "compact", disabled: (!status.value.dingtalk_configured || __VLS_unwrap(saving, {})),
    }));
    const __VLS_60 = __VLS_59({
        modelValue: (__VLS_unwrap(dingtalkEnabled, {})),
        label: "钉钉推送（报告 + 仓位保护告警）",
        color: "primary",
        inset: true,
        hideDetails: true,
        density: "compact",
        disabled: (!status.value.dingtalk_configured || __VLS_unwrap(saving, {})),
    }, ...__VLS_functionalComponentArgsRest(__VLS_59));
    let __VLS_63;
    /** @ts-ignore @type { | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer'] | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer']} */
    vSpacer;
    // @ts-ignore
    const __VLS_64 = __VLS_asFunctionalComponent1(__VLS_63, new __VLS_63({
    // @ts-ignore
    }));
    const __VLS_65 = __VLS_64({}, ...__VLS_functionalComponentArgsRest(__VLS_64));
    let __VLS_68;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_69 = __VLS_asFunctionalComponent1(__VLS_68, new __VLS_68({
        // @ts-ignore
        ...{ 'onClick': {} }, color: "primary", variant: "tonal", prependIcon: "mdi-content-save", loading: (__VLS_unwrap(saving, {})),
    }));
    const __VLS_70 = __VLS_69({
        ...{ 'onClick': {} },
        color: "primary",
        variant: "tonal",
        prependIcon: "mdi-content-save",
        loading: (__VLS_unwrap(saving, {})),
    }, ...__VLS_functionalComponentArgsRest(__VLS_69));
    let __VLS_73;
    const __VLS_74 = {
        /** @type {typeof __VLS_73.click} */
        onClick: (__VLS_unwrap(saveConfig, {})),
    };
    void __VLS_74;
    var __VLS_71;
    var __VLS_72;
    const { default: __VLS_75 } = __VLS_nonNull(__VLS_71.slots);
    // @ts-ignore
    [status, dingtalkEnabled, saving, saving, saveConfig,];
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    let __VLS_76;
    /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
    vRow;
    // @ts-ignore
    const __VLS_77 = __VLS_asFunctionalComponent1(__VLS_76, new __VLS_76({
    // @ts-ignore
    }));
    const __VLS_78 = __VLS_77({}, ...__VLS_functionalComponentArgsRest(__VLS_77));
    var __VLS_79;
    const { default: __VLS_81 } = __VLS_nonNull(__VLS_79.slots);
    const __VLS_82 = __VLS_tryAsConstant((reports.value));
    for (const [report] of __VLS_vFor(__VLS_nonNull(__VLS_82))) {
        let __VLS_83;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_84 = __VLS_asFunctionalComponent1(__VLS_83, new __VLS_83({
            // @ts-ignore
            key: (report.report_name), cols: "12", lg: "6",
        }));
        const __VLS_85 = __VLS_84({
            key: (report.report_name),
            cols: "12",
            lg: "6",
        }, ...__VLS_functionalComponentArgsRest(__VLS_84));
        var __VLS_86;
        const { default: __VLS_88 } = __VLS_nonNull(__VLS_86.slots);
        let __VLS_89;
        /** @ts-ignore @type { | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card'] | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card']} */
        vCard;
        // @ts-ignore
        const __VLS_90 = __VLS_asFunctionalComponent1(__VLS_89, new __VLS_89({
            // @ts-ignore
            height: "100%",
        }));
        const __VLS_91 = __VLS_90({
            height: "100%",
        }, ...__VLS_functionalComponentArgsRest(__VLS_90));
        var __VLS_92;
        const { default: __VLS_94 } = __VLS_nonNull(__VLS_92.slots);
        let __VLS_95;
        /** @ts-ignore @type { | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title'] | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title']} */
        vCardTitle;
        // @ts-ignore
        const __VLS_96 = __VLS_asFunctionalComponent1(__VLS_95, new __VLS_95({
            // @ts-ignore
            ...{ class: "text-subtitle-1 d-flex align-center flex-wrap ga-2" },
        }));
        const __VLS_97 = __VLS_96({
            ...{ class: "text-subtitle-1 d-flex align-center flex-wrap ga-2" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_96));
        /** @type {__VLS_StyleScopedClasses['text-subtitle-1']} */ ;
        /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
        /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
        /** @type {__VLS_StyleScopedClasses['flex-wrap']} */ ;
        /** @type {__VLS_StyleScopedClasses['ga-2']} */ ;
        var __VLS_98;
        const { default: __VLS_100 } = __VLS_nonNull(__VLS_98.slots);
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
        (report.report_name);
        if (report.running) {
            let __VLS_101;
            /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
            vChip;
            // @ts-ignore
            const __VLS_102 = __VLS_asFunctionalComponent1(__VLS_101, new __VLS_101({
                // @ts-ignore
                size: "x-small", color: "info", variant: "flat",
            }));
            const __VLS_103 = __VLS_102({
                size: "x-small",
                color: "info",
                variant: "flat",
            }, ...__VLS_functionalComponentArgsRest(__VLS_102));
            var __VLS_104;
            const { default: __VLS_106 } = __VLS_nonNull(__VLS_104.slots);
            // @ts-ignore
            [reports,];
        }
        let __VLS_107;
        /** @ts-ignore @type { | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer'] | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer']} */
        vSpacer;
        // @ts-ignore
        const __VLS_108 = __VLS_asFunctionalComponent1(__VLS_107, new __VLS_107({
        // @ts-ignore
        }));
        const __VLS_109 = __VLS_108({}, ...__VLS_functionalComponentArgsRest(__VLS_108));
        let __VLS_112;
        /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch'] | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
        vSwitch;
        // @ts-ignore
        const __VLS_113 = __VLS_asFunctionalComponent1(__VLS_112, new __VLS_112({
            // @ts-ignore
            modelValue: (report.enabled), color: "primary", inset: true, hideDetails: true, density: "compact", disabled: (__VLS_unwrap(saving, {})),
        }));
        const __VLS_114 = __VLS_113({
            modelValue: (report.enabled),
            color: "primary",
            inset: true,
            hideDetails: true,
            density: "compact",
            disabled: (__VLS_unwrap(saving, {})),
        }, ...__VLS_functionalComponentArgsRest(__VLS_113));
        // @ts-ignore
        [saving,];
        let __VLS_117;
        /** @ts-ignore @type { | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider'] | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider']} */
        vDivider;
        // @ts-ignore
        const __VLS_118 = __VLS_asFunctionalComponent1(__VLS_117, new __VLS_117({
        // @ts-ignore
        }));
        const __VLS_119 = __VLS_118({}, ...__VLS_functionalComponentArgsRest(__VLS_118));
        let __VLS_122;
        /** @ts-ignore @type { | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text'] | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text']} */
        vCardText;
        // @ts-ignore
        const __VLS_123 = __VLS_asFunctionalComponent1(__VLS_122, new __VLS_122({
        // @ts-ignore
        }));
        const __VLS_124 = __VLS_123({}, ...__VLS_functionalComponentArgsRest(__VLS_123));
        var __VLS_125;
        const { default: __VLS_127 } = __VLS_nonNull(__VLS_125.slots);
        let __VLS_128;
        /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
        vRow;
        // @ts-ignore
        const __VLS_129 = __VLS_asFunctionalComponent1(__VLS_128, new __VLS_128({
            // @ts-ignore
            dense: true,
        }));
        const __VLS_130 = __VLS_129({
            dense: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_129));
        var __VLS_131;
        const { default: __VLS_133 } = __VLS_nonNull(__VLS_131.slots);
        let __VLS_134;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_135 = __VLS_asFunctionalComponent1(__VLS_134, new __VLS_134({
            // @ts-ignore
            cols: "12", sm: "6",
        }));
        const __VLS_136 = __VLS_135({
            cols: "12",
            sm: "6",
        }, ...__VLS_functionalComponentArgsRest(__VLS_135));
        var __VLS_137;
        const { default: __VLS_139 } = __VLS_nonNull(__VLS_137.slots);
        const __VLS_140 = SmartSelect || SmartSelect;
        // @ts-ignore
        const __VLS_141 = __VLS_asFunctionalComponent1(__VLS_140, new __VLS_140({
            // @ts-ignore
            modelValue: (report.run_interval), items: (__VLS_unwrap(intervalOptions, {})), label: "统计周期", disabled: (__VLS_unwrap(saving, {})),
        }));
        const __VLS_142 = __VLS_141({
            modelValue: (report.run_interval),
            items: (__VLS_unwrap(intervalOptions, {})),
            label: "统计周期",
            disabled: (__VLS_unwrap(saving, {})),
        }, ...__VLS_functionalComponentArgsRest(__VLS_141));
        // @ts-ignore
        [saving, intervalOptions,];
        let __VLS_145;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_146 = __VLS_asFunctionalComponent1(__VLS_145, new __VLS_145({
            // @ts-ignore
            cols: "12", sm: "6",
        }));
        const __VLS_147 = __VLS_146({
            cols: "12",
            sm: "6",
        }, ...__VLS_functionalComponentArgsRest(__VLS_146));
        var __VLS_148;
        const { default: __VLS_150 } = __VLS_nonNull(__VLS_148.slots);
        let __VLS_151;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_152 = __VLS_asFunctionalComponent1(__VLS_151, new __VLS_151({
            // @ts-ignore
            modelValue: (report.top_n_by_volume), modelModifiers: { number: true, }, label: "取样合约数（按成交额 TopN）", type: "number", min: "5", max: "500", density: "compact", variant: "outlined", hideDetails: true, disabled: (__VLS_unwrap(saving, {})),
        }));
        const __VLS_153 = __VLS_152({
            modelValue: (report.top_n_by_volume),
            modelModifiers: { number: true, },
            label: "取样合约数（按成交额 TopN）",
            type: "number",
            min: "5",
            max: "500",
            density: "compact",
            variant: "outlined",
            hideDetails: true,
            disabled: (__VLS_unwrap(saving, {})),
        }, ...__VLS_functionalComponentArgsRest(__VLS_152));
        // @ts-ignore
        [saving,];
        let __VLS_156;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_157 = __VLS_asFunctionalComponent1(__VLS_156, new __VLS_156({
            // @ts-ignore
            cols: "12", sm: "6",
        }));
        const __VLS_158 = __VLS_157({
            cols: "12",
            sm: "6",
        }, ...__VLS_functionalComponentArgsRest(__VLS_157));
        var __VLS_159;
        const { default: __VLS_161 } = __VLS_nonNull(__VLS_159.slots);
        let __VLS_162;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_163 = __VLS_asFunctionalComponent1(__VLS_162, new __VLS_162({
            // @ts-ignore
            modelValue: (report.top_n_gainers), modelModifiers: { number: true, }, label: "涨幅榜条数", type: "number", min: "1", max: "50", density: "compact", variant: "outlined", hideDetails: true, disabled: (__VLS_unwrap(saving, {})),
        }));
        const __VLS_164 = __VLS_163({
            modelValue: (report.top_n_gainers),
            modelModifiers: { number: true, },
            label: "涨幅榜条数",
            type: "number",
            min: "1",
            max: "50",
            density: "compact",
            variant: "outlined",
            hideDetails: true,
            disabled: (__VLS_unwrap(saving, {})),
        }, ...__VLS_functionalComponentArgsRest(__VLS_163));
        // @ts-ignore
        [saving,];
        let __VLS_167;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_168 = __VLS_asFunctionalComponent1(__VLS_167, new __VLS_167({
            // @ts-ignore
            cols: "12", sm: "6",
        }));
        const __VLS_169 = __VLS_168({
            cols: "12",
            sm: "6",
        }, ...__VLS_functionalComponentArgsRest(__VLS_168));
        var __VLS_170;
        const { default: __VLS_172 } = __VLS_nonNull(__VLS_170.slots);
        let __VLS_173;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_174 = __VLS_asFunctionalComponent1(__VLS_173, new __VLS_173({
            // @ts-ignore
            modelValue: (report.top_n_volume_ratio), modelModifiers: { number: true, }, label: "放量榜条数", type: "number", min: "1", max: "50", density: "compact", variant: "outlined", hideDetails: true, disabled: (__VLS_unwrap(saving, {})),
        }));
        const __VLS_175 = __VLS_174({
            modelValue: (report.top_n_volume_ratio),
            modelModifiers: { number: true, },
            label: "放量榜条数",
            type: "number",
            min: "1",
            max: "50",
            density: "compact",
            variant: "outlined",
            hideDetails: true,
            disabled: (__VLS_unwrap(saving, {})),
        }, ...__VLS_functionalComponentArgsRest(__VLS_174));
        // @ts-ignore
        [saving,];
        // @ts-ignore
        [];
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "d-flex flex-wrap ga-2 mt-3 text-caption text-grey-darken-1" },
        });
        /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
        /** @type {__VLS_StyleScopedClasses['flex-wrap']} */ ;
        /** @type {__VLS_StyleScopedClasses['ga-2']} */ ;
        /** @type {__VLS_StyleScopedClasses['mt-3']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-grey-darken-1']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
        (__VLS_unwrap(formatTime, {})(report.last_run));
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
        (report.enabled ? __VLS_unwrap(formatTime, {})(report.next_run) : '未启用');
        if (report.scanned != null) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
            (report.scanned);
        }
        if (report.last_error) {
            let __VLS_178;
            /** @ts-ignore @type { | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert'] | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert']} */
            vAlert;
            // @ts-ignore
            const __VLS_179 = __VLS_asFunctionalComponent1(__VLS_178, new __VLS_178({
                // @ts-ignore
                type: "error", variant: "tonal", density: "compact", ...{ class: "mt-3" },
            }));
            const __VLS_180 = __VLS_179({
                type: "error",
                variant: "tonal",
                density: "compact",
                ...{ class: "mt-3" },
            }, ...__VLS_functionalComponentArgsRest(__VLS_179));
            /** @type {__VLS_StyleScopedClasses['mt-3']} */ ;
            var __VLS_181;
            const { default: __VLS_183 } = __VLS_nonNull(__VLS_181.slots);
            (report.last_error);
            // @ts-ignore
            [formatTime, formatTime,];
        }
        // @ts-ignore
        [];
        let __VLS_184;
        /** @ts-ignore @type { | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider'] | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider']} */
        vDivider;
        // @ts-ignore
        const __VLS_185 = __VLS_asFunctionalComponent1(__VLS_184, new __VLS_184({
        // @ts-ignore
        }));
        const __VLS_186 = __VLS_185({}, ...__VLS_functionalComponentArgsRest(__VLS_185));
        let __VLS_189;
        /** @ts-ignore @type { | typeof __VLS_components.vCardActions | typeof __VLS_components.VCardActions | typeof __VLS_components['v-card-actions'] | typeof __VLS_components.vCardActions | typeof __VLS_components.VCardActions | typeof __VLS_components['v-card-actions']} */
        vCardActions;
        // @ts-ignore
        const __VLS_190 = __VLS_asFunctionalComponent1(__VLS_189, new __VLS_189({
        // @ts-ignore
        }));
        const __VLS_191 = __VLS_190({}, ...__VLS_functionalComponentArgsRest(__VLS_190));
        var __VLS_192;
        const { default: __VLS_194 } = __VLS_nonNull(__VLS_192.slots);
        let __VLS_195;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_196 = __VLS_asFunctionalComponent1(__VLS_195, new __VLS_195({
            // @ts-ignore
            ...{ 'onClick': {} }, color: "primary", variant: "text", prependIcon: "mdi-play-circle-outline", loading: (report.running), disabled: (status.value.running),
        }));
        const __VLS_197 = __VLS_196({
            ...{ 'onClick': {} },
            color: "primary",
            variant: "text",
            prependIcon: "mdi-play-circle-outline",
            loading: (report.running),
            disabled: (status.value.running),
        }, ...__VLS_functionalComponentArgsRest(__VLS_196));
        let __VLS_200;
        const __VLS_201 = {
            /** @type {typeof __VLS_200.click} */
            onClick: (...[$event]) => {
                void $event;
                return (__VLS_unwrap(runNow, {})(report.report_name));
                // @ts-ignore
                [status, runNow,];
            },
        };
        void __VLS_201;
        var __VLS_198;
        var __VLS_199;
        const { default: __VLS_202 } = __VLS_nonNull(__VLS_198.slots);
        // @ts-ignore
        [];
        let __VLS_203;
        /** @ts-ignore @type { | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer'] | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer']} */
        vSpacer;
        // @ts-ignore
        const __VLS_204 = __VLS_asFunctionalComponent1(__VLS_203, new __VLS_203({
        // @ts-ignore
        }));
        const __VLS_205 = __VLS_204({}, ...__VLS_functionalComponentArgsRest(__VLS_204));
        let __VLS_208;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_209 = __VLS_asFunctionalComponent1(__VLS_208, new __VLS_208({
            // @ts-ignore
            ...{ 'onClick': {} }, variant: "text", prependIcon: "mdi-eye-outline", disabled: (!status.value.latest[report.report_name]),
        }));
        const __VLS_210 = __VLS_209({
            ...{ 'onClick': {} },
            variant: "text",
            prependIcon: "mdi-eye-outline",
            disabled: (!status.value.latest[report.report_name]),
        }, ...__VLS_functionalComponentArgsRest(__VLS_209));
        let __VLS_213;
        const __VLS_214 = {
            /** @type {typeof __VLS_213.click} */
            onClick: (...[$event]) => {
                void $event;
                return (selectedReport.value = report.report_name);
                // @ts-ignore
                [status, selectedReport,];
            },
        };
        void __VLS_214;
        var __VLS_211;
        var __VLS_212;
        const { default: __VLS_215 } = __VLS_nonNull(__VLS_211.slots);
        // @ts-ignore
        [];
        // @ts-ignore
        [];
        // @ts-ignore
        [];
        // @ts-ignore
        [];
        // @ts-ignore
        [];
    }
    // @ts-ignore
    [];
    let __VLS_216;
    /** @ts-ignore @type { | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card'] | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card']} */
    vCard;
    // @ts-ignore
    const __VLS_217 = __VLS_asFunctionalComponent1(__VLS_216, new __VLS_216({
        // @ts-ignore
        ...{ class: "mt-4" },
    }));
    const __VLS_218 = __VLS_217({
        ...{ class: "mt-4" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_217));
    /** @type {__VLS_StyleScopedClasses['mt-4']} */ ;
    var __VLS_219;
    const { default: __VLS_221 } = __VLS_nonNull(__VLS_219.slots);
    let __VLS_222;
    /** @ts-ignore @type { | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title'] | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title']} */
    vCardTitle;
    // @ts-ignore
    const __VLS_223 = __VLS_asFunctionalComponent1(__VLS_222, new __VLS_222({
        // @ts-ignore
        ...{ class: "text-subtitle-1 d-flex align-center flex-wrap ga-2" },
    }));
    const __VLS_224 = __VLS_223({
        ...{ class: "text-subtitle-1 d-flex align-center flex-wrap ga-2" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_223));
    /** @type {__VLS_StyleScopedClasses['text-subtitle-1']} */ ;
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
    /** @type {__VLS_StyleScopedClasses['flex-wrap']} */ ;
    /** @type {__VLS_StyleScopedClasses['ga-2']} */ ;
    var __VLS_225;
    const { default: __VLS_227 } = __VLS_nonNull(__VLS_225.slots);
    let __VLS_228;
    /** @ts-ignore @type { | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon'] | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon']} */
    vIcon;
    // @ts-ignore
    const __VLS_229 = __VLS_asFunctionalComponent1(__VLS_228, new __VLS_228({
        // @ts-ignore
        start: true,
    }));
    const __VLS_230 = __VLS_229({
        start: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_229));
    var __VLS_231;
    const { default: __VLS_233 } = __VLS_nonNull(__VLS_231.slots);
    // @ts-ignore
    [];
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    let __VLS_234;
    /** @ts-ignore @type { | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer'] | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer']} */
    vSpacer;
    // @ts-ignore
    const __VLS_235 = __VLS_asFunctionalComponent1(__VLS_234, new __VLS_234({
    // @ts-ignore
    }));
    const __VLS_236 = __VLS_235({}, ...__VLS_functionalComponentArgsRest(__VLS_235));
    const __VLS_239 = SmartSelect || SmartSelect;
    // @ts-ignore
    const __VLS_240 = __VLS_asFunctionalComponent1(__VLS_239, new __VLS_239({
        // @ts-ignore
        modelValue: (selectedReport.value), items: (__VLS_unwrap(latestNames, {})), ...{ class: "reports-picker" },
    }));
    const __VLS_241 = __VLS_240({
        modelValue: (selectedReport.value),
        items: (__VLS_unwrap(latestNames, {})),
        ...{ class: "reports-picker" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_240));
    /** @type {__VLS_StyleScopedClasses['reports-picker']} */ ;
    // @ts-ignore
    [selectedReport, latestNames,];
    let __VLS_244;
    /** @ts-ignore @type { | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider'] | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider']} */
    vDivider;
    // @ts-ignore
    const __VLS_245 = __VLS_asFunctionalComponent1(__VLS_244, new __VLS_244({
    // @ts-ignore
    }));
    const __VLS_246 = __VLS_245({}, ...__VLS_functionalComponentArgsRest(__VLS_245));
    let __VLS_249;
    /** @ts-ignore @type { | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text'] | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text']} */
    vCardText;
    // @ts-ignore
    const __VLS_250 = __VLS_asFunctionalComponent1(__VLS_249, new __VLS_249({
    // @ts-ignore
    }));
    const __VLS_251 = __VLS_250({}, ...__VLS_functionalComponentArgsRest(__VLS_250));
    var __VLS_252;
    const { default: __VLS_254 } = __VLS_nonNull(__VLS_252.slots);
    if (currentLatest.value) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "text-caption text-grey-darken-1 mb-2" },
        });
        /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-grey-darken-1']} */ ;
        /** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
        (currentLatest.value.title);
        (__VLS_unwrap(formatTime, {})(currentLatest.value.generated_at));
        __VLS_asFunctionalElement1(__VLS_intrinsics.pre, __VLS_intrinsics.pre)({
            ...{ class: "report-body" },
        });
        /** @type {__VLS_StyleScopedClasses['report-body']} */ ;
        (currentLatest.value.markdown);
    }
    else {
        let __VLS_255;
        /** @ts-ignore @type { | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert'] | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert']} */
        vAlert;
        // @ts-ignore
        const __VLS_256 = __VLS_asFunctionalComponent1(__VLS_255, new __VLS_255({
            // @ts-ignore
            type: "info", variant: "tonal", density: "compact",
        }));
        const __VLS_257 = __VLS_256({
            type: "info",
            variant: "tonal",
            density: "compact",
        }, ...__VLS_functionalComponentArgsRest(__VLS_256));
        var __VLS_258;
        const { default: __VLS_260 } = __VLS_nonNull(__VLS_258.slots);
        // @ts-ignore
        [formatTime, currentLatest, currentLatest, currentLatest, currentLatest,];
    }
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    return {};
};
void [__VLS_template];
const __VLS_export = (await import('vue')).defineComponent({});
export default {};
