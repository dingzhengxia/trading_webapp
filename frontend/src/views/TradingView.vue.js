import { ref, onMounted } from 'vue';
import { useUiStore } from '@/stores/uiStore';
import { usePositionStore } from '@/stores/positionStore';
import { useSettingsStore } from '@/stores/settingsStore';
import ControlPanel from '@/components/ControlPanel.vue';
import PositionsPanel from '@/components/PositionsPanel.vue';
import PnlSummary from '@/components/PnlSummary.vue';
import OpenHistoryPanel from '@/components/OpenHistoryPanel.vue';
import AppDockFooter from '@/components/AppDockFooter.vue';
import apiClient from '@/services/api';
import { getErrorMessage } from '@/utils/errors';
const uiStore = useUiStore();
const positionStore = usePositionStore();
const settingsStore = useSettingsStore();
const activeTab = ref('general');
const isGeneratingPlan = ref(false);
const handleStartTrading = () => {
    if (settingsStore.settings) {
        const plan = settingsStore.settings;
        const total = (plan.enable_long_trades ? plan.long_coin_list.length : 0) +
            (plan.enable_short_trades ? plan.short_coin_list.length : 0);
        uiStore.launchTask('/api/trading/start', plan, '自动开仓', total);
    }
};
const handleSyncSlTp = () => {
    if (settingsStore.settings) {
        const { enable_long_sl_tp, long_stop_loss_percentage, long_take_profit_percentage, enable_short_sl_tp, short_stop_loss_percentage, short_take_profit_percentage, 
        // --- 新增: 提取移动止盈参数 ---
        enable_long_trailing_stop, long_trailing_stop_callback_rate, enable_short_trailing_stop, short_trailing_stop_callback_rate, 
        // --------------------------
        leverage, } = settingsStore.settings;
        const payload = {
            enable_long_sl_tp,
            long_stop_loss_percentage,
            long_take_profit_percentage,
            enable_short_sl_tp,
            short_stop_loss_percentage,
            short_take_profit_percentage,
            // --- 新增: 传递参数到后端 ---
            enable_long_trailing_stop,
            long_trailing_stop_callback_rate,
            enable_short_trailing_stop,
            short_trailing_stop_callback_rate,
            // ------------------------
            leverage,
        };
        uiStore.launchTask('/api/trading/sync-sltp', payload, '同步SL/TP/移动止盈', positionStore.positions.length);
    }
};
const onGenerateRebalancePlan = () => {
    if (settingsStore.settings) {
        const criteria = {
            method: settingsStore.settings.rebalance_method,
            top_n: settingsStore.settings.rebalance_top_n,
            min_volume_usd: settingsStore.settings.rebalance_min_volume_usd,
            abs_momentum_days: settingsStore.settings.rebalance_abs_momentum_days,
            rel_strength_days: settingsStore.settings.rebalance_rel_strength_days,
            rebalance_volume_ma_days: settingsStore.settings.rebalance_volume_ma_days,
            rebalance_volume_spike_ratio: settingsStore.settings.rebalance_volume_spike_ratio,
            rebalance_benchmark_coin: settingsStore.settings.rebalance_benchmark_coin,
            enable_rebalance_filters: settingsStore.settings.enable_rebalance_filters,
            rebalance_rsi_period: settingsStore.settings.rebalance_rsi_period,
            rebalance_rsi_threshold: settingsStore.settings.rebalance_rsi_threshold,
            rebalance_short_term_momentum_days: settingsStore.settings.rebalance_short_term_momentum_days,
            rebalance_short_term_momentum_threshold: settingsStore.settings.rebalance_short_term_momentum_threshold,
            rebalance_bollinger_period: settingsStore.settings.rebalance_bollinger_period,
            rebalance_bollinger_std_dev: settingsStore.settings.rebalance_bollinger_std_dev,
            rebalance_bollinger_width_spike_ratio: settingsStore.settings.rebalance_bollinger_width_spike_ratio,
        };
        handleGenerateRebalancePlan(criteria);
    }
};
const handleGenerateRebalancePlan = async (criteria) => {
    if (uiStore.isRunning || isGeneratingPlan.value)
        return;
    isGeneratingPlan.value = true;
    uiStore.logStore.addLog({
        message: '[前端] 正在生成再平衡计划...',
        level: 'info',
        timestamp: new Date().toLocaleTimeString(),
    });
    try {
        const response = await apiClient.post('/api/rebalance/plan', criteria);
        const planData = response.data;
        if (planData.error) {
            uiStore.logStore.addLog({
                message: `计划生成逻辑错误: ${planData.error}`,
                level: 'error',
                timestamp: new Date().toLocaleTimeString(),
            });
        }
        else {
            uiStore.rebalancePlan = planData;
            uiStore.showRebalanceDialog = true;
        }
    }
    catch (error) {
        const errorMsg = getErrorMessage(error);
        uiStore.logStore.addLog({
            message: `[后端] ❌ 生成计划请求失败: ${errorMsg}`,
            level: 'error',
            timestamp: new Date().toLocaleTimeString(),
        });
    }
    finally {
        isGeneratingPlan.value = false;
    }
};
onMounted(() => {
    if (positionStore.positions.length === 0) {
        positionStore.fetchPositions();
    }
});
const __VLS_ctx = {};
let __VLS_components;
let __VLS_intrinsics;
let __VLS_directives;
void __VLS_ctx, __VLS_components, __VLS_intrinsics, __VLS_directives;
const __VLS_template = () => {
    __VLS_withDotValue(activeTab, {});
    __VLS_withDotValue(uiStore, {});
    void {};
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ style: ({ paddingBottom: '80px' }) },
    });
    let __VLS_0;
    /** @ts-ignore @type { | typeof __VLS_components.vContainer | typeof __VLS_components.VContainer | typeof __VLS_components['v-container'] | typeof __VLS_components.vContainer | typeof __VLS_components.VContainer | typeof __VLS_components['v-container']} */
    vContainer;
    // @ts-ignore
    const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
        // @ts-ignore
        fluid: true,
    }));
    const __VLS_2 = __VLS_1({
        fluid: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_1));
    var __VLS_3;
    const { default: __VLS_5 } = __VLS_nonNull(__VLS_3.slots);
    let __VLS_6;
    /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
    vRow;
    // @ts-ignore
    const __VLS_7 = __VLS_asFunctionalComponent1(__VLS_6, new __VLS_6({
    // @ts-ignore
    }));
    const __VLS_8 = __VLS_7({}, ...__VLS_functionalComponentArgsRest(__VLS_7));
    var __VLS_9;
    const { default: __VLS_11 } = __VLS_nonNull(__VLS_9.slots);
    let __VLS_12;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_13 = __VLS_asFunctionalComponent1(__VLS_12, new __VLS_12({
        // @ts-ignore
        cols: "12",
    }));
    const __VLS_14 = __VLS_13({
        cols: "12",
    }, ...__VLS_functionalComponentArgsRest(__VLS_13));
    var __VLS_15;
    const { default: __VLS_17 } = __VLS_nonNull(__VLS_15.slots);
    const __VLS_18 = ControlPanel;
    // @ts-ignore
    const __VLS_19 = __VLS_asFunctionalComponent1(__VLS_18, new __VLS_18({
        // @ts-ignore
        modelValue: (activeTab.value),
    }));
    const __VLS_20 = __VLS_19({
        modelValue: (activeTab.value),
    }, ...__VLS_functionalComponentArgsRest(__VLS_19));
    // @ts-ignore
    [activeTab,];
    // @ts-ignore
    [];
    let __VLS_23;
    /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
    vRow;
    // @ts-ignore
    const __VLS_24 = __VLS_asFunctionalComponent1(__VLS_23, new __VLS_23({
    // @ts-ignore
    }));
    const __VLS_25 = __VLS_24({}, ...__VLS_functionalComponentArgsRest(__VLS_24));
    var __VLS_26;
    const { default: __VLS_28 } = __VLS_nonNull(__VLS_26.slots);
    let __VLS_29;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_30 = __VLS_asFunctionalComponent1(__VLS_29, new __VLS_29({
        // @ts-ignore
        cols: "12",
    }));
    const __VLS_31 = __VLS_30({
        cols: "12",
    }, ...__VLS_functionalComponentArgsRest(__VLS_30));
    var __VLS_32;
    const { default: __VLS_34 } = __VLS_nonNull(__VLS_32.slots);
    const __VLS_35 = PnlSummary;
    // @ts-ignore
    const __VLS_36 = __VLS_asFunctionalComponent1(__VLS_35, new __VLS_35({
    // @ts-ignore
    }));
    const __VLS_37 = __VLS_36({}, ...__VLS_functionalComponentArgsRest(__VLS_36));
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    const __VLS_40 = PositionsPanel;
    // @ts-ignore
    const __VLS_41 = __VLS_asFunctionalComponent1(__VLS_40, new __VLS_40({
    // @ts-ignore
    }));
    const __VLS_42 = __VLS_41({}, ...__VLS_functionalComponentArgsRest(__VLS_41));
    let __VLS_45;
    /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
    vRow;
    // @ts-ignore
    const __VLS_46 = __VLS_asFunctionalComponent1(__VLS_45, new __VLS_45({
    // @ts-ignore
    }));
    const __VLS_47 = __VLS_46({}, ...__VLS_functionalComponentArgsRest(__VLS_46));
    var __VLS_48;
    const { default: __VLS_50 } = __VLS_nonNull(__VLS_48.slots);
    let __VLS_51;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_52 = __VLS_asFunctionalComponent1(__VLS_51, new __VLS_51({
        // @ts-ignore
        cols: "12",
    }));
    const __VLS_53 = __VLS_52({
        cols: "12",
    }, ...__VLS_functionalComponentArgsRest(__VLS_52));
    var __VLS_54;
    const { default: __VLS_56 } = __VLS_nonNull(__VLS_54.slots);
    const __VLS_57 = OpenHistoryPanel;
    // @ts-ignore
    const __VLS_58 = __VLS_asFunctionalComponent1(__VLS_57, new __VLS_57({
    // @ts-ignore
    }));
    const __VLS_59 = __VLS_58({}, ...__VLS_functionalComponentArgsRest(__VLS_58));
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    const __VLS_62 = AppDockFooter || AppDockFooter;
    // @ts-ignore
    const __VLS_63 = __VLS_asFunctionalComponent1(__VLS_62, new __VLS_62({
    // @ts-ignore
    }));
    const __VLS_64 = __VLS_63({}, ...__VLS_functionalComponentArgsRest(__VLS_63));
    var __VLS_65;
    const { default: __VLS_67 } = __VLS_nonNull(__VLS_65.slots);
    if (activeTab.value === 'general') {
        let __VLS_68;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_69 = __VLS_asFunctionalComponent1(__VLS_68, new __VLS_68({
            // @ts-ignore
            ...{ 'onClick': {} }, color: "info", variant: "tonal", disabled: (uiStore.value.isRunning), ...{ class: "mr-3" },
        }));
        const __VLS_70 = __VLS_69({
            ...{ 'onClick': {} },
            color: "info",
            variant: "tonal",
            disabled: (uiStore.value.isRunning),
            ...{ class: "mr-3" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_69));
        let __VLS_73;
        const __VLS_74 = {
            /** @type {typeof __VLS_73.click} */
            onClick: (__VLS_unwrap(handleSyncSlTp, {})),
        };
        void __VLS_74;
        /** @type {__VLS_StyleScopedClasses['mr-3']} */ ;
        var __VLS_71;
        var __VLS_72;
        const { default: __VLS_75 } = __VLS_nonNull(__VLS_71.slots);
        // @ts-ignore
        [activeTab, uiStore, handleSyncSlTp,];
        let __VLS_76;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_77 = __VLS_asFunctionalComponent1(__VLS_76, new __VLS_76({
            // @ts-ignore
            ...{ 'onClick': {} }, color: "success", variant: "tonal", prependIcon: "mdi-play", loading: (uiStore.value.isRunning), disabled: (uiStore.value.isRunning),
        }));
        const __VLS_78 = __VLS_77({
            ...{ 'onClick': {} },
            color: "success",
            variant: "tonal",
            prependIcon: "mdi-play",
            loading: (uiStore.value.isRunning),
            disabled: (uiStore.value.isRunning),
        }, ...__VLS_functionalComponentArgsRest(__VLS_77));
        let __VLS_81;
        const __VLS_82 = {
            /** @type {typeof __VLS_81.click} */
            onClick: (__VLS_unwrap(handleStartTrading, {})),
        };
        void __VLS_82;
        var __VLS_79;
        var __VLS_80;
        const { default: __VLS_83 } = __VLS_nonNull(__VLS_79.slots);
        // @ts-ignore
        [uiStore, uiStore, handleStartTrading,];
    }
    if (activeTab.value === 'rebalance') {
        let __VLS_84;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_85 = __VLS_asFunctionalComponent1(__VLS_84, new __VLS_84({
            // @ts-ignore
            ...{ 'onClick': {} }, color: "primary", variant: "tonal", loading: (__VLS_unwrap(isGeneratingPlan, {})), disabled: (uiStore.value.isRunning || __VLS_unwrap(isGeneratingPlan, {})),
        }));
        const __VLS_86 = __VLS_85({
            ...{ 'onClick': {} },
            color: "primary",
            variant: "tonal",
            loading: (__VLS_unwrap(isGeneratingPlan, {})),
            disabled: (uiStore.value.isRunning || __VLS_unwrap(isGeneratingPlan, {})),
        }, ...__VLS_functionalComponentArgsRest(__VLS_85));
        let __VLS_89;
        const __VLS_90 = {
            /** @type {typeof __VLS_89.click} */
            onClick: (__VLS_unwrap(onGenerateRebalancePlan, {})),
        };
        void __VLS_90;
        var __VLS_87;
        var __VLS_88;
        const { default: __VLS_91 } = __VLS_nonNull(__VLS_87.slots);
        // @ts-ignore
        [activeTab, uiStore, isGeneratingPlan, isGeneratingPlan, onGenerateRebalancePlan,];
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
