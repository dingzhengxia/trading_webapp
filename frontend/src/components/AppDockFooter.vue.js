import { computed } from 'vue';
import { useDisplay, useLayout } from 'vuetify';
// useDisplay() 上没有 application，侧边栏宽度需从 useLayout().mainRect 获取
const vuetifyDisplay = useDisplay();
const vuetifyLayout = useLayout();
const footerStyle = computed(() => {
    const styles = {
        bottom: vuetifyDisplay.smAndDown.value ? '56px' : '0px',
        left: '0px',
    };
    if (vuetifyDisplay.mdAndUp.value) {
        styles.left = `${vuetifyLayout.mainRect.value.left}px`;
    }
    return styles;
});
const __VLS_ctx = {};
let __VLS_components;
let __VLS_intrinsics;
let __VLS_directives;
void __VLS_ctx, __VLS_components, __VLS_intrinsics, __VLS_directives;
const __VLS_template = () => {
    let __VLS_0;
    /** @ts-ignore @type { | typeof __VLS_components.vFooter | typeof __VLS_components.VFooter | typeof __VLS_components['v-footer'] | typeof __VLS_components.vFooter | typeof __VLS_components.VFooter | typeof __VLS_components['v-footer']} */
    vFooter;
    // @ts-ignore
    const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
        // @ts-ignore
        ...{ style: {} }, ...{ class: "pa-0" }, ...{ style: (__VLS_unwrap(footerStyle, {})) },
    }));
    const __VLS_2 = __VLS_1({
        ...{ style: {} },
        ...{ class: "pa-0" },
        ...{ style: (__VLS_unwrap(footerStyle, {})) },
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
        flat: true, tile: true, ...{ class: "d-flex align-center px-4 w-100" }, height: "64px",
    }));
    const __VLS_8 = __VLS_7({
        flat: true,
        tile: true,
        ...{ class: "d-flex align-center px-4 w-100" },
        height: "64px",
    }, ...__VLS_functionalComponentArgsRest(__VLS_7));
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
    /** @type {__VLS_StyleScopedClasses['px-4']} */ ;
    /** @type {__VLS_StyleScopedClasses['w-100']} */ ;
    var __VLS_9;
    const { default: __VLS_11 } = __VLS_nonNull(__VLS_9.slots);
    let __VLS_12;
    /** @ts-ignore @type { | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer'] | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer']} */
    vSpacer;
    // @ts-ignore
    const __VLS_13 = __VLS_asFunctionalComponent1(__VLS_12, new __VLS_12({
    // @ts-ignore
    }));
    const __VLS_14 = __VLS_13({}, ...__VLS_functionalComponentArgsRest(__VLS_13));
    var __VLS_17 = {};
    // @ts-ignore
    [footerStyle,];
    // @ts-ignore
    [];
    var __VLS_18 = __VLS_17;
    // @ts-ignore
    [];
    return {
        __VLS_Slots: {},
    };
};
void [__VLS_template, {}];
const __VLS_base = (await import('vue')).defineComponent({});
const __VLS_export = {};
export default {};
