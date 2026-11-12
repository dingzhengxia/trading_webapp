import { ref, watch, computed } from 'vue'; // <-- 引入 computed
import { useUiStore } from '@/stores/uiStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { usePositionStore } from '@/stores/positionStore';
const uiStore = useUiStore();
const settingsStore = useSettingsStore();
const positionStore = usePositionStore();
const manualRatio = ref(0);
const internalPlan = ref(null);
// --- 核心修改：新增一个计算属性来实时计算目标空头总价值 ---
const targetShortValue = computed(() => {
    // 目标空头总价值 = 当前多头总价值 * 手动调整的目标比例
    return positionStore.longNotional * (manualRatio.value / 100);
});
// --- 修改结束 ---
const recalculatePlanLocally = () => {
    if (!uiStore.rebalancePlan)
        return;
    // 使用 computed 属性 targetShortValue 来获取目标价值
    const targetShortValueVal = targetShortValue.value;
    const targetCoinList = uiStore.rebalancePlan.target_coin_list;
    const currentShortPositions = positionStore.shortPositions;
    const currentPositionsMap = new Map(currentShortPositions.map((p) => [p.symbol, p]));
    const currentSymbols = new Set(currentPositionsMap.keys());
    const targetSymbols = new Set(targetCoinList);
    const newClosePlan = [];
    const newOpenPlanData = {};
    if (targetSymbols.size === 0) {
        for (const position of currentShortPositions) {
            newClosePlan.push({
                symbol: position.symbol,
                notional: position.notional,
                close_value: position.notional,
                close_ratio_perc: 100,
                close_ratio: 1.0,
            });
        }
    }
    else {
        const valuePerCoinIdeal = targetShortValueVal / targetSymbols.size;
        for (const [symbol, position] of currentPositionsMap.entries()) {
            if (!targetSymbols.has(symbol)) {
                newClosePlan.push({
                    symbol: position.symbol,
                    notional: position.notional,
                    close_value: position.notional,
                    close_ratio_perc: 100,
                    close_ratio: 1.0,
                });
            }
            else {
                const delta = valuePerCoinIdeal - position.notional;
                if (delta < -10) {
                    const closeRatio = Math.min(Math.abs(delta) / position.notional, 1.0);
                    newClosePlan.push({
                        symbol: position.symbol,
                        notional: position.notional,
                        close_value: position.notional * closeRatio,
                        close_ratio_perc: closeRatio * 100,
                        close_ratio: closeRatio,
                    });
                }
                else if (delta > 10) {
                    newOpenPlanData[symbol] = delta;
                }
            }
        }
        const symbolsToOpenNew = [...targetSymbols].filter((s) => !currentSymbols.has(s));
        for (const symbol of symbolsToOpenNew) {
            newOpenPlanData[symbol] = valuePerCoinIdeal;
        }
    }
    const newOpenPlan = [];
    if (targetCoinList.length > 0) {
        const valuePerCoinIdeal = targetShortValueVal / targetCoinList.length;
        for (const [symbol, value] of Object.entries(newOpenPlanData)) {
            const percentage = valuePerCoinIdeal > 0.01 ? (value / valuePerCoinIdeal) * 100 : 100;
            newOpenPlan.push({ symbol, open_value: value, percentage });
        }
    }
    internalPlan.value = {
        target_ratio_perc: manualRatio.value,
        positions_to_close: newClosePlan,
        positions_to_open: newOpenPlan,
        target_coin_list: targetCoinList,
    };
};
watch(() => uiStore.rebalancePlan, (newPlan) => {
    if (newPlan) {
        manualRatio.value = newPlan.target_ratio_perc;
        internalPlan.value = newPlan;
    }
    else {
        internalPlan.value = null;
    }
});
watch(manualRatio, () => {
    if (uiStore.showRebalanceDialog && uiStore.rebalancePlan) {
        recalculatePlanLocally();
    }
});
const close = () => {
    uiStore.showRebalanceDialog = false;
};
const applyList = () => {
    if (!internalPlan.value || !settingsStore.settings)
        return;
    const openSymbols = new Set(internalPlan.value.positions_to_open.map((p) => p.symbol));
    const symbolsToKeep = new Set(internalPlan.value.positions_to_close
        .filter((p) => p.close_ratio_perc < 100)
        .map((p) => p.symbol));
    const newShortList = Array.from(new Set([...openSymbols, ...symbolsToKeep])).sort();
    settingsStore.settings.short_coin_list = newShortList;
    uiStore.logStore.addLog({
        message: `空头币种列表已更新为 ${newShortList.length} 个币种并自动保存。`,
        level: 'success',
        timestamp: new Date().toLocaleTimeString(),
    });
    close();
};
const executePlan = async () => {
    if (!internalPlan.value || uiStore.isRunning)
        return;
    const executionOrders = [];
    for (const item of internalPlan.value.positions_to_close) {
        executionOrders.push({
            symbol: item.symbol,
            action: 'CLOSE',
            side: 'buy',
            close_ratio: item.close_ratio_perc / 100,
        });
    }
    for (const item of internalPlan.value.positions_to_open) {
        executionOrders.push({
            symbol: item.symbol,
            action: 'OPEN',
            side: 'sell',
            value_to_trade: item.open_value,
        });
    }
    close();
    const taskName = '执行再平衡';
    const totalTasks = executionOrders.length;
    uiStore.launchTask('/api/rebalance/execute', { orders: executionOrders }, taskName, totalTasks);
};
const __VLS_ctx = {};
let __VLS_components;
let __VLS_intrinsics;
let __VLS_directives;
void __VLS_ctx, __VLS_components, __VLS_intrinsics, __VLS_directives;
const __VLS_template = () => {
    __VLS_withDotValue(uiStore, {});
    __VLS_withDotValue(internalPlan, {});
    __VLS_withDotValue(manualRatio, {});
    __VLS_withDotValue(targetShortValue, {});
    let __VLS_0;
    /** @ts-ignore @type { | typeof __VLS_components.vDialog | typeof __VLS_components.VDialog | typeof __VLS_components['v-dialog'] | typeof __VLS_components.vDialog | typeof __VLS_components.VDialog | typeof __VLS_components['v-dialog']} */
    vDialog;
    // @ts-ignore
    const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
        // @ts-ignore
        modelValue: (uiStore.value.showRebalanceDialog), maxWidth: "600px", persistent: true,
    }));
    const __VLS_2 = __VLS_1({
        modelValue: (uiStore.value.showRebalanceDialog),
        maxWidth: "600px",
        persistent: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_1));
    var __VLS_3;
    const { default: __VLS_5 } = __VLS_nonNull(__VLS_3.slots);
    if (internalPlan.value) {
        let __VLS_6;
        /** @ts-ignore @type { | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card'] | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card']} */
        vCard;
        // @ts-ignore
        const __VLS_7 = __VLS_asFunctionalComponent1(__VLS_6, new __VLS_6({
        // @ts-ignore
        }));
        const __VLS_8 = __VLS_7({}, ...__VLS_functionalComponentArgsRest(__VLS_7));
        var __VLS_9;
        const { default: __VLS_11 } = __VLS_nonNull(__VLS_9.slots);
        let __VLS_12;
        /** @ts-ignore @type { | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title'] | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title']} */
        vCardTitle;
        // @ts-ignore
        const __VLS_13 = __VLS_asFunctionalComponent1(__VLS_12, new __VLS_12({
            // @ts-ignore
            ...{ class: "text-h5" },
        }));
        const __VLS_14 = __VLS_13({
            ...{ class: "text-h5" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_13));
        /** @type {__VLS_StyleScopedClasses['text-h5']} */ ;
        var __VLS_15;
        const { default: __VLS_17 } = __VLS_nonNull(__VLS_15.slots);
        (manualRatio.value.toFixed(1));
        // @ts-ignore
        [uiStore, internalPlan, manualRatio,];
        let __VLS_18;
        /** @ts-ignore @type { | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text'] | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text']} */
        vCardText;
        // @ts-ignore
        const __VLS_19 = __VLS_asFunctionalComponent1(__VLS_18, new __VLS_18({
        // @ts-ignore
        }));
        const __VLS_20 = __VLS_19({}, ...__VLS_functionalComponentArgsRest(__VLS_19));
        var __VLS_21;
        const { default: __VLS_23 } = __VLS_nonNull(__VLS_21.slots);
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "text-center mb-6" },
        });
        /** @type {__VLS_StyleScopedClasses['text-center']} */ ;
        /** @type {__VLS_StyleScopedClasses['mb-6']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "text-caption text-grey" },
        });
        /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "text-h4 font-weight-bold text-amber-accent-3 my-1" },
        });
        /** @type {__VLS_StyleScopedClasses['text-h4']} */ ;
        /** @type {__VLS_StyleScopedClasses['font-weight-bold']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-amber-accent-3']} */ ;
        /** @type {__VLS_StyleScopedClasses['my-1']} */ ;
        (targetShortValue.value.toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }));
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "mb-6" },
        });
        /** @type {__VLS_StyleScopedClasses['mb-6']} */ ;
        let __VLS_24;
        /** @ts-ignore @type { | typeof __VLS_components.vSlider | typeof __VLS_components.VSlider | typeof __VLS_components['v-slider'] | typeof __VLS_components.vSlider | typeof __VLS_components.VSlider | typeof __VLS_components['v-slider']} */
        vSlider;
        // @ts-ignore
        const __VLS_25 = __VLS_asFunctionalComponent1(__VLS_24, new __VLS_24({
            // @ts-ignore
            modelValue: (manualRatio.value), step: (0.5), color: "primary", label: "手动调整目标比例", ...{ class: "my-4 align-center" }, hideDetails: true, min: "0", max: "150",
        }));
        const __VLS_26 = __VLS_25({
            modelValue: (manualRatio.value),
            step: (0.5),
            color: "primary",
            label: "手动调整目标比例",
            ...{ class: "my-4 align-center" },
            hideDetails: true,
            min: "0",
            max: "150",
        }, ...__VLS_functionalComponentArgsRest(__VLS_25));
        /** @type {__VLS_StyleScopedClasses['my-4']} */ ;
        /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
        var __VLS_27;
        const { default: __VLS_29 } = __VLS_nonNull(__VLS_27.slots);
        {
            const { 'thumb-label': __VLS_30 } = __VLS_nonNull(__VLS_27.slots);
            const [{ modelValue }] = __VLS_vSlot(__VLS_nonNull(__VLS_30));
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
                ...{ class: "font-weight-bold" },
            });
            /** @type {__VLS_StyleScopedClasses['font-weight-bold']} */ ;
            (modelValue.toFixed(1));
            // @ts-ignore
            [manualRatio, targetShortValue,];
        }
        // @ts-ignore
        [];
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
        if (internalPlan.value.positions_to_close.length) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
            __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
                ...{ class: "font-weight-bold" },
            });
            /** @type {__VLS_StyleScopedClasses['font-weight-bold']} */ ;
            let __VLS_31;
            /** @ts-ignore @type { | typeof __VLS_components.vList | typeof __VLS_components.VList | typeof __VLS_components['v-list'] | typeof __VLS_components.vList | typeof __VLS_components.VList | typeof __VLS_components['v-list']} */
            vList;
            // @ts-ignore
            const __VLS_32 = __VLS_asFunctionalComponent1(__VLS_31, new __VLS_31({
                // @ts-ignore
                density: "compact",
            }));
            const __VLS_33 = __VLS_32({
                density: "compact",
            }, ...__VLS_functionalComponentArgsRest(__VLS_32));
            var __VLS_34;
            const { default: __VLS_36 } = __VLS_nonNull(__VLS_34.slots);
            const __VLS_37 = __VLS_tryAsConstant((internalPlan.value.positions_to_close));
            for (const [p] of __VLS_vFor(__VLS_nonNull(__VLS_37))) {
                let __VLS_38;
                /** @ts-ignore @type { | typeof __VLS_components.vListItem | typeof __VLS_components.VListItem | typeof __VLS_components['v-list-item'] | typeof __VLS_components.vListItem | typeof __VLS_components.VListItem | typeof __VLS_components['v-list-item']} */
                vListItem;
                // @ts-ignore
                const __VLS_39 = __VLS_asFunctionalComponent1(__VLS_38, new __VLS_38({
                    // @ts-ignore
                    key: (p.symbol),
                }));
                const __VLS_40 = __VLS_39({
                    key: (p.symbol),
                }, ...__VLS_functionalComponentArgsRest(__VLS_39));
                var __VLS_41;
                const { default: __VLS_43 } = __VLS_nonNull(__VLS_41.slots);
                (p.symbol);
                (p.close_value.toFixed(2));
                (p.close_ratio_perc.toFixed(0));
                // @ts-ignore
                [internalPlan, internalPlan,];
                // @ts-ignore
                [];
            }
            // @ts-ignore
            [];
        }
        if (internalPlan.value.positions_to_open.length) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                ...{ class: "mt-4" },
            });
            /** @type {__VLS_StyleScopedClasses['mt-4']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
                ...{ class: "font-weight-bold" },
            });
            /** @type {__VLS_StyleScopedClasses['font-weight-bold']} */ ;
            let __VLS_44;
            /** @ts-ignore @type { | typeof __VLS_components.vList | typeof __VLS_components.VList | typeof __VLS_components['v-list'] | typeof __VLS_components.vList | typeof __VLS_components.VList | typeof __VLS_components['v-list']} */
            vList;
            // @ts-ignore
            const __VLS_45 = __VLS_asFunctionalComponent1(__VLS_44, new __VLS_44({
                // @ts-ignore
                density: "compact",
            }));
            const __VLS_46 = __VLS_45({
                density: "compact",
            }, ...__VLS_functionalComponentArgsRest(__VLS_45));
            var __VLS_47;
            const { default: __VLS_49 } = __VLS_nonNull(__VLS_47.slots);
            const __VLS_50 = __VLS_tryAsConstant((internalPlan.value.positions_to_open));
            for (const [p] of __VLS_vFor(__VLS_nonNull(__VLS_50))) {
                let __VLS_51;
                /** @ts-ignore @type { | typeof __VLS_components.vListItem | typeof __VLS_components.VListItem | typeof __VLS_components['v-list-item'] | typeof __VLS_components.vListItem | typeof __VLS_components.VListItem | typeof __VLS_components['v-list-item']} */
                vListItem;
                // @ts-ignore
                const __VLS_52 = __VLS_asFunctionalComponent1(__VLS_51, new __VLS_51({
                    // @ts-ignore
                    key: (p.symbol),
                }));
                const __VLS_53 = __VLS_52({
                    key: (p.symbol),
                }, ...__VLS_functionalComponentArgsRest(__VLS_52));
                var __VLS_54;
                const { default: __VLS_56 } = __VLS_nonNull(__VLS_54.slots);
                (p.symbol);
                (p.open_value.toFixed(2));
                (p.percentage.toFixed(0));
                // @ts-ignore
                [internalPlan, internalPlan,];
                // @ts-ignore
                [];
            }
            // @ts-ignore
            [];
        }
        let __VLS_57;
        /** @ts-ignore @type { | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert'] | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert']} */
        vAlert;
        // @ts-ignore
        const __VLS_58 = __VLS_asFunctionalComponent1(__VLS_57, new __VLS_57({
            // @ts-ignore
            type: "warning", variant: "tonal", ...{ class: "mt-4 text-caption" },
        }));
        const __VLS_59 = __VLS_58({
            type: "warning",
            variant: "tonal",
            ...{ class: "mt-4 text-caption" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_58));
        /** @type {__VLS_StyleScopedClasses['mt-4']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
        var __VLS_60;
        const { default: __VLS_62 } = __VLS_nonNull(__VLS_60.slots);
        // @ts-ignore
        [];
        // @ts-ignore
        [];
        let __VLS_63;
        /** @ts-ignore @type { | typeof __VLS_components.vCardActions | typeof __VLS_components.VCardActions | typeof __VLS_components['v-card-actions'] | typeof __VLS_components.vCardActions | typeof __VLS_components.VCardActions | typeof __VLS_components['v-card-actions']} */
        vCardActions;
        // @ts-ignore
        const __VLS_64 = __VLS_asFunctionalComponent1(__VLS_63, new __VLS_63({
        // @ts-ignore
        }));
        const __VLS_65 = __VLS_64({}, ...__VLS_functionalComponentArgsRest(__VLS_64));
        var __VLS_66;
        const { default: __VLS_68 } = __VLS_nonNull(__VLS_66.slots);
        let __VLS_69;
        /** @ts-ignore @type { | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer'] | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer']} */
        vSpacer;
        // @ts-ignore
        const __VLS_70 = __VLS_asFunctionalComponent1(__VLS_69, new __VLS_69({
        // @ts-ignore
        }));
        const __VLS_71 = __VLS_70({}, ...__VLS_functionalComponentArgsRest(__VLS_70));
        let __VLS_74;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_75 = __VLS_asFunctionalComponent1(__VLS_74, new __VLS_74({
            // @ts-ignore
            ...{ 'onClick': {} }, color: "blue-darken-1", variant: "text",
        }));
        const __VLS_76 = __VLS_75({
            ...{ 'onClick': {} },
            color: "blue-darken-1",
            variant: "text",
        }, ...__VLS_functionalComponentArgsRest(__VLS_75));
        let __VLS_79;
        const __VLS_80 = {
            /** @type {typeof __VLS_79.click} */
            onClick: (__VLS_unwrap(close, {})),
        };
        void __VLS_80;
        var __VLS_77;
        var __VLS_78;
        const { default: __VLS_81 } = __VLS_nonNull(__VLS_77.slots);
        // @ts-ignore
        [close,];
        let __VLS_82;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_83 = __VLS_asFunctionalComponent1(__VLS_82, new __VLS_82({
            // @ts-ignore
            ...{ 'onClick': {} }, color: "primary", variant: "text",
        }));
        const __VLS_84 = __VLS_83({
            ...{ 'onClick': {} },
            color: "primary",
            variant: "text",
        }, ...__VLS_functionalComponentArgsRest(__VLS_83));
        let __VLS_87;
        const __VLS_88 = {
            /** @type {typeof __VLS_87.click} */
            onClick: (__VLS_unwrap(applyList, {})),
        };
        void __VLS_88;
        var __VLS_85;
        var __VLS_86;
        const { default: __VLS_89 } = __VLS_nonNull(__VLS_85.slots);
        // @ts-ignore
        [applyList,];
        let __VLS_90;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_91 = __VLS_asFunctionalComponent1(__VLS_90, new __VLS_90({
            // @ts-ignore
            ...{ 'onClick': {} }, color: "red-darken-1", variant: "tonal", disabled: (uiStore.value.isRunning),
        }));
        const __VLS_92 = __VLS_91({
            ...{ 'onClick': {} },
            color: "red-darken-1",
            variant: "tonal",
            disabled: (uiStore.value.isRunning),
        }, ...__VLS_functionalComponentArgsRest(__VLS_91));
        let __VLS_95;
        const __VLS_96 = {
            /** @type {typeof __VLS_95.click} */
            onClick: (__VLS_unwrap(executePlan, {})),
        };
        void __VLS_96;
        var __VLS_93;
        var __VLS_94;
        const { default: __VLS_97 } = __VLS_nonNull(__VLS_93.slots);
        // @ts-ignore
        [uiStore, executePlan,];
        // @ts-ignore
        [];
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
