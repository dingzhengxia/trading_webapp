import { useSnackbarStore } from '@/stores/snackbar';
const snackbarStore = useSnackbarStore();
const __VLS_ctx = {};
let __VLS_components;
let __VLS_intrinsics;
let __VLS_directives;
void __VLS_ctx, __VLS_components, __VLS_intrinsics, __VLS_directives;
const __VLS_template = () => {
    __VLS_withDotValue(snackbarStore, {});
    let __VLS_0;
    /** @ts-ignore @type { | typeof __VLS_components.vSnackbar | typeof __VLS_components.VSnackbar | typeof __VLS_components['v-snackbar'] | typeof __VLS_components.vSnackbar | typeof __VLS_components.VSnackbar | typeof __VLS_components['v-snackbar']} */
    vSnackbar;
    // @ts-ignore
    const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
        // @ts-ignore
        modelValue: (snackbarStore.value.visible), timeout: (snackbarStore.value.timeout), color: (snackbarStore.value.color), location: "bottom right",
    }));
    const __VLS_2 = __VLS_1({
        modelValue: (snackbarStore.value.visible),
        timeout: (snackbarStore.value.timeout),
        color: (snackbarStore.value.color),
        location: "bottom right",
    }, ...__VLS_functionalComponentArgsRest(__VLS_1));
    var __VLS_3;
    const { default: __VLS_5 } = __VLS_nonNull(__VLS_3.slots);
    (snackbarStore.value.message);
    {
        const { actions: __VLS_6 } = __VLS_nonNull(__VLS_3.slots);
        let __VLS_7;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_8 = __VLS_asFunctionalComponent1(__VLS_7, new __VLS_7({
            // @ts-ignore
            ...{ 'onClick': {} }, variant: "text",
        }));
        const __VLS_9 = __VLS_8({
            ...{ 'onClick': {} },
            variant: "text",
        }, ...__VLS_functionalComponentArgsRest(__VLS_8));
        let __VLS_12;
        const __VLS_13 = {
            /** @type {typeof __VLS_12.click} */
            onClick: (...[$event]) => {
                void $event;
                return (snackbarStore.value.hide());
                // @ts-ignore
                [snackbarStore, snackbarStore, snackbarStore, snackbarStore, snackbarStore,];
            },
        };
        void __VLS_13;
        var __VLS_10;
        var __VLS_11;
        const { default: __VLS_14 } = __VLS_nonNull(__VLS_10.slots);
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
