import { ref, computed, watch } from 'vue';
import SmartSelect from '@/components/SmartSelect.vue';
import { useSettingsStore } from '@/stores/settingsStore';
import { useSnackbarStore } from '@/stores/snackbar';
import apiClient from '@/services/api';
import { debounce } from '@/utils/debounce';
import { getErrorMessage } from '@/utils/errors';
const { defineExpose, } = {};
const settingsStore = useSettingsStore();
const snackbarStore = useSnackbarStore();
const MAX_VISIBLE_CHIPS = 3;
const isLongPoolExpanded = ref(false);
const isShortPoolExpanded = ref(false);
const longPoolShowAll = ref(false);
const shortPoolShowAll = ref(false);
const newCoinSymbol = ref('');
const isAddingCoin = ref(false);
// --- 核心修正：创建一个带防抖的保存函数 ---
const savePoolsDebounced = debounce(() => {
    savePools(true); // 传入一个参数标记为自动保存
}, 1500);
// --- 核心修正：增加 watch 侦听器来触发自动保存 ---
watch(() => settingsStore.availableLongCoins, () => {
    savePoolsDebounced();
}, { deep: true });
watch(() => settingsStore.availableShortCoins, () => {
    savePoolsDebounced();
}, { deep: true });
watch(newCoinSymbol, (newValue) => {
    if (newValue && newValue !== newValue.toUpperCase()) {
        newCoinSymbol.value = newValue.toUpperCase();
    }
});
const removePoolItemValue = (poolType, value) => {
    const pool = poolType === 'long'
        ? settingsStore.availableLongCoins
        : settingsStore.availableShortCoins;
    const index = pool.indexOf(value);
    if (index >= 0) {
        pool.splice(index, 1);
    }
};
const allAvailableCoins = computed(() => [...new Set(settingsStore.availableCoins)].sort());
const mapToSelectItems = (coins) => coins.map((coin) => ({ title: coin, value: coin }));
const availableForLongPool = computed(() => {
    const shortSet = new Set(settingsStore.availableShortCoins);
    return mapToSelectItems(allAvailableCoins.value.filter((coin) => !shortSet.has(coin)));
});
const availableForShortPool = computed(() => {
    const longSet = new Set(settingsStore.availableLongCoins);
    return mapToSelectItems(allAvailableCoins.value.filter((coin) => !longSet.has(coin)));
});
// SmartSelect 回写（多选）：保持池子为字符串数组
const setAvailableLongCoins = (value) => {
    settingsStore.availableLongCoins = Array.isArray(value) ? value.map(String) : [];
};
const setAvailableShortCoins = (value) => {
    settingsStore.availableShortCoins = Array.isArray(value) ? value.map(String) : [];
};
const selectAllCoins = (poolType) => {
    if (poolType === 'long') {
        settingsStore.availableLongCoins = availableForLongPool.value.map((item) => item.value);
    }
    else if (poolType === 'short') {
        settingsStore.availableShortCoins = availableForShortPool.value.map((item) => item.value);
    }
};
const savePools = async (isAutoSave = false) => {
    try {
        await apiClient.post('/api/settings/update-coin-pools', {
            long_coins_pool: settingsStore.availableLongCoins,
            short_coins_pool: settingsStore.availableShortCoins,
        });
        if (!isAutoSave) {
            snackbarStore.show({ message: '币种备选池已成功保存。', color: 'success' });
        }
        else {
            console.log("Coin pools auto-saved successfully.");
        }
    }
    catch (error) {
        snackbarStore.show({ message: `保存币种备选池失败: ${getErrorMessage(error)}`, color: 'error' });
    }
};
const addCoin = async () => {
    const symbol = newCoinSymbol.value.trim();
    if (!symbol || isAddingCoin.value)
        return;
    isAddingCoin.value = true;
    try {
        const response = await apiClient.post('/api/settings/add-coin', { coin: symbol });
        settingsStore.availableCoins.splice(0, settingsStore.availableCoins.length, ...response.data);
        newCoinSymbol.value = '';
        snackbarStore.show({ message: `币种 '${symbol}' 添加成功！`, color: 'success' });
    }
    catch (error) {
        snackbarStore.show({ message: `添加失败: ${getErrorMessage(error)}`, color: 'error' });
    }
    finally {
        isAddingCoin.value = false;
    }
};
watch(() => settingsStore.availableLongCoins, (newList) => {
    if (newList) {
        if (newList.length <= MAX_VISIBLE_CHIPS) {
            isLongPoolExpanded.value = false;
        }
        newList.sort();
    }
}, { deep: true });
watch(() => settingsStore.availableShortCoins, (newList) => {
    if (newList) {
        if (newList.length <= MAX_VISIBLE_CHIPS) {
            isShortPoolExpanded.value = false;
        }
        newList.sort();
    }
}, { deep: true });
// 让父组件可以通过 ref 调用手动保存
const __VLS_exposed = { savePools };
defineExpose(__VLS_exposed);
const __VLS_ctx = {};
let __VLS_components;
let __VLS_intrinsics;
let __VLS_directives;
void __VLS_ctx, __VLS_components, __VLS_intrinsics, __VLS_directives;
const __VLS_template = () => {
    __VLS_withDotValue(newCoinSymbol, {});
    __VLS_withDotValue(settingsStore, {});
    void {};
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
    let __VLS_0;
    /** @ts-ignore @type { | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card'] | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card']} */
    vCard;
    // @ts-ignore
    const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
        // @ts-ignore
        variant: "outlined", ...{ class: "mb-6" },
    }));
    const __VLS_2 = __VLS_1({
        variant: "outlined",
        ...{ class: "mb-6" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_1));
    /** @type {__VLS_StyleScopedClasses['mb-6']} */ ;
    var __VLS_3;
    const { default: __VLS_5 } = __VLS_nonNull(__VLS_3.slots);
    let __VLS_6;
    /** @ts-ignore @type { | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title'] | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title']} */
    vCardTitle;
    // @ts-ignore
    const __VLS_7 = __VLS_asFunctionalComponent1(__VLS_6, new __VLS_6({
        // @ts-ignore
        ...{ class: "text-subtitle-1 font-weight-medium d-flex align-center" },
    }));
    const __VLS_8 = __VLS_7({
        ...{ class: "text-subtitle-1 font-weight-medium d-flex align-center" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_7));
    /** @type {__VLS_StyleScopedClasses['text-subtitle-1']} */ ;
    /** @type {__VLS_StyleScopedClasses['font-weight-medium']} */ ;
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
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
    /** @ts-ignore @type { | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider'] | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider']} */
    vDivider;
    // @ts-ignore
    const __VLS_19 = __VLS_asFunctionalComponent1(__VLS_18, new __VLS_18({
    // @ts-ignore
    }));
    const __VLS_20 = __VLS_19({}, ...__VLS_functionalComponentArgsRest(__VLS_19));
    let __VLS_23;
    /** @ts-ignore @type { | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text'] | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text']} */
    vCardText;
    // @ts-ignore
    const __VLS_24 = __VLS_asFunctionalComponent1(__VLS_23, new __VLS_23({
    // @ts-ignore
    }));
    const __VLS_25 = __VLS_24({}, ...__VLS_functionalComponentArgsRest(__VLS_24));
    var __VLS_26;
    const { default: __VLS_28 } = __VLS_nonNull(__VLS_26.slots);
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "d-flex align-center" },
    });
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
    let __VLS_29;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_30 = __VLS_asFunctionalComponent1(__VLS_29, new __VLS_29({
        // @ts-ignore
        ...{ 'onKeyup': {} }, modelValue: (newCoinSymbol.value), label: "输入币种代码 (例如: btc)", variant: "outlined", density: "compact", hideDetails: true, ...{ class: "mr-4" }, autofocus: true,
    }));
    const __VLS_31 = __VLS_30({
        ...{ 'onKeyup': {} },
        modelValue: (newCoinSymbol.value),
        label: "输入币种代码 (例如: btc)",
        variant: "outlined",
        density: "compact",
        hideDetails: true,
        ...{ class: "mr-4" },
        autofocus: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_30));
    let __VLS_34;
    const __VLS_35 = {
        /** @type {typeof __VLS_34.keyup} */
        onKeyup: (__VLS_unwrap(addCoin, {})),
    };
    void __VLS_35;
    /** @type {__VLS_StyleScopedClasses['mr-4']} */ ;
    var __VLS_32;
    var __VLS_33;
    let __VLS_36;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_37 = __VLS_asFunctionalComponent1(__VLS_36, new __VLS_36({
        // @ts-ignore
        ...{ 'onClick': {} }, color: "primary", variant: "tonal", loading: (__VLS_unwrap(isAddingCoin, {})), disabled: (!newCoinSymbol.value.trim()), prependIcon: "mdi-plus",
    }));
    const __VLS_38 = __VLS_37({
        ...{ 'onClick': {} },
        color: "primary",
        variant: "tonal",
        loading: (__VLS_unwrap(isAddingCoin, {})),
        disabled: (!newCoinSymbol.value.trim()),
        prependIcon: "mdi-plus",
    }, ...__VLS_functionalComponentArgsRest(__VLS_37));
    let __VLS_41;
    const __VLS_42 = {
        /** @type {typeof __VLS_41.click} */
        onClick: (__VLS_unwrap(addCoin, {})),
    };
    void __VLS_42;
    var __VLS_39;
    var __VLS_40;
    const { default: __VLS_43 } = __VLS_nonNull(__VLS_39.slots);
    // @ts-ignore
    [newCoinSymbol, newCoinSymbol, addCoin, addCoin, isAddingCoin,];
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "text-caption text-grey mt-2" },
    });
    /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
    /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
    /** @type {__VLS_StyleScopedClasses['mt-2']} */ ;
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    let __VLS_44;
    /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
    vRow;
    // @ts-ignore
    const __VLS_45 = __VLS_asFunctionalComponent1(__VLS_44, new __VLS_44({
    // @ts-ignore
    }));
    const __VLS_46 = __VLS_45({}, ...__VLS_functionalComponentArgsRest(__VLS_45));
    var __VLS_47;
    const { default: __VLS_49 } = __VLS_nonNull(__VLS_47.slots);
    let __VLS_50;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_51 = __VLS_asFunctionalComponent1(__VLS_50, new __VLS_50({
        // @ts-ignore
        cols: "12", md: "6",
    }));
    const __VLS_52 = __VLS_51({
        cols: "12",
        md: "6",
    }, ...__VLS_functionalComponentArgsRest(__VLS_51));
    var __VLS_53;
    const { default: __VLS_55 } = __VLS_nonNull(__VLS_53.slots);
    let __VLS_56;
    /** @ts-ignore @type { | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card'] | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card']} */
    vCard;
    // @ts-ignore
    const __VLS_57 = __VLS_asFunctionalComponent1(__VLS_56, new __VLS_56({
        // @ts-ignore
        variant: "tonal", ...{ class: "pa-4" }, ...{ style: {} },
    }));
    const __VLS_58 = __VLS_57({
        variant: "tonal",
        ...{ class: "pa-4" },
        ...{ style: {} },
    }, ...__VLS_functionalComponentArgsRest(__VLS_57));
    /** @type {__VLS_StyleScopedClasses['pa-4']} */ ;
    var __VLS_59;
    const { default: __VLS_61 } = __VLS_nonNull(__VLS_59.slots);
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "d-flex align-center mb-2" },
    });
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
    /** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
        ...{ class: "text-subtitle-1 font-weight-medium" },
    });
    /** @type {__VLS_StyleScopedClasses['text-subtitle-1']} */ ;
    /** @type {__VLS_StyleScopedClasses['font-weight-medium']} */ ;
    (settingsStore.value.availableLongCoins.length);
    let __VLS_62;
    /** @ts-ignore @type { | typeof __VLS_components.vTooltip | typeof __VLS_components.VTooltip | typeof __VLS_components['v-tooltip'] | typeof __VLS_components.vTooltip | typeof __VLS_components.VTooltip | typeof __VLS_components['v-tooltip']} */
    vTooltip;
    // @ts-ignore
    const __VLS_63 = __VLS_asFunctionalComponent1(__VLS_62, new __VLS_62({
        // @ts-ignore
        location: "top",
    }));
    const __VLS_64 = __VLS_63({
        location: "top",
    }, ...__VLS_functionalComponentArgsRest(__VLS_63));
    var __VLS_65;
    const { default: __VLS_67 } = __VLS_nonNull(__VLS_65.slots);
    {
        const { activator: __VLS_68 } = __VLS_nonNull(__VLS_65.slots);
        const [{ props }] = __VLS_vSlot(__VLS_nonNull(__VLS_68));
        let __VLS_69;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_70 = __VLS_asFunctionalComponent1(__VLS_69, new __VLS_69({
            // @ts-ignore
            ...{ 'onClick': {} }, icon: "mdi-select-all", variant: "text", size: "small", ...(props),
        }));
        const __VLS_71 = __VLS_70({
            ...{ 'onClick': {} },
            icon: "mdi-select-all",
            variant: "text",
            size: "small",
            ...(props),
        }, ...__VLS_functionalComponentArgsRest(__VLS_70));
        let __VLS_74;
        const __VLS_75 = {
            /** @type {typeof __VLS_74.click} */
            onClick: (...[$event]) => {
                void $event;
                return (__VLS_unwrap(selectAllCoins, {})('long'));
                // @ts-ignore
                [settingsStore, selectAllCoins,];
            },
        };
        void __VLS_75;
        var __VLS_72;
        var __VLS_73;
        // @ts-ignore
        [];
    }
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    // @ts-ignore
    [];
    const __VLS_76 = SmartSelect || SmartSelect;
    // @ts-ignore
    const __VLS_77 = __VLS_asFunctionalComponent1(__VLS_76, new __VLS_76({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (settingsStore.value.availableLongCoins), items: (__VLS_unwrap(availableForLongPool, {})), label: "从总池中选择做多备选币种（可搜索）", multiple: true, clearable: true, searchable: true,
    }));
    const __VLS_78 = __VLS_77({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (settingsStore.value.availableLongCoins),
        items: (__VLS_unwrap(availableForLongPool, {})),
        label: "从总池中选择做多备选币种（可搜索）",
        multiple: true,
        clearable: true,
        searchable: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_77));
    let __VLS_81;
    const __VLS_82 = {
        /** @type {typeof __VLS_81.'update:modelValue'} */
        'onUpdate:modelValue': (__VLS_unwrap(setAvailableLongCoins, {})),
    };
    void __VLS_82;
    var __VLS_79;
    var __VLS_80;
    // @ts-ignore
    [settingsStore, availableForLongPool, setAvailableLongCoins,];
    // @ts-ignore
    [];
    let __VLS_83;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_84 = __VLS_asFunctionalComponent1(__VLS_83, new __VLS_83({
        // @ts-ignore
        cols: "12", md: "6",
    }));
    const __VLS_85 = __VLS_84({
        cols: "12",
        md: "6",
    }, ...__VLS_functionalComponentArgsRest(__VLS_84));
    var __VLS_86;
    const { default: __VLS_88 } = __VLS_nonNull(__VLS_86.slots);
    let __VLS_89;
    /** @ts-ignore @type { | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card'] | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card']} */
    vCard;
    // @ts-ignore
    const __VLS_90 = __VLS_asFunctionalComponent1(__VLS_89, new __VLS_89({
        // @ts-ignore
        variant: "tonal", ...{ class: "pa-4" }, ...{ style: {} },
    }));
    const __VLS_91 = __VLS_90({
        variant: "tonal",
        ...{ class: "pa-4" },
        ...{ style: {} },
    }, ...__VLS_functionalComponentArgsRest(__VLS_90));
    /** @type {__VLS_StyleScopedClasses['pa-4']} */ ;
    var __VLS_92;
    const { default: __VLS_94 } = __VLS_nonNull(__VLS_92.slots);
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "d-flex align-center mb-2" },
    });
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
    /** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
        ...{ class: "text-subtitle-1 font-weight-medium" },
    });
    /** @type {__VLS_StyleScopedClasses['text-subtitle-1']} */ ;
    /** @type {__VLS_StyleScopedClasses['font-weight-medium']} */ ;
    (settingsStore.value.availableShortCoins.length);
    let __VLS_95;
    /** @ts-ignore @type { | typeof __VLS_components.vTooltip | typeof __VLS_components.VTooltip | typeof __VLS_components['v-tooltip'] | typeof __VLS_components.vTooltip | typeof __VLS_components.VTooltip | typeof __VLS_components['v-tooltip']} */
    vTooltip;
    // @ts-ignore
    const __VLS_96 = __VLS_asFunctionalComponent1(__VLS_95, new __VLS_95({
        // @ts-ignore
        location: "top",
    }));
    const __VLS_97 = __VLS_96({
        location: "top",
    }, ...__VLS_functionalComponentArgsRest(__VLS_96));
    var __VLS_98;
    const { default: __VLS_100 } = __VLS_nonNull(__VLS_98.slots);
    {
        const { activator: __VLS_101 } = __VLS_nonNull(__VLS_98.slots);
        const [{ props }] = __VLS_vSlot(__VLS_nonNull(__VLS_101));
        let __VLS_102;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_103 = __VLS_asFunctionalComponent1(__VLS_102, new __VLS_102({
            // @ts-ignore
            ...{ 'onClick': {} }, icon: "mdi-select-all", variant: "text", size: "small", ...(props),
        }));
        const __VLS_104 = __VLS_103({
            ...{ 'onClick': {} },
            icon: "mdi-select-all",
            variant: "text",
            size: "small",
            ...(props),
        }, ...__VLS_functionalComponentArgsRest(__VLS_103));
        let __VLS_107;
        const __VLS_108 = {
            /** @type {typeof __VLS_107.click} */
            onClick: (...[$event]) => {
                void $event;
                return (__VLS_unwrap(selectAllCoins, {})('short'));
                // @ts-ignore
                [settingsStore, selectAllCoins,];
            },
        };
        void __VLS_108;
        var __VLS_105;
        var __VLS_106;
        // @ts-ignore
        [];
    }
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    // @ts-ignore
    [];
    const __VLS_109 = SmartSelect || SmartSelect;
    // @ts-ignore
    const __VLS_110 = __VLS_asFunctionalComponent1(__VLS_109, new __VLS_109({
        // @ts-ignore
        ...{ 'onUpdate:modelValue': {} }, modelValue: (settingsStore.value.availableShortCoins), items: (__VLS_unwrap(availableForShortPool, {})), label: "从总池中选择做空备选币种（可搜索）", multiple: true, clearable: true, searchable: true,
    }));
    const __VLS_111 = __VLS_110({
        ...{ 'onUpdate:modelValue': {} },
        modelValue: (settingsStore.value.availableShortCoins),
        items: (__VLS_unwrap(availableForShortPool, {})),
        label: "从总池中选择做空备选币种（可搜索）",
        multiple: true,
        clearable: true,
        searchable: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_110));
    let __VLS_114;
    const __VLS_115 = {
        /** @type {typeof __VLS_114.'update:modelValue'} */
        'onUpdate:modelValue': (__VLS_unwrap(setAvailableShortCoins, {})),
    };
    void __VLS_115;
    var __VLS_112;
    var __VLS_113;
    // @ts-ignore
    [settingsStore, availableForShortPool, setAvailableShortCoins,];
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
    setup: () => __VLS_exposed,
});
export default {};
