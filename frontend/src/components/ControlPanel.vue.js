import { ref, watch, computed } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUiStore } from '@/stores/uiStore';
import { debounce } from '@/utils/debounce';
import SmartSelect from '@/components/SmartSelect.vue';
const { defineModel, } = {};
const modelValue = defineModel();
const settingsStore = useSettingsStore();
const uiStore = useUiStore();
const MAX_VISIBLE_CHIPS = 3;
const isLongListExpanded = ref(false);
const isShortListExpanded = ref(false);
const longListShowAll = ref(false);
const shortListShowAll = ref(false);
// 多/空交易币种从各自备选池中选择；v-autocomplete 自带搜索过滤，无需手工过滤
const longListItems = computed(() => [...settingsStore.availableLongCoins].sort());
const shortListItems = computed(() => [...settingsStore.availableShortCoins].sort());
const removeListItemValue = (listType, value) => {
    if (!settingsStore.settings)
        return;
    const list = listType === 'long'
        ? settingsStore.settings.long_coin_list
        : settingsStore.settings.short_coin_list;
    const index = list.indexOf(value);
    if (index >= 0) {
        list.splice(index, 1);
    }
};
// SmartSelect 回写：settings 可能为 null（未加载完成），这里统一兜底
const toList = (value) => Array.isArray(value) ? value.map(String) : [];
const setLongCoinList = (value) => {
    if (!settingsStore.settings)
        return;
    settingsStore.settings.long_coin_list = toList(value);
};
const setShortCoinList = (value) => {
    if (!settingsStore.settings)
        return;
    settingsStore.settings.short_coin_list = toList(value);
};
const setBenchmarkCoins = (value) => {
    if (!settingsStore.settings)
        return;
    settingsStore.settings.rebalance_benchmark_coin = toList(value);
};
const rebalanceMethods = [{ value: 'multi_factor_weakest', text: '多因子弱势策略' }];
const saveSettingsDebounced = debounce(() => {
    if (settingsStore.settings) {
        settingsStore.saveGeneralSettings(settingsStore.settings);
    }
}, 1500);
watch(() => settingsStore.settings, () => {
    saveSettingsDebounced();
}, { deep: true });
watch(() => settingsStore.settings?.long_coin_list, (newList) => {
    if (newList) {
        if (newList.length <= MAX_VISIBLE_CHIPS) {
            isLongListExpanded.value = false;
        }
        newList.sort();
    }
}, { deep: true });
watch(() => settingsStore.settings?.short_coin_list, (newList) => {
    if (newList) {
        if (newList.length <= MAX_VISIBLE_CHIPS) {
            isShortListExpanded.value = false;
        }
        newList.sort();
    }
}, { deep: true });
let __VLS_modelEmit;
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
    __VLS_withDotValue(settingsStore, {});
    __VLS_withDotValue(uiStore, {});
    void {};
    if (settingsStore.value.settings) {
        let __VLS_0;
        /** @ts-ignore @type { | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card'] | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card']} */
        vCard;
        // @ts-ignore
        const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
        // @ts-ignore
        }));
        const __VLS_2 = __VLS_1({}, ...__VLS_functionalComponentArgsRest(__VLS_1));
        var __VLS_3;
        const { default: __VLS_5 } = __VLS_nonNull(__VLS_3.slots);
        let __VLS_6;
        /** @ts-ignore @type { | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title'] | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title']} */
        vCardTitle;
        // @ts-ignore
        const __VLS_7 = __VLS_asFunctionalComponent1(__VLS_6, new __VLS_6({
            // @ts-ignore
            ...{ class: "text-h6" },
        }));
        const __VLS_8 = __VLS_7({
            ...{ class: "text-h6" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_7));
        /** @type {__VLS_StyleScopedClasses['text-h6']} */ ;
        var __VLS_9;
        const { default: __VLS_11 } = __VLS_nonNull(__VLS_9.slots);
        // @ts-ignore
        [settingsStore,];
        let __VLS_12;
        /** @ts-ignore @type { | typeof __VLS_components.vTabs | typeof __VLS_components.VTabs | typeof __VLS_components['v-tabs'] | typeof __VLS_components.vTabs | typeof __VLS_components.VTabs | typeof __VLS_components['v-tabs']} */
        vTabs;
        // @ts-ignore
        const __VLS_13 = __VLS_asFunctionalComponent1(__VLS_12, new __VLS_12({
            // @ts-ignore
            modelValue: (__VLS_unwrap(modelValue, {})), bgColor: "primary",
        }));
        const __VLS_14 = __VLS_13({
            modelValue: (__VLS_unwrap(modelValue, {})),
            bgColor: "primary",
        }, ...__VLS_functionalComponentArgsRest(__VLS_13));
        var __VLS_15;
        const { default: __VLS_17 } = __VLS_nonNull(__VLS_15.slots);
        let __VLS_18;
        /** @ts-ignore @type { | typeof __VLS_components.vTab | typeof __VLS_components.VTab | typeof __VLS_components['v-tab'] | typeof __VLS_components.vTab | typeof __VLS_components.VTab | typeof __VLS_components['v-tab']} */
        vTab;
        // @ts-ignore
        const __VLS_19 = __VLS_asFunctionalComponent1(__VLS_18, new __VLS_18({
            // @ts-ignore
            value: "general",
        }));
        const __VLS_20 = __VLS_19({
            value: "general",
        }, ...__VLS_functionalComponentArgsRest(__VLS_19));
        var __VLS_21;
        const { default: __VLS_23 } = __VLS_nonNull(__VLS_21.slots);
        // @ts-ignore
        [modelValue,];
        let __VLS_24;
        /** @ts-ignore @type { | typeof __VLS_components.vTab | typeof __VLS_components.VTab | typeof __VLS_components['v-tab'] | typeof __VLS_components.vTab | typeof __VLS_components.VTab | typeof __VLS_components['v-tab']} */
        vTab;
        // @ts-ignore
        const __VLS_25 = __VLS_asFunctionalComponent1(__VLS_24, new __VLS_24({
            // @ts-ignore
            value: "rebalance",
        }));
        const __VLS_26 = __VLS_25({
            value: "rebalance",
        }, ...__VLS_functionalComponentArgsRest(__VLS_25));
        var __VLS_27;
        const { default: __VLS_29 } = __VLS_nonNull(__VLS_27.slots);
        // @ts-ignore
        [];
        // @ts-ignore
        [];
        let __VLS_30;
        /** @ts-ignore @type { | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text'] | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text']} */
        vCardText;
        // @ts-ignore
        const __VLS_31 = __VLS_asFunctionalComponent1(__VLS_30, new __VLS_30({
        // @ts-ignore
        }));
        const __VLS_32 = __VLS_31({}, ...__VLS_functionalComponentArgsRest(__VLS_31));
        var __VLS_33;
        const { default: __VLS_35 } = __VLS_nonNull(__VLS_33.slots);
        let __VLS_36;
        /** @ts-ignore @type { | typeof __VLS_components.vWindow | typeof __VLS_components.VWindow | typeof __VLS_components['v-window'] | typeof __VLS_components.vWindow | typeof __VLS_components.VWindow | typeof __VLS_components['v-window']} */
        vWindow;
        // @ts-ignore
        const __VLS_37 = __VLS_asFunctionalComponent1(__VLS_36, new __VLS_36({
            // @ts-ignore
            modelValue: (__VLS_unwrap(modelValue, {})),
        }));
        const __VLS_38 = __VLS_37({
            modelValue: (__VLS_unwrap(modelValue, {})),
        }, ...__VLS_functionalComponentArgsRest(__VLS_37));
        var __VLS_39;
        const { default: __VLS_41 } = __VLS_nonNull(__VLS_39.slots);
        let __VLS_42;
        /** @ts-ignore @type { | typeof __VLS_components.vWindowItem | typeof __VLS_components.VWindowItem | typeof __VLS_components['v-window-item'] | typeof __VLS_components.vWindowItem | typeof __VLS_components.VWindowItem | typeof __VLS_components['v-window-item']} */
        vWindowItem;
        // @ts-ignore
        const __VLS_43 = __VLS_asFunctionalComponent1(__VLS_42, new __VLS_42({
            // @ts-ignore
            value: "general",
        }));
        const __VLS_44 = __VLS_43({
            value: "general",
        }, ...__VLS_functionalComponentArgsRest(__VLS_43));
        var __VLS_45;
        const { default: __VLS_47 } = __VLS_nonNull(__VLS_45.slots);
        let __VLS_48;
        /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
        vRow;
        // @ts-ignore
        const __VLS_49 = __VLS_asFunctionalComponent1(__VLS_48, new __VLS_48({
        // @ts-ignore
        }));
        const __VLS_50 = __VLS_49({}, ...__VLS_functionalComponentArgsRest(__VLS_49));
        var __VLS_51;
        const { default: __VLS_53 } = __VLS_nonNull(__VLS_51.slots);
        let __VLS_54;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_55 = __VLS_asFunctionalComponent1(__VLS_54, new __VLS_54({
            // @ts-ignore
            cols: "12", md: "6",
        }));
        const __VLS_56 = __VLS_55({
            cols: "12",
            md: "6",
        }, ...__VLS_functionalComponentArgsRest(__VLS_55));
        var __VLS_57;
        const { default: __VLS_59 } = __VLS_nonNull(__VLS_57.slots);
        let __VLS_60;
        /** @ts-ignore @type { | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card'] | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card']} */
        vCard;
        // @ts-ignore
        const __VLS_61 = __VLS_asFunctionalComponent1(__VLS_60, new __VLS_60({
            // @ts-ignore
            variant: "outlined", ...{ class: "d-flex flex-column" }, ...{ style: {} },
        }));
        const __VLS_62 = __VLS_61({
            variant: "outlined",
            ...{ class: "d-flex flex-column" },
            ...{ style: {} },
        }, ...__VLS_functionalComponentArgsRest(__VLS_61));
        /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
        /** @type {__VLS_StyleScopedClasses['flex-column']} */ ;
        var __VLS_63;
        const { default: __VLS_65 } = __VLS_nonNull(__VLS_63.slots);
        let __VLS_66;
        /** @ts-ignore @type { | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title'] | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title']} */
        vCardTitle;
        // @ts-ignore
        const __VLS_67 = __VLS_asFunctionalComponent1(__VLS_66, new __VLS_66({
        // @ts-ignore
        }));
        const __VLS_68 = __VLS_67({}, ...__VLS_functionalComponentArgsRest(__VLS_67));
        var __VLS_69;
        const { default: __VLS_71 } = __VLS_nonNull(__VLS_69.slots);
        // @ts-ignore
        [modelValue,];
        let __VLS_72;
        /** @ts-ignore @type { | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text'] | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text']} */
        vCardText;
        // @ts-ignore
        const __VLS_73 = __VLS_asFunctionalComponent1(__VLS_72, new __VLS_72({
            // @ts-ignore
            ...{ class: "flex-grow-1" },
        }));
        const __VLS_74 = __VLS_73({
            ...{ class: "flex-grow-1" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_73));
        /** @type {__VLS_StyleScopedClasses['flex-grow-1']} */ ;
        var __VLS_75;
        const { default: __VLS_77 } = __VLS_nonNull(__VLS_75.slots);
        let __VLS_78;
        /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch'] | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
        vSwitch;
        // @ts-ignore
        const __VLS_79 = __VLS_asFunctionalComponent1(__VLS_78, new __VLS_78({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.enable_long_trades), label: "开启多头交易", color: "success", inset: true,
        }));
        const __VLS_80 = __VLS_79({
            modelValue: (settingsStore.value.settings.enable_long_trades),
            label: "开启多头交易",
            color: "success",
            inset: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_79));
        let __VLS_83;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_84 = __VLS_asFunctionalComponent1(__VLS_83, new __VLS_83({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.total_long_position_value), modelModifiers: { number: true, }, label: "多头总价值 (USD)", type: "number", disabled: (!settingsStore.value.settings.enable_long_trades),
        }));
        const __VLS_85 = __VLS_84({
            modelValue: (settingsStore.value.settings.total_long_position_value),
            modelModifiers: { number: true, },
            label: "多头总价值 (USD)",
            type: "number",
            disabled: (!settingsStore.value.settings.enable_long_trades),
        }, ...__VLS_functionalComponentArgsRest(__VLS_84));
        const __VLS_88 = SmartSelect || SmartSelect;
        // @ts-ignore
        const __VLS_89 = __VLS_asFunctionalComponent1(__VLS_88, new __VLS_88({
            // @ts-ignore
            ...{ 'onUpdate:modelValue': {} }, modelValue: (settingsStore.value.settings.long_coin_list), items: (__VLS_unwrap(longListItems, {})), label: "从备选池中选择做多币种（可搜索）", multiple: true, clearable: true, searchable: true, disabled: (!settingsStore.value.settings.enable_long_trades),
        }));
        const __VLS_90 = __VLS_89({
            ...{ 'onUpdate:modelValue': {} },
            modelValue: (settingsStore.value.settings.long_coin_list),
            items: (__VLS_unwrap(longListItems, {})),
            label: "从备选池中选择做多币种（可搜索）",
            multiple: true,
            clearable: true,
            searchable: true,
            disabled: (!settingsStore.value.settings.enable_long_trades),
        }, ...__VLS_functionalComponentArgsRest(__VLS_89));
        let __VLS_93;
        const __VLS_94 = {
            /** @type {typeof __VLS_93.'update:modelValue'} */
            'onUpdate:modelValue': (__VLS_unwrap(setLongCoinList, {})),
        };
        void __VLS_94;
        var __VLS_91;
        var __VLS_92;
        let __VLS_95;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_96 = __VLS_asFunctionalComponent1(__VLS_95, new __VLS_95({
            // @ts-ignore
            ...{ 'onClick': {} }, size: "small", disabled: (!settingsStore.value.settings.enable_long_trades),
        }));
        const __VLS_97 = __VLS_96({
            ...{ 'onClick': {} },
            size: "small",
            disabled: (!settingsStore.value.settings.enable_long_trades),
        }, ...__VLS_functionalComponentArgsRest(__VLS_96));
        let __VLS_100;
        const __VLS_101 = {
            /** @type {typeof __VLS_100.click} */
            onClick: (...[$event]) => {
                void $event;
                if (!(settingsStore.value.settings))
                    throw 0;
                return (uiStore.value.showWeightDialog = true);
                // @ts-ignore
                [settingsStore, settingsStore, settingsStore, settingsStore, settingsStore, settingsStore, longListItems, setLongCoinList, uiStore,];
            },
        };
        void __VLS_101;
        var __VLS_98;
        var __VLS_99;
        const { default: __VLS_102 } = __VLS_nonNull(__VLS_98.slots);
        // @ts-ignore
        [];
        let __VLS_103;
        /** @ts-ignore @type { | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider'] | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider']} */
        vDivider;
        // @ts-ignore
        const __VLS_104 = __VLS_asFunctionalComponent1(__VLS_103, new __VLS_103({
            // @ts-ignore
            ...{ class: "my-4" },
        }));
        const __VLS_105 = __VLS_104({
            ...{ class: "my-4" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_104));
        /** @type {__VLS_StyleScopedClasses['my-4']} */ ;
        let __VLS_108;
        /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch'] | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
        vSwitch;
        // @ts-ignore
        const __VLS_109 = __VLS_asFunctionalComponent1(__VLS_108, new __VLS_108({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.enable_long_sl_tp), label: "开启多头固定 SL/TP", color: "info", inset: true, disabled: (!settingsStore.value.settings.enable_long_trades),
        }));
        const __VLS_110 = __VLS_109({
            modelValue: (settingsStore.value.settings.enable_long_sl_tp),
            label: "开启多头固定 SL/TP",
            color: "info",
            inset: true,
            disabled: (!settingsStore.value.settings.enable_long_trades),
        }, ...__VLS_functionalComponentArgsRest(__VLS_109));
        let __VLS_113;
        /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
        vRow;
        // @ts-ignore
        const __VLS_114 = __VLS_asFunctionalComponent1(__VLS_113, new __VLS_113({
            // @ts-ignore
            dense: true,
        }));
        const __VLS_115 = __VLS_114({
            dense: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_114));
        var __VLS_116;
        const { default: __VLS_118 } = __VLS_nonNull(__VLS_116.slots);
        let __VLS_119;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_120 = __VLS_asFunctionalComponent1(__VLS_119, new __VLS_119({
            // @ts-ignore
            cols: "6",
        }));
        const __VLS_121 = __VLS_120({
            cols: "6",
        }, ...__VLS_functionalComponentArgsRest(__VLS_120));
        var __VLS_122;
        const { default: __VLS_124 } = __VLS_nonNull(__VLS_122.slots);
        let __VLS_125;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_126 = __VLS_asFunctionalComponent1(__VLS_125, new __VLS_125({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.long_stop_loss_percentage), modelModifiers: { number: true, }, label: "止损 (%)", type: "number", disabled: (!settingsStore.value.settings.enable_long_sl_tp), hint: "设为0则不设置止损", persistentHint: true,
        }));
        const __VLS_127 = __VLS_126({
            modelValue: (settingsStore.value.settings.long_stop_loss_percentage),
            modelModifiers: { number: true, },
            label: "止损 (%)",
            type: "number",
            disabled: (!settingsStore.value.settings.enable_long_sl_tp),
            hint: "设为0则不设置止损",
            persistentHint: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_126));
        // @ts-ignore
        [settingsStore, settingsStore, settingsStore, settingsStore,];
        let __VLS_130;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_131 = __VLS_asFunctionalComponent1(__VLS_130, new __VLS_130({
            // @ts-ignore
            cols: "6",
        }));
        const __VLS_132 = __VLS_131({
            cols: "6",
        }, ...__VLS_functionalComponentArgsRest(__VLS_131));
        var __VLS_133;
        const { default: __VLS_135 } = __VLS_nonNull(__VLS_133.slots);
        let __VLS_136;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_137 = __VLS_asFunctionalComponent1(__VLS_136, new __VLS_136({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.long_take_profit_percentage), modelModifiers: { number: true, }, label: "止盈 (%)", type: "number", disabled: (!settingsStore.value.settings.enable_long_sl_tp), hint: "设为0则不设置止盈", persistentHint: true,
        }));
        const __VLS_138 = __VLS_137({
            modelValue: (settingsStore.value.settings.long_take_profit_percentage),
            modelModifiers: { number: true, },
            label: "止盈 (%)",
            type: "number",
            disabled: (!settingsStore.value.settings.enable_long_sl_tp),
            hint: "设为0则不设置止盈",
            persistentHint: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_137));
        // @ts-ignore
        [settingsStore, settingsStore,];
        // @ts-ignore
        [];
        let __VLS_141;
        /** @ts-ignore @type { | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider'] | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider']} */
        vDivider;
        // @ts-ignore
        const __VLS_142 = __VLS_asFunctionalComponent1(__VLS_141, new __VLS_141({
            // @ts-ignore
            ...{ class: "my-4" },
        }));
        const __VLS_143 = __VLS_142({
            ...{ class: "my-4" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_142));
        /** @type {__VLS_StyleScopedClasses['my-4']} */ ;
        let __VLS_146;
        /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch'] | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
        vSwitch;
        // @ts-ignore
        const __VLS_147 = __VLS_asFunctionalComponent1(__VLS_146, new __VLS_146({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.enable_long_trailing_stop), label: "开启多头移动止盈 (Trailing)", color: "purple-accent-2", inset: true, disabled: (!settingsStore.value.settings.enable_long_trades),
        }));
        const __VLS_148 = __VLS_147({
            modelValue: (settingsStore.value.settings.enable_long_trailing_stop),
            label: "开启多头移动止盈 (Trailing)",
            color: "purple-accent-2",
            inset: true,
            disabled: (!settingsStore.value.settings.enable_long_trades),
        }, ...__VLS_functionalComponentArgsRest(__VLS_147));
        let __VLS_151;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_152 = __VLS_asFunctionalComponent1(__VLS_151, new __VLS_151({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.long_trailing_stop_callback_rate), modelModifiers: { number: true, }, label: "回调率 (%)", type: "number", step: "0.1", min: "0.1", max: "5.0", disabled: (!settingsStore.value.settings.enable_long_trailing_stop), hint: "价格回撤多少百分比时平仓 (建议 0.5% - 5.0%)", persistentHint: true,
        }));
        const __VLS_153 = __VLS_152({
            modelValue: (settingsStore.value.settings.long_trailing_stop_callback_rate),
            modelModifiers: { number: true, },
            label: "回调率 (%)",
            type: "number",
            step: "0.1",
            min: "0.1",
            max: "5.0",
            disabled: (!settingsStore.value.settings.enable_long_trailing_stop),
            hint: "价格回撤多少百分比时平仓 (建议 0.5% - 5.0%)",
            persistentHint: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_152));
        // @ts-ignore
        [settingsStore, settingsStore, settingsStore, settingsStore,];
        // @ts-ignore
        [];
        // @ts-ignore
        [];
        let __VLS_156;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_157 = __VLS_asFunctionalComponent1(__VLS_156, new __VLS_156({
            // @ts-ignore
            cols: "12", md: "6",
        }));
        const __VLS_158 = __VLS_157({
            cols: "12",
            md: "6",
        }, ...__VLS_functionalComponentArgsRest(__VLS_157));
        var __VLS_159;
        const { default: __VLS_161 } = __VLS_nonNull(__VLS_159.slots);
        let __VLS_162;
        /** @ts-ignore @type { | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card'] | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card']} */
        vCard;
        // @ts-ignore
        const __VLS_163 = __VLS_asFunctionalComponent1(__VLS_162, new __VLS_162({
            // @ts-ignore
            variant: "outlined", ...{ class: "d-flex flex-column" }, ...{ style: {} },
        }));
        const __VLS_164 = __VLS_163({
            variant: "outlined",
            ...{ class: "d-flex flex-column" },
            ...{ style: {} },
        }, ...__VLS_functionalComponentArgsRest(__VLS_163));
        /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
        /** @type {__VLS_StyleScopedClasses['flex-column']} */ ;
        var __VLS_165;
        const { default: __VLS_167 } = __VLS_nonNull(__VLS_165.slots);
        let __VLS_168;
        /** @ts-ignore @type { | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title'] | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title']} */
        vCardTitle;
        // @ts-ignore
        const __VLS_169 = __VLS_asFunctionalComponent1(__VLS_168, new __VLS_168({
        // @ts-ignore
        }));
        const __VLS_170 = __VLS_169({}, ...__VLS_functionalComponentArgsRest(__VLS_169));
        var __VLS_171;
        const { default: __VLS_173 } = __VLS_nonNull(__VLS_171.slots);
        // @ts-ignore
        [];
        let __VLS_174;
        /** @ts-ignore @type { | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text'] | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text']} */
        vCardText;
        // @ts-ignore
        const __VLS_175 = __VLS_asFunctionalComponent1(__VLS_174, new __VLS_174({
            // @ts-ignore
            ...{ class: "flex-grow-1" },
        }));
        const __VLS_176 = __VLS_175({
            ...{ class: "flex-grow-1" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_175));
        /** @type {__VLS_StyleScopedClasses['flex-grow-1']} */ ;
        var __VLS_177;
        const { default: __VLS_179 } = __VLS_nonNull(__VLS_177.slots);
        let __VLS_180;
        /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch'] | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
        vSwitch;
        // @ts-ignore
        const __VLS_181 = __VLS_asFunctionalComponent1(__VLS_180, new __VLS_180({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.enable_short_trades), label: "开启空头交易", color: "error", inset: true,
        }));
        const __VLS_182 = __VLS_181({
            modelValue: (settingsStore.value.settings.enable_short_trades),
            label: "开启空头交易",
            color: "error",
            inset: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_181));
        let __VLS_185;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_186 = __VLS_asFunctionalComponent1(__VLS_185, new __VLS_185({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.total_short_position_value), modelModifiers: { number: true, }, label: "空头总价值 (USD)", type: "number", disabled: (!settingsStore.value.settings.enable_short_trades),
        }));
        const __VLS_187 = __VLS_186({
            modelValue: (settingsStore.value.settings.total_short_position_value),
            modelModifiers: { number: true, },
            label: "空头总价值 (USD)",
            type: "number",
            disabled: (!settingsStore.value.settings.enable_short_trades),
        }, ...__VLS_functionalComponentArgsRest(__VLS_186));
        const __VLS_190 = SmartSelect || SmartSelect;
        // @ts-ignore
        const __VLS_191 = __VLS_asFunctionalComponent1(__VLS_190, new __VLS_190({
            // @ts-ignore
            ...{ 'onUpdate:modelValue': {} }, modelValue: (settingsStore.value.settings.short_coin_list), items: (__VLS_unwrap(shortListItems, {})), label: "从备选池中选择空头币种（可搜索）", multiple: true, clearable: true, searchable: true, disabled: (!settingsStore.value.settings.enable_short_trades),
        }));
        const __VLS_192 = __VLS_191({
            ...{ 'onUpdate:modelValue': {} },
            modelValue: (settingsStore.value.settings.short_coin_list),
            items: (__VLS_unwrap(shortListItems, {})),
            label: "从备选池中选择空头币种（可搜索）",
            multiple: true,
            clearable: true,
            searchable: true,
            disabled: (!settingsStore.value.settings.enable_short_trades),
        }, ...__VLS_functionalComponentArgsRest(__VLS_191));
        let __VLS_195;
        const __VLS_196 = {
            /** @type {typeof __VLS_195.'update:modelValue'} */
            'onUpdate:modelValue': (__VLS_unwrap(setShortCoinList, {})),
        };
        void __VLS_196;
        var __VLS_193;
        var __VLS_194;
        let __VLS_197;
        /** @ts-ignore @type { | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider'] | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider']} */
        vDivider;
        // @ts-ignore
        const __VLS_198 = __VLS_asFunctionalComponent1(__VLS_197, new __VLS_197({
            // @ts-ignore
            ...{ class: "my-4" },
        }));
        const __VLS_199 = __VLS_198({
            ...{ class: "my-4" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_198));
        /** @type {__VLS_StyleScopedClasses['my-4']} */ ;
        let __VLS_202;
        /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch'] | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
        vSwitch;
        // @ts-ignore
        const __VLS_203 = __VLS_asFunctionalComponent1(__VLS_202, new __VLS_202({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.enable_short_sl_tp), label: "开启空头固定 SL/TP", color: "info", inset: true, disabled: (!settingsStore.value.settings.enable_short_trades),
        }));
        const __VLS_204 = __VLS_203({
            modelValue: (settingsStore.value.settings.enable_short_sl_tp),
            label: "开启空头固定 SL/TP",
            color: "info",
            inset: true,
            disabled: (!settingsStore.value.settings.enable_short_trades),
        }, ...__VLS_functionalComponentArgsRest(__VLS_203));
        let __VLS_207;
        /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
        vRow;
        // @ts-ignore
        const __VLS_208 = __VLS_asFunctionalComponent1(__VLS_207, new __VLS_207({
            // @ts-ignore
            dense: true,
        }));
        const __VLS_209 = __VLS_208({
            dense: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_208));
        var __VLS_210;
        const { default: __VLS_212 } = __VLS_nonNull(__VLS_210.slots);
        let __VLS_213;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_214 = __VLS_asFunctionalComponent1(__VLS_213, new __VLS_213({
            // @ts-ignore
            cols: "6",
        }));
        const __VLS_215 = __VLS_214({
            cols: "6",
        }, ...__VLS_functionalComponentArgsRest(__VLS_214));
        var __VLS_216;
        const { default: __VLS_218 } = __VLS_nonNull(__VLS_216.slots);
        let __VLS_219;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_220 = __VLS_asFunctionalComponent1(__VLS_219, new __VLS_219({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.short_stop_loss_percentage), modelModifiers: { number: true, }, label: "止损 (%)", type: "number", disabled: (!settingsStore.value.settings.enable_short_sl_tp), hint: "设为0则不设置止损", persistentHint: true,
        }));
        const __VLS_221 = __VLS_220({
            modelValue: (settingsStore.value.settings.short_stop_loss_percentage),
            modelModifiers: { number: true, },
            label: "止损 (%)",
            type: "number",
            disabled: (!settingsStore.value.settings.enable_short_sl_tp),
            hint: "设为0则不设置止损",
            persistentHint: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_220));
        // @ts-ignore
        [settingsStore, settingsStore, settingsStore, settingsStore, settingsStore, settingsStore, settingsStore, settingsStore, settingsStore, shortListItems, setShortCoinList,];
        let __VLS_224;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_225 = __VLS_asFunctionalComponent1(__VLS_224, new __VLS_224({
            // @ts-ignore
            cols: "6",
        }));
        const __VLS_226 = __VLS_225({
            cols: "6",
        }, ...__VLS_functionalComponentArgsRest(__VLS_225));
        var __VLS_227;
        const { default: __VLS_229 } = __VLS_nonNull(__VLS_227.slots);
        let __VLS_230;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_231 = __VLS_asFunctionalComponent1(__VLS_230, new __VLS_230({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.short_take_profit_percentage), modelModifiers: { number: true, }, label: "止盈 (%)", type: "number", disabled: (!settingsStore.value.settings.enable_short_sl_tp), hint: "设为0则不设置止盈", persistentHint: true,
        }));
        const __VLS_232 = __VLS_231({
            modelValue: (settingsStore.value.settings.short_take_profit_percentage),
            modelModifiers: { number: true, },
            label: "止盈 (%)",
            type: "number",
            disabled: (!settingsStore.value.settings.enable_short_sl_tp),
            hint: "设为0则不设置止盈",
            persistentHint: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_231));
        // @ts-ignore
        [settingsStore, settingsStore,];
        // @ts-ignore
        [];
        let __VLS_235;
        /** @ts-ignore @type { | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider'] | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider']} */
        vDivider;
        // @ts-ignore
        const __VLS_236 = __VLS_asFunctionalComponent1(__VLS_235, new __VLS_235({
            // @ts-ignore
            ...{ class: "my-4" },
        }));
        const __VLS_237 = __VLS_236({
            ...{ class: "my-4" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_236));
        /** @type {__VLS_StyleScopedClasses['my-4']} */ ;
        let __VLS_240;
        /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch'] | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
        vSwitch;
        // @ts-ignore
        const __VLS_241 = __VLS_asFunctionalComponent1(__VLS_240, new __VLS_240({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.enable_short_trailing_stop), label: "开启空头移动止盈 (Trailing)", color: "purple-accent-2", inset: true, disabled: (!settingsStore.value.settings.enable_short_trades),
        }));
        const __VLS_242 = __VLS_241({
            modelValue: (settingsStore.value.settings.enable_short_trailing_stop),
            label: "开启空头移动止盈 (Trailing)",
            color: "purple-accent-2",
            inset: true,
            disabled: (!settingsStore.value.settings.enable_short_trades),
        }, ...__VLS_functionalComponentArgsRest(__VLS_241));
        let __VLS_245;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_246 = __VLS_asFunctionalComponent1(__VLS_245, new __VLS_245({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.short_trailing_stop_callback_rate), modelModifiers: { number: true, }, label: "反弹率 (%)", type: "number", step: "0.1", min: "0.1", max: "5.0", disabled: (!settingsStore.value.settings.enable_short_trailing_stop), hint: "价格反弹多少百分比时平仓 (建议 0.5% - 5.0%)", persistentHint: true,
        }));
        const __VLS_247 = __VLS_246({
            modelValue: (settingsStore.value.settings.short_trailing_stop_callback_rate),
            modelModifiers: { number: true, },
            label: "反弹率 (%)",
            type: "number",
            step: "0.1",
            min: "0.1",
            max: "5.0",
            disabled: (!settingsStore.value.settings.enable_short_trailing_stop),
            hint: "价格反弹多少百分比时平仓 (建议 0.5% - 5.0%)",
            persistentHint: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_246));
        // @ts-ignore
        [settingsStore, settingsStore, settingsStore, settingsStore,];
        // @ts-ignore
        [];
        // @ts-ignore
        [];
        // @ts-ignore
        [];
        let __VLS_250;
        /** @ts-ignore @type { | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card'] | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card']} */
        vCard;
        // @ts-ignore
        const __VLS_251 = __VLS_asFunctionalComponent1(__VLS_250, new __VLS_250({
            // @ts-ignore
            variant: "outlined", ...{ class: "mt-4" },
        }));
        const __VLS_252 = __VLS_251({
            variant: "outlined",
            ...{ class: "mt-4" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_251));
        /** @type {__VLS_StyleScopedClasses['mt-4']} */ ;
        var __VLS_253;
        const { default: __VLS_255 } = __VLS_nonNull(__VLS_253.slots);
        let __VLS_256;
        /** @ts-ignore @type { | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title'] | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title']} */
        vCardTitle;
        // @ts-ignore
        const __VLS_257 = __VLS_asFunctionalComponent1(__VLS_256, new __VLS_256({
        // @ts-ignore
        }));
        const __VLS_258 = __VLS_257({}, ...__VLS_functionalComponentArgsRest(__VLS_257));
        var __VLS_259;
        const { default: __VLS_261 } = __VLS_nonNull(__VLS_259.slots);
        // @ts-ignore
        [];
        let __VLS_262;
        /** @ts-ignore @type { | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text'] | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text']} */
        vCardText;
        // @ts-ignore
        const __VLS_263 = __VLS_asFunctionalComponent1(__VLS_262, new __VLS_262({
        // @ts-ignore
        }));
        const __VLS_264 = __VLS_263({}, ...__VLS_functionalComponentArgsRest(__VLS_263));
        var __VLS_265;
        const { default: __VLS_267 } = __VLS_nonNull(__VLS_265.slots);
        let __VLS_268;
        /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
        vRow;
        // @ts-ignore
        const __VLS_269 = __VLS_asFunctionalComponent1(__VLS_268, new __VLS_268({
        // @ts-ignore
        }));
        const __VLS_270 = __VLS_269({}, ...__VLS_functionalComponentArgsRest(__VLS_269));
        var __VLS_271;
        const { default: __VLS_273 } = __VLS_nonNull(__VLS_271.slots);
        let __VLS_274;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_275 = __VLS_asFunctionalComponent1(__VLS_274, new __VLS_274({
            // @ts-ignore
            cols: "12", sm: "6",
        }));
        const __VLS_276 = __VLS_275({
            cols: "12",
            sm: "6",
        }, ...__VLS_functionalComponentArgsRest(__VLS_275));
        var __VLS_277;
        const { default: __VLS_279 } = __VLS_nonNull(__VLS_277.slots);
        let __VLS_280;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_281 = __VLS_asFunctionalComponent1(__VLS_280, new __VLS_280({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.open_maker_retries), modelModifiers: { number: true, }, label: "开仓重试次数", type: "number", hint: "挂单失败或超时后重试的次数", persistentHint: true,
        }));
        const __VLS_282 = __VLS_281({
            modelValue: (settingsStore.value.settings.open_maker_retries),
            modelModifiers: { number: true, },
            label: "开仓重试次数",
            type: "number",
            hint: "挂单失败或超时后重试的次数",
            persistentHint: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_281));
        // @ts-ignore
        [settingsStore,];
        let __VLS_285;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_286 = __VLS_asFunctionalComponent1(__VLS_285, new __VLS_285({
            // @ts-ignore
            cols: "12", sm: "6",
        }));
        const __VLS_287 = __VLS_286({
            cols: "12",
            sm: "6",
        }, ...__VLS_functionalComponentArgsRest(__VLS_286));
        var __VLS_288;
        const { default: __VLS_290 } = __VLS_nonNull(__VLS_288.slots);
        let __VLS_291;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_292 = __VLS_asFunctionalComponent1(__VLS_291, new __VLS_291({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.open_order_fill_timeout_seconds), modelModifiers: { number: true, }, label: "开仓订单超时 (秒)", type: "number", hint: "挂单后等待成交的最大时间", persistentHint: true,
        }));
        const __VLS_293 = __VLS_292({
            modelValue: (settingsStore.value.settings.open_order_fill_timeout_seconds),
            modelModifiers: { number: true, },
            label: "开仓订单超时 (秒)",
            type: "number",
            hint: "挂单后等待成交的最大时间",
            persistentHint: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_292));
        // @ts-ignore
        [settingsStore,];
        let __VLS_296;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_297 = __VLS_asFunctionalComponent1(__VLS_296, new __VLS_296({
            // @ts-ignore
            cols: "12", sm: "6",
        }));
        const __VLS_298 = __VLS_297({
            cols: "12",
            sm: "6",
        }, ...__VLS_functionalComponentArgsRest(__VLS_297));
        var __VLS_299;
        const { default: __VLS_301 } = __VLS_nonNull(__VLS_299.slots);
        let __VLS_302;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_303 = __VLS_asFunctionalComponent1(__VLS_302, new __VLS_302({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.close_maker_retries), modelModifiers: { number: true, }, label: "平仓重试次数", type: "number",
        }));
        const __VLS_304 = __VLS_303({
            modelValue: (settingsStore.value.settings.close_maker_retries),
            modelModifiers: { number: true, },
            label: "平仓重试次数",
            type: "number",
        }, ...__VLS_functionalComponentArgsRest(__VLS_303));
        // @ts-ignore
        [settingsStore,];
        let __VLS_307;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_308 = __VLS_asFunctionalComponent1(__VLS_307, new __VLS_307({
            // @ts-ignore
            cols: "12", sm: "6",
        }));
        const __VLS_309 = __VLS_308({
            cols: "12",
            sm: "6",
        }, ...__VLS_functionalComponentArgsRest(__VLS_308));
        var __VLS_310;
        const { default: __VLS_312 } = __VLS_nonNull(__VLS_310.slots);
        let __VLS_313;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_314 = __VLS_asFunctionalComponent1(__VLS_313, new __VLS_313({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.close_order_fill_timeout_seconds), modelModifiers: { number: true, }, label: "平仓订单超时 (秒)", type: "number",
        }));
        const __VLS_315 = __VLS_314({
            modelValue: (settingsStore.value.settings.close_order_fill_timeout_seconds),
            modelModifiers: { number: true, },
            label: "平仓订单超时 (秒)",
            type: "number",
        }, ...__VLS_functionalComponentArgsRest(__VLS_314));
        // @ts-ignore
        [settingsStore,];
        // @ts-ignore
        [];
        // @ts-ignore
        [];
        // @ts-ignore
        [];
        // @ts-ignore
        [];
        let __VLS_318;
        /** @ts-ignore @type { | typeof __VLS_components.vWindowItem | typeof __VLS_components.VWindowItem | typeof __VLS_components['v-window-item'] | typeof __VLS_components.vWindowItem | typeof __VLS_components.VWindowItem | typeof __VLS_components['v-window-item']} */
        vWindowItem;
        // @ts-ignore
        const __VLS_319 = __VLS_asFunctionalComponent1(__VLS_318, new __VLS_318({
            // @ts-ignore
            value: "rebalance",
        }));
        const __VLS_320 = __VLS_319({
            value: "rebalance",
        }, ...__VLS_functionalComponentArgsRest(__VLS_319));
        var __VLS_321;
        const { default: __VLS_323 } = __VLS_nonNull(__VLS_321.slots);
        __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
            ...{ class: "mb-4" },
        });
        /** @type {__VLS_StyleScopedClasses['mb-4']} */ ;
        let __VLS_324;
        /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
        vRow;
        // @ts-ignore
        const __VLS_325 = __VLS_asFunctionalComponent1(__VLS_324, new __VLS_324({
        // @ts-ignore
        }));
        const __VLS_326 = __VLS_325({}, ...__VLS_functionalComponentArgsRest(__VLS_325));
        var __VLS_327;
        const { default: __VLS_329 } = __VLS_nonNull(__VLS_327.slots);
        let __VLS_330;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_331 = __VLS_asFunctionalComponent1(__VLS_330, new __VLS_330({
            // @ts-ignore
            cols: "12", md: "6",
        }));
        const __VLS_332 = __VLS_331({
            cols: "12",
            md: "6",
        }, ...__VLS_functionalComponentArgsRest(__VLS_331));
        var __VLS_333;
        const { default: __VLS_335 } = __VLS_nonNull(__VLS_333.slots);
        const __VLS_336 = SmartSelect || SmartSelect;
        // @ts-ignore
        const __VLS_337 = __VLS_asFunctionalComponent1(__VLS_336, new __VLS_336({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.rebalance_method), items: (__VLS_unwrap(rebalanceMethods, {})), itemTitle: "text", itemValue: "value", label: "筛选策略",
        }));
        const __VLS_338 = __VLS_337({
            modelValue: (settingsStore.value.settings.rebalance_method),
            items: (__VLS_unwrap(rebalanceMethods, {})),
            itemTitle: "text",
            itemValue: "value",
            label: "筛选策略",
        }, ...__VLS_functionalComponentArgsRest(__VLS_337));
        let __VLS_341;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_342 = __VLS_asFunctionalComponent1(__VLS_341, new __VLS_341({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.rebalance_top_n), modelModifiers: { number: true, }, label: "目标币种数量 (Top N)", type: "number", variant: "outlined", density: "compact",
        }));
        const __VLS_343 = __VLS_342({
            modelValue: (settingsStore.value.settings.rebalance_top_n),
            modelModifiers: { number: true, },
            label: "目标币种数量 (Top N)",
            type: "number",
            variant: "outlined",
            density: "compact",
        }, ...__VLS_functionalComponentArgsRest(__VLS_342));
        let __VLS_346;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_347 = __VLS_asFunctionalComponent1(__VLS_346, new __VLS_346({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.rebalance_min_volume_usd), modelModifiers: { number: true, }, label: "最小24h交易额 (USD)", type: "number", variant: "outlined", density: "compact",
        }));
        const __VLS_348 = __VLS_347({
            modelValue: (settingsStore.value.settings.rebalance_min_volume_usd),
            modelModifiers: { number: true, },
            label: "最小24h交易额 (USD)",
            type: "number",
            variant: "outlined",
            density: "compact",
        }, ...__VLS_functionalComponentArgsRest(__VLS_347));
        let __VLS_351;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_352 = __VLS_asFunctionalComponent1(__VLS_351, new __VLS_351({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.rebalance_volume_ma_days), modelModifiers: { number: true, }, label: "成交量均线天数 (MA)", type: "number", hint: "用于计算平均成交量", persistentHint: true, variant: "outlined", density: "compact",
        }));
        const __VLS_353 = __VLS_352({
            modelValue: (settingsStore.value.settings.rebalance_volume_ma_days),
            modelModifiers: { number: true, },
            label: "成交量均线天数 (MA)",
            type: "number",
            hint: "用于计算平均成交量",
            persistentHint: true,
            variant: "outlined",
            density: "compact",
        }, ...__VLS_functionalComponentArgsRest(__VLS_352));
        // @ts-ignore
        [settingsStore, settingsStore, settingsStore, settingsStore, rebalanceMethods,];
        let __VLS_356;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_357 = __VLS_asFunctionalComponent1(__VLS_356, new __VLS_356({
            // @ts-ignore
            cols: "12", md: "6",
        }));
        const __VLS_358 = __VLS_357({
            cols: "12",
            md: "6",
        }, ...__VLS_functionalComponentArgsRest(__VLS_357));
        var __VLS_359;
        const { default: __VLS_361 } = __VLS_nonNull(__VLS_359.slots);
        if (settingsStore.value.settings.rebalance_method === 'multi_factor_weakest') {
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
            const __VLS_362 = SmartSelect || SmartSelect;
            // @ts-ignore
            const __VLS_363 = __VLS_asFunctionalComponent1(__VLS_362, new __VLS_362({
                // @ts-ignore
                ...{ 'onUpdate:modelValue': {} }, modelValue: (settingsStore.value.settings.rebalance_benchmark_coin), items: (__VLS_unwrap(longListItems, {})), label: "相对强度基准币种", multiple: true, searchable: true, persistentHint: true, hint: "用于计算相对强度",
            }));
            const __VLS_364 = __VLS_363({
                ...{ 'onUpdate:modelValue': {} },
                modelValue: (settingsStore.value.settings.rebalance_benchmark_coin),
                items: (__VLS_unwrap(longListItems, {})),
                label: "相对强度基准币种",
                multiple: true,
                searchable: true,
                persistentHint: true,
                hint: "用于计算相对强度",
            }, ...__VLS_functionalComponentArgsRest(__VLS_363));
            let __VLS_367;
            const __VLS_368 = {
                /** @type {typeof __VLS_367.'update:modelValue'} */
                'onUpdate:modelValue': (__VLS_unwrap(setBenchmarkCoins, {})),
            };
            void __VLS_368;
            var __VLS_365;
            var __VLS_366;
            let __VLS_369;
            /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
            vTextField;
            // @ts-ignore
            const __VLS_370 = __VLS_asFunctionalComponent1(__VLS_369, new __VLS_369({
                // @ts-ignore
                modelValue: (settingsStore.value.settings.rebalance_abs_momentum_days), modelModifiers: { number: true, }, label: "绝对动量天数", type: "number", variant: "outlined", density: "compact",
            }));
            const __VLS_371 = __VLS_370({
                modelValue: (settingsStore.value.settings.rebalance_abs_momentum_days),
                modelModifiers: { number: true, },
                label: "绝对动量天数",
                type: "number",
                variant: "outlined",
                density: "compact",
            }, ...__VLS_functionalComponentArgsRest(__VLS_370));
            let __VLS_374;
            /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
            vTextField;
            // @ts-ignore
            const __VLS_375 = __VLS_asFunctionalComponent1(__VLS_374, new __VLS_374({
                // @ts-ignore
                modelValue: (settingsStore.value.settings.rebalance_rel_strength_days), modelModifiers: { number: true, }, label: "相对强度天数", type: "number", variant: "outlined", density: "compact",
            }));
            const __VLS_376 = __VLS_375({
                modelValue: (settingsStore.value.settings.rebalance_rel_strength_days),
                modelModifiers: { number: true, },
                label: "相对强度天数",
                type: "number",
                variant: "outlined",
                density: "compact",
            }, ...__VLS_functionalComponentArgsRest(__VLS_375));
        }
        let __VLS_379;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_380 = __VLS_asFunctionalComponent1(__VLS_379, new __VLS_379({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.rebalance_volume_spike_ratio), modelModifiers: { number: true, }, label: "成交量放大过滤倍数", type: "number", hint: "最近成交量 > N倍均量则过滤", persistentHint: true, variant: "outlined", density: "compact",
        }));
        const __VLS_381 = __VLS_380({
            modelValue: (settingsStore.value.settings.rebalance_volume_spike_ratio),
            modelModifiers: { number: true, },
            label: "成交量放大过滤倍数",
            type: "number",
            hint: "最近成交量 > N倍均量则过滤",
            persistentHint: true,
            variant: "outlined",
            density: "compact",
        }, ...__VLS_functionalComponentArgsRest(__VLS_380));
        // @ts-ignore
        [settingsStore, settingsStore, settingsStore, settingsStore, settingsStore, longListItems, setBenchmarkCoins,];
        // @ts-ignore
        [];
        let __VLS_384;
        /** @ts-ignore @type { | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card'] | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card']} */
        vCard;
        // @ts-ignore
        const __VLS_385 = __VLS_asFunctionalComponent1(__VLS_384, new __VLS_384({
            // @ts-ignore
            variant: "outlined", ...{ class: "mt-4" },
        }));
        const __VLS_386 = __VLS_385({
            variant: "outlined",
            ...{ class: "mt-4" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_385));
        /** @type {__VLS_StyleScopedClasses['mt-4']} */ ;
        var __VLS_387;
        const { default: __VLS_389 } = __VLS_nonNull(__VLS_387.slots);
        let __VLS_390;
        /** @ts-ignore @type { | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title'] | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title']} */
        vCardTitle;
        // @ts-ignore
        const __VLS_391 = __VLS_asFunctionalComponent1(__VLS_390, new __VLS_390({
            // @ts-ignore
            ...{ class: "d-flex align-center" },
        }));
        const __VLS_392 = __VLS_391({
            ...{ class: "d-flex align-center" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_391));
        /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
        /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
        var __VLS_393;
        const { default: __VLS_395 } = __VLS_nonNull(__VLS_393.slots);
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
        let __VLS_396;
        /** @ts-ignore @type { | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer'] | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer']} */
        vSpacer;
        // @ts-ignore
        const __VLS_397 = __VLS_asFunctionalComponent1(__VLS_396, new __VLS_396({
        // @ts-ignore
        }));
        const __VLS_398 = __VLS_397({}, ...__VLS_functionalComponentArgsRest(__VLS_397));
        let __VLS_401;
        /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch'] | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
        vSwitch;
        // @ts-ignore
        const __VLS_402 = __VLS_asFunctionalComponent1(__VLS_401, new __VLS_401({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.enable_rebalance_filters), label: "启用", color: "primary", hideDetails: true, inset: true,
        }));
        const __VLS_403 = __VLS_402({
            modelValue: (settingsStore.value.settings.enable_rebalance_filters),
            label: "启用",
            color: "primary",
            hideDetails: true,
            inset: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_402));
        // @ts-ignore
        [settingsStore,];
        let __VLS_406;
        /** @ts-ignore @type { | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider'] | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider']} */
        vDivider;
        // @ts-ignore
        const __VLS_407 = __VLS_asFunctionalComponent1(__VLS_406, new __VLS_406({
        // @ts-ignore
        }));
        const __VLS_408 = __VLS_407({}, ...__VLS_functionalComponentArgsRest(__VLS_407));
        let __VLS_411;
        /** @ts-ignore @type { | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text'] | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text']} */
        vCardText;
        // @ts-ignore
        const __VLS_412 = __VLS_asFunctionalComponent1(__VLS_411, new __VLS_411({
            // @ts-ignore
            ...{ class: ({ 'disabled-overlay': !settingsStore.value.settings.enable_rebalance_filters }) },
        }));
        const __VLS_413 = __VLS_412({
            ...{ class: ({ 'disabled-overlay': !settingsStore.value.settings.enable_rebalance_filters }) },
        }, ...__VLS_functionalComponentArgsRest(__VLS_412));
        /** @type {__VLS_StyleScopedClasses['disabled-overlay']} */ ;
        var __VLS_414;
        const { default: __VLS_416 } = __VLS_nonNull(__VLS_414.slots);
        let __VLS_417;
        /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
        vRow;
        // @ts-ignore
        const __VLS_418 = __VLS_asFunctionalComponent1(__VLS_417, new __VLS_417({
        // @ts-ignore
        }));
        const __VLS_419 = __VLS_418({}, ...__VLS_functionalComponentArgsRest(__VLS_418));
        var __VLS_420;
        const { default: __VLS_422 } = __VLS_nonNull(__VLS_420.slots);
        let __VLS_423;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_424 = __VLS_asFunctionalComponent1(__VLS_423, new __VLS_423({
            // @ts-ignore
            cols: "12", sm: "6", md: "4",
        }));
        const __VLS_425 = __VLS_424({
            cols: "12",
            sm: "6",
            md: "4",
        }, ...__VLS_functionalComponentArgsRest(__VLS_424));
        var __VLS_426;
        const { default: __VLS_428 } = __VLS_nonNull(__VLS_426.slots);
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "text-subtitle-2 mb-1" },
        });
        /** @type {__VLS_StyleScopedClasses['text-subtitle-2']} */ ;
        /** @type {__VLS_StyleScopedClasses['mb-1']} */ ;
        let __VLS_429;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_430 = __VLS_asFunctionalComponent1(__VLS_429, new __VLS_429({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.rebalance_rsi_period), modelModifiers: { number: true, }, label: "RSI 周期", type: "number", density: "compact",
        }));
        const __VLS_431 = __VLS_430({
            modelValue: (settingsStore.value.settings.rebalance_rsi_period),
            modelModifiers: { number: true, },
            label: "RSI 周期",
            type: "number",
            density: "compact",
        }, ...__VLS_functionalComponentArgsRest(__VLS_430));
        let __VLS_434;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_435 = __VLS_asFunctionalComponent1(__VLS_434, new __VLS_434({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.rebalance_rsi_threshold), modelModifiers: { number: true, }, label: "RSI 最低门槛", type: "number", hint: "低于此值将被剔除", persistentHint: true, density: "compact",
        }));
        const __VLS_436 = __VLS_435({
            modelValue: (settingsStore.value.settings.rebalance_rsi_threshold),
            modelModifiers: { number: true, },
            label: "RSI 最低门槛",
            type: "number",
            hint: "低于此值将被剔除",
            persistentHint: true,
            density: "compact",
        }, ...__VLS_functionalComponentArgsRest(__VLS_435));
        // @ts-ignore
        [settingsStore, settingsStore, settingsStore,];
        let __VLS_439;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_440 = __VLS_asFunctionalComponent1(__VLS_439, new __VLS_439({
            // @ts-ignore
            cols: "12", sm: "6", md: "4",
        }));
        const __VLS_441 = __VLS_440({
            cols: "12",
            sm: "6",
            md: "4",
        }, ...__VLS_functionalComponentArgsRest(__VLS_440));
        var __VLS_442;
        const { default: __VLS_444 } = __VLS_nonNull(__VLS_442.slots);
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "text-subtitle-2 mb-1" },
        });
        /** @type {__VLS_StyleScopedClasses['text-subtitle-2']} */ ;
        /** @type {__VLS_StyleScopedClasses['mb-1']} */ ;
        let __VLS_445;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_446 = __VLS_asFunctionalComponent1(__VLS_445, new __VLS_445({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.rebalance_short_term_momentum_days), modelModifiers: { number: true, }, label: "考察天数", type: "number", density: "compact",
        }));
        const __VLS_447 = __VLS_446({
            modelValue: (settingsStore.value.settings.rebalance_short_term_momentum_days),
            modelModifiers: { number: true, },
            label: "考察天数",
            type: "number",
            density: "compact",
        }, ...__VLS_functionalComponentArgsRest(__VLS_446));
        let __VLS_450;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_451 = __VLS_asFunctionalComponent1(__VLS_450, new __VLS_450({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.rebalance_short_term_momentum_threshold), modelModifiers: { number: true, }, label: "最大涨幅 (%)", type: "number", hint: "短期涨幅过高将剔除", persistentHint: true, density: "compact",
        }));
        const __VLS_452 = __VLS_451({
            modelValue: (settingsStore.value.settings.rebalance_short_term_momentum_threshold),
            modelModifiers: { number: true, },
            label: "最大涨幅 (%)",
            type: "number",
            hint: "短期涨幅过高将剔除",
            persistentHint: true,
            density: "compact",
        }, ...__VLS_functionalComponentArgsRest(__VLS_451));
        // @ts-ignore
        [settingsStore, settingsStore,];
        let __VLS_455;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_456 = __VLS_asFunctionalComponent1(__VLS_455, new __VLS_455({
            // @ts-ignore
            cols: "12", sm: "6", md: "4",
        }));
        const __VLS_457 = __VLS_456({
            cols: "12",
            sm: "6",
            md: "4",
        }, ...__VLS_functionalComponentArgsRest(__VLS_456));
        var __VLS_458;
        const { default: __VLS_460 } = __VLS_nonNull(__VLS_458.slots);
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "text-subtitle-2 mb-1" },
        });
        /** @type {__VLS_StyleScopedClasses['text-subtitle-2']} */ ;
        /** @type {__VLS_StyleScopedClasses['mb-1']} */ ;
        let __VLS_461;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_462 = __VLS_asFunctionalComponent1(__VLS_461, new __VLS_461({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.rebalance_bollinger_period), modelModifiers: { number: true, }, label: "布林带周期", type: "number", density: "compact",
        }));
        const __VLS_463 = __VLS_462({
            modelValue: (settingsStore.value.settings.rebalance_bollinger_period),
            modelModifiers: { number: true, },
            label: "布林带周期",
            type: "number",
            density: "compact",
        }, ...__VLS_functionalComponentArgsRest(__VLS_462));
        let __VLS_466;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_467 = __VLS_asFunctionalComponent1(__VLS_466, new __VLS_466({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.rebalance_bollinger_std_dev), modelModifiers: { number: true, }, label: "布林带标准差", type: "number", density: "compact",
        }));
        const __VLS_468 = __VLS_467({
            modelValue: (settingsStore.value.settings.rebalance_bollinger_std_dev),
            modelModifiers: { number: true, },
            label: "布林带标准差",
            type: "number",
            density: "compact",
        }, ...__VLS_functionalComponentArgsRest(__VLS_467));
        let __VLS_471;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_472 = __VLS_asFunctionalComponent1(__VLS_471, new __VLS_471({
            // @ts-ignore
            modelValue: (settingsStore.value.settings.rebalance_bollinger_width_spike_ratio), modelModifiers: { number: true, }, label: "宽度放大倍数", type: "number", hint: "当前宽度/均值 > 此值则剔除", persistentHint: true, density: "compact",
        }));
        const __VLS_473 = __VLS_472({
            modelValue: (settingsStore.value.settings.rebalance_bollinger_width_spike_ratio),
            modelModifiers: { number: true, },
            label: "宽度放大倍数",
            type: "number",
            hint: "当前宽度/均值 > 此值则剔除",
            persistentHint: true,
            density: "compact",
        }, ...__VLS_functionalComponentArgsRest(__VLS_472));
        // @ts-ignore
        [settingsStore, settingsStore, settingsStore,];
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
        // @ts-ignore
        [];
        // @ts-ignore
        [];
    }
    else {
        let __VLS_476;
        /** @ts-ignore @type { | typeof __VLS_components.vSkeletonLoader | typeof __VLS_components.VSkeletonLoader | typeof __VLS_components['v-skeleton-loader'] | typeof __VLS_components.vSkeletonLoader | typeof __VLS_components.VSkeletonLoader | typeof __VLS_components['v-skeleton-loader']} */
        vSkeletonLoader;
        // @ts-ignore
        const __VLS_477 = __VLS_asFunctionalComponent1(__VLS_476, new __VLS_476({
            // @ts-ignore
            type: "card, article",
        }));
        const __VLS_478 = __VLS_477({
            type: "card, article",
        }, ...__VLS_functionalComponentArgsRest(__VLS_477));
    }
    // @ts-ignore
    [];
    return {};
};
void [__VLS_template];
const __VLS_export = (await import('vue')).defineComponent({
    __typeEmits: {},
    __typeProps: {},
});
export default {};
