import { ref, computed, watch } from 'vue';
import { useUiStore } from '@/stores/uiStore';
import { usePositionStore } from '@/stores/positionStore';
const uiStore = useUiStore();
const positionStore = usePositionStore();
const closeRatio = ref(100);
const dialogTitle = computed(() => {
    const target = uiStore.closeTarget;
    if (!target)
        return '确认平仓';
    if (target.type === 'single')
        return `平仓: ${target.position.symbol}`;
    if (target.type === 'selected')
        return `平掉选中的 ${target.positions.length} 个仓位`;
    if (target.type === 'by_side') {
        if (target.side === 'long')
            return '平掉所有多头';
        if (target.side === 'short')
            return '平掉所有空头';
        if (target.side === 'all')
            return '平掉全部仓位';
    }
    return '确认平仓';
});
const totalNotionalToClose = computed(() => {
    const target = uiStore.closeTarget;
    if (!target)
        return 0;
    switch (target.type) {
        case 'single':
            return target.position.notional;
        case 'selected':
            return target.positions.reduce((sum, p) => sum + p.notional, 0);
        case 'by_side':
            if (target.side === 'long')
                return positionStore.longNotional;
            if (target.side === 'short')
                return positionStore.shortNotional;
            return positionStore.longNotional + positionStore.shortNotional;
        default:
            return 0;
    }
});
const closeValue = computed(() => {
    const ratio = Math.max(0, Math.min(100, Number(closeRatio.value) || 0));
    return totalNotionalToClose.value * (ratio / 100);
});
watch(closeRatio, (newValue) => {
    const numValue = Number(newValue);
    if (isNaN(numValue) || numValue < 0) {
        closeRatio.value = 0;
    }
    else if (numValue > 100) {
        closeRatio.value = 100;
    }
});
const closeDialog = () => {
    uiStore.showCloseDialog = false;
};
watch(() => uiStore.showCloseDialog, (isOpen) => {
    if (isOpen) {
        closeRatio.value = 100;
    }
});
const executeClose = () => {
    const target = uiStore.closeTarget;
    if (!target || uiStore.isRunning || closeRatio.value <= 0)
        return;
    const ratio = closeRatio.value / 100;
    let endpoint = '';
    let payload = {};
    let taskName = '';
    let totalTasks = 0;
    if (target.type === 'single') {
        endpoint = '/api/positions/close';
        payload = { full_symbol: target.position.full_symbol, ratio };
        taskName = `平仓 ${target.position.symbol}`;
        totalTasks = 1;
    }
    else if (target.type === 'by_side') {
        endpoint = '/api/positions/close-by-side';
        payload = { side: target.side, ratio };
        taskName = `批量平仓-${target.side}`;
        if (target.side === 'long')
            totalTasks = positionStore.longPositions.length;
        else if (target.side === 'short')
            totalTasks = positionStore.shortPositions.length;
        else
            totalTasks = positionStore.positions.length;
    }
    else if (target.type === 'selected') {
        const fullSymbols = target.positions.map((p) => p.full_symbol);
        endpoint = '/api/positions/close-multiple';
        payload = { full_symbols: fullSymbols, ratio };
        taskName = '平掉选中';
        totalTasks = fullSymbols.length;
    }
    closeDialog();
    uiStore.launchTask(endpoint, payload, taskName, totalTasks);
};
const __VLS_ctx = {};
let __VLS_components;
let __VLS_intrinsics;
let __VLS_directives;
void __VLS_ctx, __VLS_components, __VLS_intrinsics, __VLS_directives;
const __VLS_template = () => {
    __VLS_withDotValue(uiStore, {});
    __VLS_withDotValue(closeValue, {});
    let __VLS_0;
    /** @ts-ignore @type { | typeof __VLS_components.vDialog | typeof __VLS_components.VDialog | typeof __VLS_components['v-dialog'] | typeof __VLS_components.vDialog | typeof __VLS_components.VDialog | typeof __VLS_components['v-dialog']} */
    vDialog;
    // @ts-ignore
    const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
        // @ts-ignore
        modelValue: (uiStore.value.showCloseDialog), maxWidth: "400px", persistent: true,
    }));
    const __VLS_2 = __VLS_1({
        modelValue: (uiStore.value.showCloseDialog),
        maxWidth: "400px",
        persistent: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_1));
    var __VLS_3;
    const { default: __VLS_5 } = __VLS_nonNull(__VLS_3.slots);
    if (uiStore.value.closeTarget) {
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
            ...{ class: "text-h5 text-center pt-4" },
        }));
        const __VLS_14 = __VLS_13({
            ...{ class: "text-h5 text-center pt-4" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_13));
        /** @type {__VLS_StyleScopedClasses['text-h5']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-center']} */ ;
        /** @type {__VLS_StyleScopedClasses['pt-4']} */ ;
        var __VLS_15;
        const { default: __VLS_17 } = __VLS_nonNull(__VLS_15.slots);
        (__VLS_unwrap(dialogTitle, {}));
        // @ts-ignore
        [uiStore, uiStore, dialogTitle,];
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
            ...{ class: "text-center" },
        });
        /** @type {__VLS_StyleScopedClasses['text-center']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "text-caption text-grey" },
        });
        /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "text-center mt-4 mb-2" },
        });
        /** @type {__VLS_StyleScopedClasses['text-center']} */ ;
        /** @type {__VLS_StyleScopedClasses['mt-4']} */ ;
        /** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "text-caption" },
        });
        /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "text-h4 font-weight-bold text-amber-accent-3 my-1" },
        });
        /** @type {__VLS_StyleScopedClasses['text-h4']} */ ;
        /** @type {__VLS_StyleScopedClasses['font-weight-bold']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-amber-accent-3']} */ ;
        /** @type {__VLS_StyleScopedClasses['my-1']} */ ;
        (closeValue.value.toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }));
        let __VLS_24;
        /** @ts-ignore @type { | typeof __VLS_components.vSlider | typeof __VLS_components.VSlider | typeof __VLS_components['v-slider'] | typeof __VLS_components.vSlider | typeof __VLS_components.VSlider | typeof __VLS_components['v-slider']} */
        vSlider;
        // @ts-ignore
        const __VLS_25 = __VLS_asFunctionalComponent1(__VLS_24, new __VLS_24({
            // @ts-ignore
            modelValue: (__VLS_unwrap(closeRatio, {})), step: (1), color: "primary", ...{ class: "my-4 align-center" }, hideDetails: true,
        }));
        const __VLS_26 = __VLS_25({
            modelValue: (__VLS_unwrap(closeRatio, {})),
            step: (1),
            color: "primary",
            ...{ class: "my-4 align-center" },
            hideDetails: true,
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
            (Math.ceil(modelValue));
            // @ts-ignore
            [closeValue, closeRatio,];
        }
        // @ts-ignore
        [];
        let __VLS_31;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_32 = __VLS_asFunctionalComponent1(__VLS_31, new __VLS_31({
            // @ts-ignore
            modelValue: (__VLS_unwrap(closeRatio, {})), modelModifiers: { number: true, }, type: "number", variant: "outlined", density: "compact", hideDetails: true, suffix: "%", ...{ class: "mx-auto" }, ...{ style: {} },
        }));
        const __VLS_33 = __VLS_32({
            modelValue: (__VLS_unwrap(closeRatio, {})),
            modelModifiers: { number: true, },
            type: "number",
            variant: "outlined",
            density: "compact",
            hideDetails: true,
            suffix: "%",
            ...{ class: "mx-auto" },
            ...{ style: {} },
        }, ...__VLS_functionalComponentArgsRest(__VLS_32));
        /** @type {__VLS_StyleScopedClasses['mx-auto']} */ ;
        // @ts-ignore
        [closeRatio,];
        let __VLS_36;
        /** @ts-ignore @type { | typeof __VLS_components.vCardActions | typeof __VLS_components.VCardActions | typeof __VLS_components['v-card-actions'] | typeof __VLS_components.vCardActions | typeof __VLS_components.VCardActions | typeof __VLS_components['v-card-actions']} */
        vCardActions;
        // @ts-ignore
        const __VLS_37 = __VLS_asFunctionalComponent1(__VLS_36, new __VLS_36({
            // @ts-ignore
            ...{ class: "pa-4" },
        }));
        const __VLS_38 = __VLS_37({
            ...{ class: "pa-4" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_37));
        /** @type {__VLS_StyleScopedClasses['pa-4']} */ ;
        var __VLS_39;
        const { default: __VLS_41 } = __VLS_nonNull(__VLS_39.slots);
        let __VLS_42;
        /** @ts-ignore @type { | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer'] | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer']} */
        vSpacer;
        // @ts-ignore
        const __VLS_43 = __VLS_asFunctionalComponent1(__VLS_42, new __VLS_42({
        // @ts-ignore
        }));
        const __VLS_44 = __VLS_43({}, ...__VLS_functionalComponentArgsRest(__VLS_43));
        let __VLS_47;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_48 = __VLS_asFunctionalComponent1(__VLS_47, new __VLS_47({
            // @ts-ignore
            ...{ 'onClick': {} }, color: "grey", variant: "text", ...{ class: "mr-2" },
        }));
        const __VLS_49 = __VLS_48({
            ...{ 'onClick': {} },
            color: "grey",
            variant: "text",
            ...{ class: "mr-2" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_48));
        let __VLS_52;
        const __VLS_53 = {
            /** @type {typeof __VLS_52.click} */
            onClick: (__VLS_unwrap(closeDialog, {})),
        };
        void __VLS_53;
        /** @type {__VLS_StyleScopedClasses['mr-2']} */ ;
        var __VLS_50;
        var __VLS_51;
        const { default: __VLS_54 } = __VLS_nonNull(__VLS_50.slots);
        // @ts-ignore
        [closeDialog,];
        let __VLS_55;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_56 = __VLS_asFunctionalComponent1(__VLS_55, new __VLS_55({
            // @ts-ignore
            ...{ 'onClick': {} }, color: "red-darken-1", variant: "tonal", disabled: (__VLS_unwrap(closeRatio, {}) <= 0 || uiStore.value.isRunning),
        }));
        const __VLS_57 = __VLS_56({
            ...{ 'onClick': {} },
            color: "red-darken-1",
            variant: "tonal",
            disabled: (__VLS_unwrap(closeRatio, {}) <= 0 || uiStore.value.isRunning),
        }, ...__VLS_functionalComponentArgsRest(__VLS_56));
        let __VLS_60;
        const __VLS_61 = {
            /** @type {typeof __VLS_60.click} */
            onClick: (__VLS_unwrap(executeClose, {})),
        };
        void __VLS_61;
        var __VLS_58;
        var __VLS_59;
        const { default: __VLS_62 } = __VLS_nonNull(__VLS_58.slots);
        (__VLS_unwrap(closeRatio, {}));
        // @ts-ignore
        [uiStore, closeRatio, closeRatio, executeClose,];
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
