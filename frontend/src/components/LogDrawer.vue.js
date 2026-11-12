import { useLogStore } from '@/stores/logStore';
const { defineModel, } = {};
// v-virtual-scroll 的 slot item 类型为 unknown，这里收窄为 LogEntry
const toLogEntry = (item) => item;
// --- 核心修改在这里 ---
// 使用 defineModel 来创建一个双向绑定的 v-model
const show = defineModel();
// -----------------------
const logStore = useLogStore();
// 样式函数保持不变
const logLevelColor = (level) => {
    switch (level) {
        case 'success':
            return 'text-success';
        case 'error':
            return 'text-error';
        case 'warning':
            return 'text-orange';
        case 'info':
            return 'text-info';
        default:
            return '';
    }
};
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
    __VLS_withDotValue(logStore, {});
    void {};
    let __VLS_0;
    /** @ts-ignore @type { | typeof __VLS_components.vNavigationDrawer | typeof __VLS_components.VNavigationDrawer | typeof __VLS_components['v-navigation-drawer'] | typeof __VLS_components.vNavigationDrawer | typeof __VLS_components.VNavigationDrawer | typeof __VLS_components['v-navigation-drawer']} */
    vNavigationDrawer;
    // @ts-ignore
    const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
        // @ts-ignore
        modelValue: (__VLS_unwrap(show, {})), location: "right", width: "400", ...{ class: "log-drawer" },
    }));
    const __VLS_2 = __VLS_1({
        modelValue: (__VLS_unwrap(show, {})),
        location: "right",
        width: "400",
        ...{ class: "log-drawer" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_1));
    /** @type {__VLS_StyleScopedClasses['log-drawer']} */ ;
    var __VLS_3;
    const { default: __VLS_5 } = __VLS_nonNull(__VLS_3.slots);
    let __VLS_6;
    /** @ts-ignore @type { | typeof __VLS_components.vToolbar | typeof __VLS_components.VToolbar | typeof __VLS_components['v-toolbar'] | typeof __VLS_components.vToolbar | typeof __VLS_components.VToolbar | typeof __VLS_components['v-toolbar']} */
    vToolbar;
    // @ts-ignore
    const __VLS_7 = __VLS_asFunctionalComponent1(__VLS_6, new __VLS_6({
        // @ts-ignore
        density: "compact",
    }));
    const __VLS_8 = __VLS_7({
        density: "compact",
    }, ...__VLS_functionalComponentArgsRest(__VLS_7));
    var __VLS_9;
    const { default: __VLS_11 } = __VLS_nonNull(__VLS_9.slots);
    let __VLS_12;
    /** @ts-ignore @type { | typeof __VLS_components.vToolbarTitle | typeof __VLS_components.VToolbarTitle | typeof __VLS_components['v-toolbar-title'] | typeof __VLS_components.vToolbarTitle | typeof __VLS_components.VToolbarTitle | typeof __VLS_components['v-toolbar-title']} */
    vToolbarTitle;
    // @ts-ignore
    const __VLS_13 = __VLS_asFunctionalComponent1(__VLS_12, new __VLS_12({
        // @ts-ignore
        ...{ class: "text-subtitle-1" },
    }));
    const __VLS_14 = __VLS_13({
        ...{ class: "text-subtitle-1" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_13));
    /** @type {__VLS_StyleScopedClasses['text-subtitle-1']} */ ;
    var __VLS_15;
    const { default: __VLS_17 } = __VLS_nonNull(__VLS_15.slots);
    // @ts-ignore
    [show,];
    let __VLS_18;
    /** @ts-ignore @type { | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer'] | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer']} */
    vSpacer;
    // @ts-ignore
    const __VLS_19 = __VLS_asFunctionalComponent1(__VLS_18, new __VLS_18({
    // @ts-ignore
    }));
    const __VLS_20 = __VLS_19({}, ...__VLS_functionalComponentArgsRest(__VLS_19));
    let __VLS_23;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_24 = __VLS_asFunctionalComponent1(__VLS_23, new __VLS_23({
        // @ts-ignore
        ...{ 'onClick': {} }, icon: "mdi-delete", size: "small", title: "清空日志",
    }));
    const __VLS_25 = __VLS_24({
        ...{ 'onClick': {} },
        icon: "mdi-delete",
        size: "small",
        title: "清空日志",
    }, ...__VLS_functionalComponentArgsRest(__VLS_24));
    let __VLS_28;
    const __VLS_29 = {
        /** @type {typeof __VLS_28.click} */
        onClick: (...[$event]) => {
            void $event;
            return (logStore.value.clearLogs());
            // @ts-ignore
            [logStore,];
        },
    };
    void __VLS_29;
    var __VLS_26;
    var __VLS_27;
    // @ts-ignore
    [];
    let __VLS_30;
    /** @ts-ignore @type { | typeof __VLS_components.vVirtualScroll | typeof __VLS_components.VVirtualScroll | typeof __VLS_components['v-virtual-scroll'] | typeof __VLS_components.vVirtualScroll | typeof __VLS_components.VVirtualScroll | typeof __VLS_components['v-virtual-scroll']} */
    vVirtualScroll;
    // @ts-ignore
    const __VLS_31 = __VLS_asFunctionalComponent1(__VLS_30, new __VLS_30({
        // @ts-ignore
        items: (logStore.value.logs), height: "calc(100vh - 48px)",
    }));
    const __VLS_32 = __VLS_31({
        items: (logStore.value.logs),
        height: "calc(100vh - 48px)",
    }, ...__VLS_functionalComponentArgsRest(__VLS_31));
    var __VLS_33;
    const { default: __VLS_35 } = __VLS_nonNull(__VLS_33.slots);
    {
        const { default: __VLS_36 } = __VLS_nonNull(__VLS_33.slots);
        const [{ item, index }] = __VLS_vSlot(__VLS_nonNull(__VLS_36));
        let __VLS_37;
        /** @ts-ignore @type { | typeof __VLS_components.vListItem | typeof __VLS_components.VListItem | typeof __VLS_components['v-list-item'] | typeof __VLS_components.vListItem | typeof __VLS_components.VListItem | typeof __VLS_components['v-list-item']} */
        vListItem;
        // @ts-ignore
        const __VLS_38 = __VLS_asFunctionalComponent1(__VLS_37, new __VLS_37({
            // @ts-ignore
            key: (index), ...{ class: "py-1 px-2" },
        }));
        const __VLS_39 = __VLS_38({
            key: (index),
            ...{ class: "py-1 px-2" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_38));
        /** @type {__VLS_StyleScopedClasses['py-1']} */ ;
        /** @type {__VLS_StyleScopedClasses['px-2']} */ ;
        var __VLS_40;
        const { default: __VLS_42 } = __VLS_nonNull(__VLS_40.slots);
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "log-entry" },
            ...{ class: (__VLS_unwrap(logLevelColor, {})(__VLS_unwrap(toLogEntry, {})(item).level)) },
        });
        /** @type {__VLS_StyleScopedClasses['log-entry']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
            ...{ class: "log-timestamp text-grey" },
        });
        /** @type {__VLS_StyleScopedClasses['log-timestamp']} */ ;
        /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
        (__VLS_unwrap(toLogEntry, {})(item).timestamp);
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
            ...{ class: "log-message" },
        });
        /** @type {__VLS_StyleScopedClasses['log-message']} */ ;
        (__VLS_unwrap(toLogEntry, {})(item).message);
        // @ts-ignore
        [logStore, logLevelColor, toLogEntry, toLogEntry, toLogEntry,];
        // @ts-ignore
        [];
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
const __VLS_export = (await import('vue')).defineComponent({
    __typeEmits: {},
    __typeProps: {},
});
export default {};
