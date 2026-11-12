import { computed } from 'vue';
import { useUiStore } from '@/stores/uiStore';
import api from '@/services/api';
const uiStore = useUiStore();
const progressPercentage = computed(() => {
    const total = uiStore.progress.total;
    if (total === 0)
        return 0;
    const processed = uiStore.progress.success_count + uiStore.progress.failed_count;
    return (processed / total) * 100;
});
const stopTrading = () => {
    uiStore.initiateStop();
    api.post('/api/trading/stop').catch((e) => {
        uiStore.logStore.addLog({
            message: `发送停止指令失败: ${e.message}`,
            level: 'error',
            timestamp: new Date().toLocaleTimeString(),
        });
        uiStore.setStatus('停止失败', false);
    });
};
const cardColor = computed(() => {
    if (uiStore.isStopping)
        return 'red-darken-3';
    const hasErrors = uiStore.progress.failed_count > 0;
    if (uiStore.progress.is_final) {
        return hasErrors ? 'red-darken-3' : 'green-darken-3';
    }
    return hasErrors ? 'red-darken-3' : 'blue-grey-darken-3';
});
const progressColor = computed(() => {
    if (uiStore.isStopping)
        return 'white';
    return uiStore.progress.failed_count > 0 ? 'red-lighten-2' : 'light-blue-accent-3';
});
const __VLS_ctx = {};
let __VLS_components;
let __VLS_intrinsics;
let __VLS_directives;
void __VLS_ctx, __VLS_components, __VLS_intrinsics, __VLS_directives;
const __VLS_template = () => {
    __VLS_withDotValue(uiStore, {});
    if (uiStore.value.progress.show) {
        let __VLS_0;
        /** @ts-ignore @type { | typeof __VLS_components.vFooter | typeof __VLS_components.VFooter | typeof __VLS_components['v-footer'] | typeof __VLS_components.vFooter | typeof __VLS_components.VFooter | typeof __VLS_components['v-footer']} */
        vFooter;
        // @ts-ignore
        const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
            // @ts-ignore
            app: true, ...{ class: "pa-0" }, ...{ style: {} },
        }));
        const __VLS_2 = __VLS_1({
            app: true,
            ...{ class: "pa-0" },
            ...{ style: {} },
        }, ...__VLS_functionalComponentArgsRest(__VLS_1));
        /** @type {__VLS_StyleScopedClasses['pa-0']} */ ;
        var __VLS_3;
        const { default: __VLS_5 } = __VLS_nonNull(__VLS_3.slots);
        let __VLS_6;
        /** @ts-ignore @type { | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card'] | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card']} */
        vCard;
        // @ts-ignore
        const __VLS_7 = __VLS_asFunctionalComponent1(__VLS_6, new __VLS_6({
            // @ts-ignore
            flat: true, tile: true, ...{ class: "d-flex align-center px-2 px-sm-4 w-100" }, color: (__VLS_unwrap(cardColor, {})), height: "48px",
        }));
        const __VLS_8 = __VLS_7({
            flat: true,
            tile: true,
            ...{ class: "d-flex align-center px-2 px-sm-4 w-100" },
            color: (__VLS_unwrap(cardColor, {})),
            height: "48px",
        }, ...__VLS_functionalComponentArgsRest(__VLS_7));
        /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
        /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
        /** @type {__VLS_StyleScopedClasses['px-2']} */ ;
        /** @type {__VLS_StyleScopedClasses['px-sm-4']} */ ;
        /** @type {__VLS_StyleScopedClasses['w-100']} */ ;
        var __VLS_9;
        const { default: __VLS_11 } = __VLS_nonNull(__VLS_9.slots);
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
            ...{ class: "text-caption font-weight-bold flex-shrink-0 mr-4 d-none d-md-flex" },
        });
        /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
        /** @type {__VLS_StyleScopedClasses['font-weight-bold']} */ ;
        /** @type {__VLS_StyleScopedClasses['flex-shrink-0']} */ ;
        /** @type {__VLS_StyleScopedClasses['mr-4']} */ ;
        /** @type {__VLS_StyleScopedClasses['d-none']} */ ;
        /** @type {__VLS_StyleScopedClasses['d-md-flex']} */ ;
        (uiStore.value.progress.task_name);
        let __VLS_12;
        /** @ts-ignore @type { | typeof __VLS_components.vProgressLinear | typeof __VLS_components.VProgressLinear | typeof __VLS_components['v-progress-linear'] | typeof __VLS_components.vProgressLinear | typeof __VLS_components.VProgressLinear | typeof __VLS_components['v-progress-linear']} */
        vProgressLinear;
        // @ts-ignore
        const __VLS_13 = __VLS_asFunctionalComponent1(__VLS_12, new __VLS_12({
            // @ts-ignore
            modelValue: (__VLS_unwrap(progressPercentage, {})), color: (__VLS_unwrap(progressColor, {})), indeterminate: (uiStore.value.isStopping), height: "25", rounded: true, striped: (!uiStore.value.isStopping), stream: true, ...{ class: "flex-grow-1 font-weight-bold" },
        }));
        const __VLS_14 = __VLS_13({
            modelValue: (__VLS_unwrap(progressPercentage, {})),
            color: (__VLS_unwrap(progressColor, {})),
            indeterminate: (uiStore.value.isStopping),
            height: "25",
            rounded: true,
            striped: (!uiStore.value.isStopping),
            stream: true,
            ...{ class: "flex-grow-1 font-weight-bold" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_13));
        /** @type {__VLS_StyleScopedClasses['flex-grow-1']} */ ;
        /** @type {__VLS_StyleScopedClasses['font-weight-bold']} */ ;
        var __VLS_15;
        const { default: __VLS_17 } = __VLS_nonNull(__VLS_15.slots);
        {
            const { default: __VLS_18 } = __VLS_nonNull(__VLS_15.slots);
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                ...{ class: "d-flex justify-space-between align-center w-100 px-2 text-white text-caption" },
            });
            /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
            /** @type {__VLS_StyleScopedClasses['justify-space-between']} */ ;
            /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
            /** @type {__VLS_StyleScopedClasses['w-100']} */ ;
            /** @type {__VLS_StyleScopedClasses['px-2']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-white']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
                ...{ class: "d-md-none" },
            });
            /** @type {__VLS_StyleScopedClasses['d-md-none']} */ ;
            (uiStore.value.progress.task_name);
            let __VLS_19;
            /** @ts-ignore @type { | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer'] | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer']} */
            vSpacer;
            // @ts-ignore
            const __VLS_20 = __VLS_asFunctionalComponent1(__VLS_19, new __VLS_19({
                // @ts-ignore
                ...{ class: "d-md-none" },
            }));
            const __VLS_21 = __VLS_20({
                ...{ class: "d-md-none" },
            }, ...__VLS_functionalComponentArgsRest(__VLS_20));
            /** @type {__VLS_StyleScopedClasses['d-md-none']} */ ;
            if (!uiStore.value.isStopping) {
                __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
                    ...{ class: "mx-2" },
                });
                /** @type {__VLS_StyleScopedClasses['mx-2']} */ ;
                (Math.ceil(__VLS_unwrap(progressPercentage, {})));
            }
            else {
                __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
                    ...{ class: "mx-2" },
                });
                /** @type {__VLS_StyleScopedClasses['mx-2']} */ ;
            }
            let __VLS_24;
            /** @ts-ignore @type { | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer'] | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer']} */
            vSpacer;
            // @ts-ignore
            const __VLS_25 = __VLS_asFunctionalComponent1(__VLS_24, new __VLS_24({
            // @ts-ignore
            }));
            const __VLS_26 = __VLS_25({}, ...__VLS_functionalComponentArgsRest(__VLS_25));
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                ...{ class: "d-flex align-center" },
            });
            /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
            /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
            let __VLS_29;
            /** @ts-ignore @type { | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon'] | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon']} */
            vIcon;
            // @ts-ignore
            const __VLS_30 = __VLS_asFunctionalComponent1(__VLS_29, new __VLS_29({
                // @ts-ignore
                size: "small", color: "light-green-accent-3", ...{ class: "mr-1" },
            }));
            const __VLS_31 = __VLS_30({
                size: "small",
                color: "light-green-accent-3",
                ...{ class: "mr-1" },
            }, ...__VLS_functionalComponentArgsRest(__VLS_30));
            /** @type {__VLS_StyleScopedClasses['mr-1']} */ ;
            var __VLS_32;
            const { default: __VLS_34 } = __VLS_nonNull(__VLS_32.slots);
            // @ts-ignore
            [uiStore, uiStore, uiStore, uiStore, uiStore, uiStore, cardColor, progressPercentage, progressPercentage, progressColor,];
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
            (uiStore.value.progress.success_count);
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
                ...{ class: "mx-1" },
            });
            /** @type {__VLS_StyleScopedClasses['mx-1']} */ ;
            let __VLS_35;
            /** @ts-ignore @type { | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon'] | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon']} */
            vIcon;
            // @ts-ignore
            const __VLS_36 = __VLS_asFunctionalComponent1(__VLS_35, new __VLS_35({
                // @ts-ignore
                size: "small", color: (uiStore.value.progress.failed_count > 0 ? 'red-accent-2' : 'grey-lighten-1'), ...{ class: "mr-1" },
            }));
            const __VLS_37 = __VLS_36({
                size: "small",
                color: (uiStore.value.progress.failed_count > 0 ? 'red-accent-2' : 'grey-lighten-1'),
                ...{ class: "mr-1" },
            }, ...__VLS_functionalComponentArgsRest(__VLS_36));
            /** @type {__VLS_StyleScopedClasses['mr-1']} */ ;
            var __VLS_38;
            const { default: __VLS_40 } = __VLS_nonNull(__VLS_38.slots);
            // @ts-ignore
            [uiStore, uiStore,];
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
            (uiStore.value.progress.failed_count);
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
                ...{ class: "mx-1" },
            });
            /** @type {__VLS_StyleScopedClasses['mx-1']} */ ;
            let __VLS_41;
            /** @ts-ignore @type { | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon'] | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon']} */
            vIcon;
            // @ts-ignore
            const __VLS_42 = __VLS_asFunctionalComponent1(__VLS_41, new __VLS_41({
                // @ts-ignore
                size: "small", color: "grey-lighten-1", ...{ class: "mr-1" },
            }));
            const __VLS_43 = __VLS_42({
                size: "small",
                color: "grey-lighten-1",
                ...{ class: "mr-1" },
            }, ...__VLS_functionalComponentArgsRest(__VLS_42));
            /** @type {__VLS_StyleScopedClasses['mr-1']} */ ;
            var __VLS_44;
            const { default: __VLS_46 } = __VLS_nonNull(__VLS_44.slots);
            // @ts-ignore
            [uiStore,];
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
            (uiStore.value.progress.total);
            // @ts-ignore
            [uiStore,];
        }
        // @ts-ignore
        [];
        let __VLS_47;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_48 = __VLS_asFunctionalComponent1(__VLS_47, new __VLS_47({
            // @ts-ignore
            ...{ 'onClick': {} }, color: "white", variant: "text", size: "small", disabled: (!uiStore.value.isRunning || uiStore.value.isStopping), loading: (uiStore.value.isStopping), ...{ class: "flex-shrink-0 ml-2" }, icon: "mdi-stop-circle-outline",
        }));
        const __VLS_49 = __VLS_48({
            ...{ 'onClick': {} },
            color: "white",
            variant: "text",
            size: "small",
            disabled: (!uiStore.value.isRunning || uiStore.value.isStopping),
            loading: (uiStore.value.isStopping),
            ...{ class: "flex-shrink-0 ml-2" },
            icon: "mdi-stop-circle-outline",
        }, ...__VLS_functionalComponentArgsRest(__VLS_48));
        let __VLS_52;
        const __VLS_53 = {
            /** @type {typeof __VLS_52.click} */
            onClick: (__VLS_unwrap(stopTrading, {})),
        };
        void __VLS_53;
        /** @type {__VLS_StyleScopedClasses['flex-shrink-0']} */ ;
        /** @type {__VLS_StyleScopedClasses['ml-2']} */ ;
        var __VLS_50;
        var __VLS_51;
        // @ts-ignore
        [uiStore, uiStore, uiStore, stopTrading,];
        // @ts-ignore
        [];
    }
    // @ts-ignore
    [];
    return {};
};
void [__VLS_template];
const __VLS_export = (await import('vue')).defineComponent({});
export default {};
