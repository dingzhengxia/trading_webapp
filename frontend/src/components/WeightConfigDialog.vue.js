import { ref, watch, computed, nextTick } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';
const { defineProps, defineEmits, } = {};
const props = defineProps();
const emit = defineEmits(['update:modelValue']);
const settingsStore = useSettingsStore();
const localWeights = ref([]);
const manuallyEdited = ref(new Set());
let isRecalculating = false;
const show = computed({
    get: () => props.modelValue,
    set: (value) => emit('update:modelValue', value),
});
const totalWeight = computed(() => {
    return localWeights.value.reduce((sum, item) => sum + (Number(item.weight) || 0), 0);
});
// --- 这是最终的、简单且正确的重新计算逻辑 ---
const recalculateWeights = (editedSymbol) => {
    if (isRecalculating)
        return;
    isRecalculating = true;
    // 核心修正：只有在值发生变动时，才将该项加入“手动编辑”列表
    manuallyEdited.value.add(editedSymbol);
    const unassignedItems = localWeights.value.filter((item) => !manuallyEdited.value.has(item.symbol));
    const lockedTotal = localWeights.value
        .filter((item) => manuallyEdited.value.has(item.symbol))
        .reduce((sum, item) => sum + (Number(item.weight) || 0), 0);
    if (unassignedItems.length > 0) {
        const remainingTotal = 100 - lockedTotal;
        distribute(remainingTotal >= 0 ? remainingTotal : 0, unassignedItems);
    }
    else if (Math.abs(totalWeight.value - 100) > 0.001) {
        const lastItem = localWeights.value.find((item) => item.symbol !== editedSymbol) || localWeights.value[0];
        if (lastItem) {
            const diff = 100 - totalWeight.value;
            lastItem.weight = parseFloat(((Number(lastItem.weight) || 0) + diff).toFixed(2));
        }
    }
    nextTick(() => {
        isRecalculating = false;
    });
};
// 精确的分配函数
const distribute = (total, items) => {
    const count = items.length;
    if (count === 0)
        return;
    const avg = total / count;
    let accumulatedWeight = 0;
    items.forEach((item, index) => {
        if (index === count - 1) {
            item.weight = parseFloat((total - accumulatedWeight).toFixed(2));
        }
        else {
            const w = parseFloat(avg.toFixed(2));
            item.weight = w;
            accumulatedWeight += w;
        }
    });
};
// “均分权重”按钮，清空所有锁定，然后重新均分
const resetAndUnlock = () => {
    manuallyEdited.value.clear();
    distribute(100, localWeights.value);
};
// --- 核心修正：初始化函数 ---
const initWeights = () => {
    if (!settingsStore.settings?.long_coin_list)
        return;
    const selectedCoins = settingsStore.settings.long_coin_list;
    const currentWeights = settingsStore.settings.long_custom_weights || {};
    // 关键：每次打开弹窗，都必须清空“手动编辑”的记录！
    manuallyEdited.value.clear();
    localWeights.value = selectedCoins.map((coin) => ({
        symbol: coin,
        weight: currentWeights[coin] !== undefined ? currentWeights[coin] : 0,
    }));
    // 如果没有自定义权重，或者总和不为100，则自动均分
    if (Object.keys(currentWeights).length === 0 || Math.abs(totalWeight.value - 100) > 0.001) {
        resetAndUnlock();
    }
    // 注意：不再有 else 分支去预设 manuallyEdited
};
const save = () => {
    if (Math.abs(totalWeight.value - 100) < 0.001) {
        const newWeights = {};
        localWeights.value.forEach((item) => {
            newWeights[item.symbol] = item.weight;
        });
        if (settingsStore.settings) {
            settingsStore.settings.long_custom_weights = newWeights;
        }
        close();
    }
};
const close = () => {
    emit('update:modelValue', false);
};
watch(() => props.modelValue, (newValue) => {
    if (newValue) {
        // 每次打开弹窗，都重新初始化
        initWeights();
    }
}, { immediate: true });
const __VLS_ctx = {
    ...{},
    ...{},
    ...{},
    ...{},
};
let __VLS_components;
let __VLS_intrinsics;
let __VLS_directives;
void __VLS_ctx, __VLS_components, __VLS_intrinsics, __VLS_directives;
const __VLS_template = () => {
    __VLS_withDotValue(totalWeight, {});
    let __VLS_0;
    /** @ts-ignore @type { | typeof __VLS_components.vDialog | typeof __VLS_components.VDialog | typeof __VLS_components['v-dialog'] | typeof __VLS_components.vDialog | typeof __VLS_components.VDialog | typeof __VLS_components['v-dialog']} */
    vDialog;
    // @ts-ignore
    const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
        // @ts-ignore
        modelValue: (__VLS_unwrap(show, {})), maxWidth: "500px", persistent: true,
    }));
    const __VLS_2 = __VLS_1({
        modelValue: (__VLS_unwrap(show, {})),
        maxWidth: "500px",
        persistent: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_1));
    var __VLS_3;
    const { default: __VLS_5 } = __VLS_nonNull(__VLS_3.slots);
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
    }));
    const __VLS_14 = __VLS_13({}, ...__VLS_functionalComponentArgsRest(__VLS_13));
    var __VLS_15;
    const { default: __VLS_17 } = __VLS_nonNull(__VLS_15.slots);
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
        ...{ class: "text-h5" },
    });
    /** @type {__VLS_StyleScopedClasses['text-h5']} */ ;
    // @ts-ignore
    [show,];
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
    __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
        ...{ class: "text-caption mb-4" },
    });
    /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
    /** @type {__VLS_StyleScopedClasses['mb-4']} */ ;
    let __VLS_24;
    /** @ts-ignore @type { | typeof __VLS_components.vForm | typeof __VLS_components.VForm | typeof __VLS_components['v-form'] | typeof __VLS_components.vForm | typeof __VLS_components.VForm | typeof __VLS_components['v-form']} */
    vForm;
    // @ts-ignore
    const __VLS_25 = __VLS_asFunctionalComponent1(__VLS_24, new __VLS_24({
        // @ts-ignore
        ref: "form",
    }));
    const __VLS_26 = __VLS_25({
        ref: "form",
    }, ...__VLS_functionalComponentArgsRest(__VLS_25));
    var __VLS_27;
    const { default: __VLS_29 } = __VLS_nonNull(__VLS_27.slots);
    const __VLS_30 = __VLS_tryAsConstant((__VLS_unwrap(localWeights, {})));
    for (const [coin] of __VLS_vFor(__VLS_nonNull(__VLS_30))) {
        let __VLS_31;
        /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
        vRow;
        // @ts-ignore
        const __VLS_32 = __VLS_asFunctionalComponent1(__VLS_31, new __VLS_31({
            // @ts-ignore
            key: (coin.symbol), ...{ class: "align-center" },
        }));
        const __VLS_33 = __VLS_32({
            key: (coin.symbol),
            ...{ class: "align-center" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_32));
        /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
        var __VLS_34;
        const { default: __VLS_36 } = __VLS_nonNull(__VLS_34.slots);
        let __VLS_37;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_38 = __VLS_asFunctionalComponent1(__VLS_37, new __VLS_37({
            // @ts-ignore
            cols: "4",
        }));
        const __VLS_39 = __VLS_38({
            cols: "4",
        }, ...__VLS_functionalComponentArgsRest(__VLS_38));
        var __VLS_40;
        const { default: __VLS_42 } = __VLS_nonNull(__VLS_40.slots);
        let __VLS_43;
        /** @ts-ignore @type { | typeof __VLS_components.vLabel | typeof __VLS_components.VLabel | typeof __VLS_components['v-label'] | typeof __VLS_components.vLabel | typeof __VLS_components.VLabel | typeof __VLS_components['v-label']} */
        vLabel;
        // @ts-ignore
        const __VLS_44 = __VLS_asFunctionalComponent1(__VLS_43, new __VLS_43({
        // @ts-ignore
        }));
        const __VLS_45 = __VLS_44({}, ...__VLS_functionalComponentArgsRest(__VLS_44));
        var __VLS_46;
        const { default: __VLS_48 } = __VLS_nonNull(__VLS_46.slots);
        (coin.symbol);
        // @ts-ignore
        [localWeights,];
        // @ts-ignore
        [];
        let __VLS_49;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_50 = __VLS_asFunctionalComponent1(__VLS_49, new __VLS_49({
            // @ts-ignore
            cols: "8",
        }));
        const __VLS_51 = __VLS_50({
            cols: "8",
        }, ...__VLS_functionalComponentArgsRest(__VLS_50));
        var __VLS_52;
        const { default: __VLS_54 } = __VLS_nonNull(__VLS_52.slots);
        let __VLS_55;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_56 = __VLS_asFunctionalComponent1(__VLS_55, new __VLS_55({
            // @ts-ignore
            ...{ 'onInput': {} }, modelValue: (coin.weight), modelModifiers: { number: true, }, type: "number", variant: "outlined", density: "compact", suffix: "%", hideDetails: true,
        }));
        const __VLS_57 = __VLS_56({
            ...{ 'onInput': {} },
            modelValue: (coin.weight),
            modelModifiers: { number: true, },
            type: "number",
            variant: "outlined",
            density: "compact",
            suffix: "%",
            hideDetails: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_56));
        let __VLS_60;
        const __VLS_61 = {
            /** @type {typeof __VLS_60.input} */
            onInput: (...[$event]) => {
                void $event;
                return (__VLS_unwrap(recalculateWeights, {})(coin.symbol));
                // @ts-ignore
                [recalculateWeights,];
            },
        };
        void __VLS_61;
        var __VLS_58;
        var __VLS_59;
        // @ts-ignore
        [];
        // @ts-ignore
        [];
        // @ts-ignore
        [];
    }
    // @ts-ignore
    [];
    let __VLS_62;
    /** @ts-ignore @type { | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider'] | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider']} */
    vDivider;
    // @ts-ignore
    const __VLS_63 = __VLS_asFunctionalComponent1(__VLS_62, new __VLS_62({
        // @ts-ignore
        ...{ class: "my-4" },
    }));
    const __VLS_64 = __VLS_63({
        ...{ class: "my-4" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_63));
    /** @type {__VLS_StyleScopedClasses['my-4']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "d-flex justify-space-between" },
    });
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['justify-space-between']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
        ...{ class: "font-weight-bold" },
    });
    /** @type {__VLS_StyleScopedClasses['font-weight-bold']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
        ...{ class: (Math.abs(totalWeight.value - 100) < 0.001 ? 'text-success' : 'text-error') },
    });
    (totalWeight.value.toFixed(2));
    // @ts-ignore
    [totalWeight, totalWeight,];
    let __VLS_67;
    /** @ts-ignore @type { | typeof __VLS_components.vCardActions | typeof __VLS_components.VCardActions | typeof __VLS_components['v-card-actions'] | typeof __VLS_components.vCardActions | typeof __VLS_components.VCardActions | typeof __VLS_components['v-card-actions']} */
    vCardActions;
    // @ts-ignore
    const __VLS_68 = __VLS_asFunctionalComponent1(__VLS_67, new __VLS_67({
    // @ts-ignore
    }));
    const __VLS_69 = __VLS_68({}, ...__VLS_functionalComponentArgsRest(__VLS_68));
    var __VLS_70;
    const { default: __VLS_72 } = __VLS_nonNull(__VLS_70.slots);
    let __VLS_73;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_74 = __VLS_asFunctionalComponent1(__VLS_73, new __VLS_73({
        // @ts-ignore
        ...{ 'onClick': {} }, color: "primary", variant: "text",
    }));
    const __VLS_75 = __VLS_74({
        ...{ 'onClick': {} },
        color: "primary",
        variant: "text",
    }, ...__VLS_functionalComponentArgsRest(__VLS_74));
    let __VLS_78;
    const __VLS_79 = {
        /** @type {typeof __VLS_78.click} */
        onClick: (__VLS_unwrap(resetAndUnlock, {})),
    };
    void __VLS_79;
    var __VLS_76;
    var __VLS_77;
    const { default: __VLS_80 } = __VLS_nonNull(__VLS_76.slots);
    // @ts-ignore
    [resetAndUnlock,];
    let __VLS_81;
    /** @ts-ignore @type { | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer'] | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer']} */
    vSpacer;
    // @ts-ignore
    const __VLS_82 = __VLS_asFunctionalComponent1(__VLS_81, new __VLS_81({
    // @ts-ignore
    }));
    const __VLS_83 = __VLS_82({}, ...__VLS_functionalComponentArgsRest(__VLS_82));
    let __VLS_86;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_87 = __VLS_asFunctionalComponent1(__VLS_86, new __VLS_86({
        // @ts-ignore
        ...{ 'onClick': {} }, color: "blue-darken-1", variant: "text",
    }));
    const __VLS_88 = __VLS_87({
        ...{ 'onClick': {} },
        color: "blue-darken-1",
        variant: "text",
    }, ...__VLS_functionalComponentArgsRest(__VLS_87));
    let __VLS_91;
    const __VLS_92 = {
        /** @type {typeof __VLS_91.click} */
        onClick: (__VLS_unwrap(close, {})),
    };
    void __VLS_92;
    var __VLS_89;
    var __VLS_90;
    const { default: __VLS_93 } = __VLS_nonNull(__VLS_89.slots);
    // @ts-ignore
    [close,];
    let __VLS_94;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_95 = __VLS_asFunctionalComponent1(__VLS_94, new __VLS_94({
        // @ts-ignore
        ...{ 'onClick': {} }, color: "blue-darken-1", variant: "tonal", disabled: (Math.abs(totalWeight.value - 100) > 0.001),
    }));
    const __VLS_96 = __VLS_95({
        ...{ 'onClick': {} },
        color: "blue-darken-1",
        variant: "tonal",
        disabled: (Math.abs(totalWeight.value - 100) > 0.001),
    }, ...__VLS_functionalComponentArgsRest(__VLS_95));
    let __VLS_99;
    const __VLS_100 = {
        /** @type {typeof __VLS_99.click} */
        onClick: (__VLS_unwrap(save, {})),
    };
    void __VLS_100;
    var __VLS_97;
    var __VLS_98;
    const { default: __VLS_101 } = __VLS_nonNull(__VLS_97.slots);
    // @ts-ignore
    [totalWeight, save,];
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    return {};
};
void [__VLS_template];
const __VLS_export = (await import('vue')).defineComponent({
    emits: {},
    __typeProps: {},
});
export default {};
