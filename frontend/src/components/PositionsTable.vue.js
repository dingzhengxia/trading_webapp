import { computed, ref } from 'vue';
import { useDisplay } from 'vuetify';
import { useUiStore } from '@/stores/uiStore';
import { usePositionStore } from '@/stores/positionStore';
const { defineProps, defineEmits, } = {};
const props = defineProps();
const emit = defineEmits(['refresh']);
const uiStore = useUiStore();
const positionStore = usePositionStore();
const totalNotional = computed(() => {
    return props.positions.reduce((sum, position) => sum + position.notional, 0);
});
const selectedInThisTable = computed(() => {
    const currentTableSymbols = new Set(props.positions.map((p) => p.full_symbol));
    return positionStore.selectedPositions
        .filter((fullSymbol) => currentTableSymbols.has(fullSymbol))
        .map((fullSymbol) => props.positions.find((p) => p.full_symbol === fullSymbol))
        .filter((p) => p);
});
const handleCloseAll = () => {
    uiStore.openCloseDialog({ type: 'by_side', side: props.side });
};
const handleCloseSelected = () => {
    if (selectedInThisTable.value.length > 0) {
        uiStore.openCloseDialog({ type: 'selected', positions: selectedInThisTable.value });
    }
};
// --- 反手（单仓位）---
const reverseDialog = ref(false);
const reverseTarget = ref(null);
const reverseValue = ref(0);
const openReverseDialog = (position) => {
    reverseTarget.value = position;
    reverseValue.value = Math.max(1, Math.round(position.notional * 100) / 100);
    reverseDialog.value = true;
};
const confirmReverse = () => {
    const target = reverseTarget.value;
    if (!target || !(reverseValue.value > 0))
        return;
    // 传 full_symbol 即可，后端会自动截取基础币种（XAUT/USDT:USDT → XAUT）
    uiStore.launchTask('/api/trading/manual', { items: [{ symbol: target.full_symbol, action: 'reverse', value: Number(reverseValue.value) }] }, `反手交易 ${target.full_symbol}`, 1);
    reverseDialog.value = false;
};
const headers = [
    { title: '合约', key: 'full_symbol', sortable: true, width: '20%' },
    { title: '名义价值', key: 'notional', sortable: true, width: '15%' },
    { title: '浮动盈亏', key: 'pnl', sortable: true, width: '15%' },
    { title: '回报率', key: 'pnl_percentage', sortable: true, width: '15%' },
    { title: '开仓均价', key: 'entry_price', width: '15%' },
    { title: '操作', key: 'actions', sortable: false, align: 'end', width: '12%' },
];
// 手机端隐藏「开仓均价」列，避免表格横向溢出
const { smAndDown } = useDisplay();
const isMobile = computed(() => smAndDown.value);
const visibleHeaders = computed(() => isMobile.value ? headers.filter((header) => header.key !== 'entry_price') : headers);
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
    __VLS_withDotValue(totalNotional, {});
    __VLS_withDotValue(selectedInThisTable, {});
    __VLS_withDotValue(positionStore, {});
    __VLS_withDotValue(isMobile, {});
    __VLS_withDotValue(uiStore, {});
    __VLS_withDotValue(reverseTarget, {});
    __VLS_withDotValue(reverseDialog, {});
    void {};
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
    /** @ts-ignore @type { | typeof __VLS_components.vToolbar | typeof __VLS_components.VToolbar | typeof __VLS_components['v-toolbar'] | typeof __VLS_components.vToolbar | typeof __VLS_components.VToolbar | typeof __VLS_components['v-toolbar']} */
    vToolbar;
    // @ts-ignore
    const __VLS_7 = __VLS_asFunctionalComponent1(__VLS_6, new __VLS_6({
        // @ts-ignore
        density: "compact", flat: true,
    }));
    const __VLS_8 = __VLS_7({
        density: "compact",
        flat: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_7));
    var __VLS_9;
    const { default: __VLS_11 } = __VLS_nonNull(__VLS_9.slots);
    let __VLS_12;
    /** @ts-ignore @type { | typeof __VLS_components.vToolbarTitle | typeof __VLS_components.VToolbarTitle | typeof __VLS_components['v-toolbar-title'] | typeof __VLS_components.vToolbarTitle | typeof __VLS_components.VToolbarTitle | typeof __VLS_components['v-toolbar-title']} */
    vToolbarTitle;
    // @ts-ignore
    const __VLS_13 = __VLS_asFunctionalComponent1(__VLS_12, new __VLS_12({
        // @ts-ignore
        ...{ class: "text-h6" },
    }));
    const __VLS_14 = __VLS_13({
        ...{ class: "text-h6" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_13));
    /** @type {__VLS_StyleScopedClasses['text-h6']} */ ;
    var __VLS_15;
    const { default: __VLS_17 } = __VLS_nonNull(__VLS_15.slots);
    (__VLS_ctx.title);
    // @ts-ignore
    [title,];
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
        color: (__VLS_ctx.side === 'long' ? 'success' : 'error'), label: true, variant: "flat", size: "small", ...{ class: "mr-2" },
    }));
    const __VLS_25 = __VLS_24({
        color: (__VLS_ctx.side === 'long' ? 'success' : 'error'),
        label: true,
        variant: "flat",
        size: "small",
        ...{ class: "mr-2" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_24));
    /** @type {__VLS_StyleScopedClasses['mr-2']} */ ;
    var __VLS_26;
    const { default: __VLS_28 } = __VLS_nonNull(__VLS_26.slots);
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
        ...{ class: "font-weight-bold" },
    });
    /** @type {__VLS_StyleScopedClasses['font-weight-bold']} */ ;
    (totalNotional.value.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }));
    // @ts-ignore
    [side, totalNotional,];
    let __VLS_29;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_30 = __VLS_asFunctionalComponent1(__VLS_29, new __VLS_29({
        // @ts-ignore
        ...{ 'onClick': {} }, icon: "mdi-refresh", variant: "text", size: "small", loading: (__VLS_ctx.loading),
    }));
    const __VLS_31 = __VLS_30({
        ...{ 'onClick': {} },
        icon: "mdi-refresh",
        variant: "text",
        size: "small",
        loading: (__VLS_ctx.loading),
    }, ...__VLS_functionalComponentArgsRest(__VLS_30));
    let __VLS_34;
    const __VLS_35 = {
        /** @type {typeof __VLS_34.click} */
        onClick: (...[$event]) => {
            void $event;
            return (__VLS_unwrap(emit, {})('refresh'));
            // @ts-ignore
            [loading, emit,];
        },
    };
    void __VLS_35;
    var __VLS_32;
    var __VLS_33;
    // @ts-ignore
    [];
    let __VLS_36;
    /** @ts-ignore @type { | typeof __VLS_components.vToolbar | typeof __VLS_components.VToolbar | typeof __VLS_components['v-toolbar'] | typeof __VLS_components.vToolbar | typeof __VLS_components.VToolbar | typeof __VLS_components['v-toolbar']} */
    vToolbar;
    // @ts-ignore
    const __VLS_37 = __VLS_asFunctionalComponent1(__VLS_36, new __VLS_36({
        // @ts-ignore
        density: "compact", flat: true, color: "transparent", ...{ class: "px-2 toolbar-wrap" },
    }));
    const __VLS_38 = __VLS_37({
        density: "compact",
        flat: true,
        color: "transparent",
        ...{ class: "px-2 toolbar-wrap" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_37));
    /** @type {__VLS_StyleScopedClasses['px-2']} */ ;
    /** @type {__VLS_StyleScopedClasses['toolbar-wrap']} */ ;
    var __VLS_39;
    const { default: __VLS_41 } = __VLS_nonNull(__VLS_39.slots);
    let __VLS_42;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_43 = __VLS_asFunctionalComponent1(__VLS_42, new __VLS_42({
        // @ts-ignore
        ...{ 'onClick': {} }, color: "warning", variant: "tonal", size: "small", disabled: (selectedInThisTable.value.length === 0), prependIcon: "mdi-close-box-multiple",
    }));
    const __VLS_44 = __VLS_43({
        ...{ 'onClick': {} },
        color: "warning",
        variant: "tonal",
        size: "small",
        disabled: (selectedInThisTable.value.length === 0),
        prependIcon: "mdi-close-box-multiple",
    }, ...__VLS_functionalComponentArgsRest(__VLS_43));
    let __VLS_47;
    const __VLS_48 = {
        /** @type {typeof __VLS_47.click} */
        onClick: (__VLS_unwrap(handleCloseSelected, {})),
    };
    void __VLS_48;
    var __VLS_45;
    var __VLS_46;
    const { default: __VLS_49 } = __VLS_nonNull(__VLS_45.slots);
    (selectedInThisTable.value.length);
    // @ts-ignore
    [selectedInThisTable, selectedInThisTable, handleCloseSelected,];
    let __VLS_50;
    /** @ts-ignore @type { | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer'] | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer']} */
    vSpacer;
    // @ts-ignore
    const __VLS_51 = __VLS_asFunctionalComponent1(__VLS_50, new __VLS_50({
    // @ts-ignore
    }));
    const __VLS_52 = __VLS_51({}, ...__VLS_functionalComponentArgsRest(__VLS_51));
    let __VLS_55;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_56 = __VLS_asFunctionalComponent1(__VLS_55, new __VLS_55({
        // @ts-ignore
        ...{ 'onClick': {} }, color: "blue-grey", variant: "tonal", size: "small", prependIcon: "mdi-close-circle-multiple",
    }));
    const __VLS_57 = __VLS_56({
        ...{ 'onClick': {} },
        color: "blue-grey",
        variant: "tonal",
        size: "small",
        prependIcon: "mdi-close-circle-multiple",
    }, ...__VLS_functionalComponentArgsRest(__VLS_56));
    let __VLS_60;
    const __VLS_61 = {
        /** @type {typeof __VLS_60.click} */
        onClick: (__VLS_unwrap(handleCloseAll, {})),
    };
    void __VLS_61;
    var __VLS_58;
    var __VLS_59;
    const { default: __VLS_62 } = __VLS_nonNull(__VLS_58.slots);
    // @ts-ignore
    [handleCloseAll,];
    // @ts-ignore
    [];
    let __VLS_63;
    /** @ts-ignore @type { | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider'] | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider']} */
    vDivider;
    // @ts-ignore
    const __VLS_64 = __VLS_asFunctionalComponent1(__VLS_63, new __VLS_63({
    // @ts-ignore
    }));
    const __VLS_65 = __VLS_64({}, ...__VLS_functionalComponentArgsRest(__VLS_64));
    let __VLS_68;
    /** @ts-ignore @type { | typeof __VLS_components.vDataTableVirtual | typeof __VLS_components.VDataTableVirtual | typeof __VLS_components['v-data-table-virtual'] | typeof __VLS_components.vDataTableVirtual | typeof __VLS_components.VDataTableVirtual | typeof __VLS_components['v-data-table-virtual']} */
    vDataTableVirtual;
    // @ts-ignore
    const __VLS_69 = __VLS_asFunctionalComponent1(__VLS_68, new __VLS_68({
        // @ts-ignore
        modelValue: (positionStore.value.selectedPositions), headers: (__VLS_unwrap(visibleHeaders, {})), items: (__VLS_ctx.positions), itemValue: "full_symbol", showSelect: true, density: "compact", ...{ class: "text-caption position-table" }, fixedHeader: true, height: (isMobile.value ? '45vh' : 'calc(50vh - 120px)'), noDataText: "无持仓数据",
    }));
    const __VLS_70 = __VLS_69({
        modelValue: (positionStore.value.selectedPositions),
        headers: (__VLS_unwrap(visibleHeaders, {})),
        items: (__VLS_ctx.positions),
        itemValue: "full_symbol",
        showSelect: true,
        density: "compact",
        ...{ class: "text-caption position-table" },
        fixedHeader: true,
        height: (isMobile.value ? '45vh' : 'calc(50vh - 120px)'),
        noDataText: "无持仓数据",
    }, ...__VLS_functionalComponentArgsRest(__VLS_69));
    /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
    /** @type {__VLS_StyleScopedClasses['position-table']} */ ;
    var __VLS_71;
    const { default: __VLS_73 } = __VLS_nonNull(__VLS_71.slots);
    {
        const { 'item.notional': __VLS_74 } = __VLS_nonNull(__VLS_71.slots);
        const [{ item }] = __VLS_vSlot(__VLS_nonNull(__VLS_74));
        (item.notional.toFixed(2));
        // @ts-ignore
        [positionStore, visibleHeaders, positions, isMobile,];
    }
    {
        const { 'item.pnl': __VLS_75 } = __VLS_nonNull(__VLS_71.slots);
        const [{ item }] = __VLS_vSlot(__VLS_nonNull(__VLS_75));
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
            ...{ class: (item.pnl >= 0 ? 'text-success' : 'text-error') },
        });
        (item.pnl.toFixed(2));
        // @ts-ignore
        [];
    }
    {
        const { 'item.pnl_percentage': __VLS_76 } = __VLS_nonNull(__VLS_71.slots);
        const [{ item }] = __VLS_vSlot(__VLS_nonNull(__VLS_76));
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
            ...{ class: (item.pnl_percentage >= 0 ? 'text-success' : 'text-error') },
        });
        (item.pnl_percentage > 0 ? '+' : '');
        (item.pnl_percentage.toFixed(2));
        // @ts-ignore
        [];
    }
    {
        const { 'item.actions': __VLS_77 } = __VLS_nonNull(__VLS_71.slots);
        const [{ item }] = __VLS_vSlot(__VLS_nonNull(__VLS_77));
        let __VLS_78;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_79 = __VLS_asFunctionalComponent1(__VLS_78, new __VLS_78({
            // @ts-ignore
            ...{ 'onClick': {} }, color: "warning", variant: "text", size: "x-small", disabled: (uiStore.value.isRunning),
        }));
        const __VLS_80 = __VLS_79({
            ...{ 'onClick': {} },
            color: "warning",
            variant: "text",
            size: "x-small",
            disabled: (uiStore.value.isRunning),
        }, ...__VLS_functionalComponentArgsRest(__VLS_79));
        let __VLS_83;
        const __VLS_84 = {
            /** @type {typeof __VLS_83.click} */
            onClick: (...[$event]) => {
                void $event;
                return (__VLS_unwrap(openReverseDialog, {})(item));
                // @ts-ignore
                [uiStore, openReverseDialog,];
            },
        };
        void __VLS_84;
        var __VLS_81;
        var __VLS_82;
        const { default: __VLS_85 } = __VLS_nonNull(__VLS_81.slots);
        // @ts-ignore
        [];
        let __VLS_86;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_87 = __VLS_asFunctionalComponent1(__VLS_86, new __VLS_86({
            // @ts-ignore
            ...{ 'onClick': {} }, color: "error", variant: "text", size: "x-small",
        }));
        const __VLS_88 = __VLS_87({
            ...{ 'onClick': {} },
            color: "error",
            variant: "text",
            size: "x-small",
        }, ...__VLS_functionalComponentArgsRest(__VLS_87));
        let __VLS_91;
        const __VLS_92 = {
            /** @type {typeof __VLS_91.click} */
            onClick: (...[$event]) => {
                void $event;
                return (uiStore.value.openCloseDialog({ type: 'single', position: item }));
                // @ts-ignore
                [uiStore,];
            },
        };
        void __VLS_92;
        var __VLS_89;
        var __VLS_90;
        const { default: __VLS_93 } = __VLS_nonNull(__VLS_89.slots);
        // @ts-ignore
        [];
        // @ts-ignore
        [];
    }
    // @ts-ignore
    [];
    let __VLS_94;
    /** @ts-ignore @type { | typeof __VLS_components.vDialog | typeof __VLS_components.VDialog | typeof __VLS_components['v-dialog'] | typeof __VLS_components.vDialog | typeof __VLS_components.VDialog | typeof __VLS_components['v-dialog']} */
    vDialog;
    // @ts-ignore
    const __VLS_95 = __VLS_asFunctionalComponent1(__VLS_94, new __VLS_94({
        // @ts-ignore
        modelValue: (reverseDialog.value), maxWidth: "460", persistent: true,
    }));
    const __VLS_96 = __VLS_95({
        modelValue: (reverseDialog.value),
        maxWidth: "460",
        persistent: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_95));
    var __VLS_97;
    const { default: __VLS_99 } = __VLS_nonNull(__VLS_97.slots);
    let __VLS_100;
    /** @ts-ignore @type { | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card'] | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card']} */
    vCard;
    // @ts-ignore
    const __VLS_101 = __VLS_asFunctionalComponent1(__VLS_100, new __VLS_100({
    // @ts-ignore
    }));
    const __VLS_102 = __VLS_101({}, ...__VLS_functionalComponentArgsRest(__VLS_101));
    var __VLS_103;
    const { default: __VLS_105 } = __VLS_nonNull(__VLS_103.slots);
    let __VLS_106;
    /** @ts-ignore @type { | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title'] | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title']} */
    vCardTitle;
    // @ts-ignore
    const __VLS_107 = __VLS_asFunctionalComponent1(__VLS_106, new __VLS_106({
        // @ts-ignore
        ...{ class: "text-h6" },
    }));
    const __VLS_108 = __VLS_107({
        ...{ class: "text-h6" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_107));
    /** @type {__VLS_StyleScopedClasses['text-h6']} */ ;
    var __VLS_109;
    const { default: __VLS_111 } = __VLS_nonNull(__VLS_109.slots);
    let __VLS_112;
    /** @ts-ignore @type { | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon'] | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon']} */
    vIcon;
    // @ts-ignore
    const __VLS_113 = __VLS_asFunctionalComponent1(__VLS_112, new __VLS_112({
        // @ts-ignore
        color: "warning", ...{ class: "mr-2" },
    }));
    const __VLS_114 = __VLS_113({
        color: "warning",
        ...{ class: "mr-2" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_113));
    /** @type {__VLS_StyleScopedClasses['mr-2']} */ ;
    var __VLS_115;
    const { default: __VLS_117 } = __VLS_nonNull(__VLS_115.slots);
    // @ts-ignore
    [reverseDialog,];
    // @ts-ignore
    [];
    if (reverseTarget.value) {
        let __VLS_118;
        /** @ts-ignore @type { | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text'] | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text']} */
        vCardText;
        // @ts-ignore
        const __VLS_119 = __VLS_asFunctionalComponent1(__VLS_118, new __VLS_118({
        // @ts-ignore
        }));
        const __VLS_120 = __VLS_119({}, ...__VLS_functionalComponentArgsRest(__VLS_119));
        var __VLS_121;
        const { default: __VLS_123 } = __VLS_nonNull(__VLS_121.slots);
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "mb-3" },
        });
        /** @type {__VLS_StyleScopedClasses['mb-3']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
            ...{ class: "font-weight-bold" },
        });
        /** @type {__VLS_StyleScopedClasses['font-weight-bold']} */ ;
        (reverseTarget.value.full_symbol);
        let __VLS_124;
        /** @ts-ignore @type { | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon'] | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon']} */
        vIcon;
        // @ts-ignore
        const __VLS_125 = __VLS_asFunctionalComponent1(__VLS_124, new __VLS_124({
            // @ts-ignore
            size: "small", ...{ class: "mx-2" },
        }));
        const __VLS_126 = __VLS_125({
            size: "small",
            ...{ class: "mx-2" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_125));
        /** @type {__VLS_StyleScopedClasses['mx-2']} */ ;
        var __VLS_127;
        const { default: __VLS_129 } = __VLS_nonNull(__VLS_127.slots);
        // @ts-ignore
        [reverseTarget, reverseTarget,];
        let __VLS_130;
        /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
        vChip;
        // @ts-ignore
        const __VLS_131 = __VLS_asFunctionalComponent1(__VLS_130, new __VLS_130({
            // @ts-ignore
            color: (reverseTarget.value.side === 'long' ? 'error' : 'success'), size: "small", label: true,
        }));
        const __VLS_132 = __VLS_131({
            color: (reverseTarget.value.side === 'long' ? 'error' : 'success'),
            size: "small",
            label: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_131));
        var __VLS_133;
        const { default: __VLS_135 } = __VLS_nonNull(__VLS_133.slots);
        (reverseTarget.value.side === 'long' ? '做空' : '做多');
        // @ts-ignore
        [reverseTarget, reverseTarget,];
        let __VLS_136;
        /** @ts-ignore @type { | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert'] | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert']} */
        vAlert;
        // @ts-ignore
        const __VLS_137 = __VLS_asFunctionalComponent1(__VLS_136, new __VLS_136({
            // @ts-ignore
            type: "warning", variant: "tonal", density: "compact", ...{ class: "mb-4" },
        }));
        const __VLS_138 = __VLS_137({
            type: "warning",
            variant: "tonal",
            density: "compact",
            ...{ class: "mb-4" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_137));
        /** @type {__VLS_StyleScopedClasses['mb-4']} */ ;
        var __VLS_139;
        const { default: __VLS_141 } = __VLS_nonNull(__VLS_139.slots);
        __VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
        // @ts-ignore
        [];
        let __VLS_142;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_143 = __VLS_asFunctionalComponent1(__VLS_142, new __VLS_142({
            // @ts-ignore
            modelValue: (__VLS_unwrap(reverseValue, {})), modelModifiers: { number: true, }, label: "反手后目标价值 (USD)", type: "number", min: "1", step: "1", variant: "outlined", density: "compact", rules: ([(v) => v > 0 || '价值必须大于 0']), hideDetails: "auto",
        }));
        const __VLS_144 = __VLS_143({
            modelValue: (__VLS_unwrap(reverseValue, {})),
            modelModifiers: { number: true, },
            label: "反手后目标价值 (USD)",
            type: "number",
            min: "1",
            step: "1",
            variant: "outlined",
            density: "compact",
            rules: ([(v) => v > 0 || '价值必须大于 0']),
            hideDetails: "auto",
        }, ...__VLS_functionalComponentArgsRest(__VLS_143));
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "text-caption text-grey mt-1" },
        });
        /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
        /** @type {__VLS_StyleScopedClasses['mt-1']} */ ;
        (reverseTarget.value.notional.toFixed(2));
        // @ts-ignore
        [reverseTarget, reverseValue,];
    }
    let __VLS_147;
    /** @ts-ignore @type { | typeof __VLS_components.vCardActions | typeof __VLS_components.VCardActions | typeof __VLS_components['v-card-actions'] | typeof __VLS_components.vCardActions | typeof __VLS_components.VCardActions | typeof __VLS_components['v-card-actions']} */
    vCardActions;
    // @ts-ignore
    const __VLS_148 = __VLS_asFunctionalComponent1(__VLS_147, new __VLS_147({
    // @ts-ignore
    }));
    const __VLS_149 = __VLS_148({}, ...__VLS_functionalComponentArgsRest(__VLS_148));
    var __VLS_150;
    const { default: __VLS_152 } = __VLS_nonNull(__VLS_150.slots);
    let __VLS_153;
    /** @ts-ignore @type { | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer'] | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer']} */
    vSpacer;
    // @ts-ignore
    const __VLS_154 = __VLS_asFunctionalComponent1(__VLS_153, new __VLS_153({
    // @ts-ignore
    }));
    const __VLS_155 = __VLS_154({}, ...__VLS_functionalComponentArgsRest(__VLS_154));
    let __VLS_158;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_159 = __VLS_asFunctionalComponent1(__VLS_158, new __VLS_158({
        // @ts-ignore
        ...{ 'onClick': {} }, variant: "text",
    }));
    const __VLS_160 = __VLS_159({
        ...{ 'onClick': {} },
        variant: "text",
    }, ...__VLS_functionalComponentArgsRest(__VLS_159));
    let __VLS_163;
    const __VLS_164 = {
        /** @type {typeof __VLS_163.click} */
        onClick: (...[$event]) => {
            void $event;
            return (reverseDialog.value = false);
            // @ts-ignore
            [reverseDialog,];
        },
    };
    void __VLS_164;
    var __VLS_161;
    var __VLS_162;
    const { default: __VLS_165 } = __VLS_nonNull(__VLS_161.slots);
    // @ts-ignore
    [];
    let __VLS_166;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_167 = __VLS_asFunctionalComponent1(__VLS_166, new __VLS_166({
        // @ts-ignore
        ...{ 'onClick': {} }, color: "warning", variant: "tonal", disabled: (!(__VLS_unwrap(reverseValue, {}) > 0) || uiStore.value.isRunning),
    }));
    const __VLS_168 = __VLS_167({
        ...{ 'onClick': {} },
        color: "warning",
        variant: "tonal",
        disabled: (!(__VLS_unwrap(reverseValue, {}) > 0) || uiStore.value.isRunning),
    }, ...__VLS_functionalComponentArgsRest(__VLS_167));
    let __VLS_171;
    const __VLS_172 = {
        /** @type {typeof __VLS_171.click} */
        onClick: (__VLS_unwrap(confirmReverse, {})),
    };
    void __VLS_172;
    var __VLS_169;
    var __VLS_170;
    const { default: __VLS_173 } = __VLS_nonNull(__VLS_169.slots);
    // @ts-ignore
    [uiStore, reverseValue, confirmReverse,];
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
    return {};
};
void [__VLS_template];
const __VLS_export = (await import('vue')).defineComponent({
    emits: {},
    __typeProps: {},
});
export default {};
