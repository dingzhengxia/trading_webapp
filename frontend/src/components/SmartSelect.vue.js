import { computed, ref } from 'vue';
import { useDisplay } from 'vuetify';
const { defineProps, defineEmits, withDefaults, } = {};
const props = withDefaults(defineProps(), {
    items: () => [],
    itemTitle: 'title',
    itemValue: 'value',
    multiple: false,
    disabled: false,
    clearable: false,
    density: 'compact',
    variant: 'outlined',
    hideDetails: true,
    dense: false,
    searchable: false,
});
const emit = defineEmits();
const { smAndDown } = useDisplay();
const isMobile = computed(() => smAndDown.value);
// ---- 手机端全屏选择页 ----
const dialog = ref(false);
const search = ref('');
const normalizedItems = computed(() => props.items.map((raw) => {
    if (raw !== null && typeof raw === 'object') {
        const record = raw;
        return {
            title: String(record[props.itemTitle] ?? ''),
            value: record[props.itemValue],
        };
    }
    return { title: String(raw), value: raw };
}));
const selectedValues = computed(() => {
    const value = props.modelValue;
    if (Array.isArray(value))
        return value;
    if (value === null || value === undefined || value === '')
        return [];
    return [value];
});
const hasValue = computed(() => selectedValues.value.length > 0);
const filteredItems = computed(() => {
    const keyword = search.value.trim().toUpperCase();
    if (!keyword)
        return normalizedItems.value;
    return normalizedItems.value.filter((opt) => opt.title.toUpperCase().includes(keyword));
});
const summary = computed(() => {
    const list = selectedValues.value;
    if (list.length === 0)
        return '';
    const titles = list.map((value) => normalizedItems.value.find((opt) => opt.value === value)?.title ?? String(value));
    if (!props.multiple)
        return titles[0] ?? String(list[0]);
    if (titles.length <= 2)
        return titles.join('、');
    return `${titles.slice(0, 2).join('、')} 等 ${titles.length} 项`;
});
const placeholderText = computed(() => (selectedValues.value.length === 0 ? '点击选择' : ''));
function isSelected(value) {
    return selectedValues.value.includes(value);
}
function onSelect(value) {
    emit('update:modelValue', value);
}
function clear() {
    emit('update:modelValue', props.multiple ? [] : null);
}
function clearAndClose() {
    clear();
    dialog.value = false;
}
function openDialog() {
    if (props.disabled)
        return;
    search.value = '';
    dialog.value = true;
}
function pick(value) {
    if (props.disabled)
        return;
    if (props.multiple) {
        const next = isSelected(value)
            ? selectedValues.value.filter((item) => item !== value)
            : [...selectedValues.value, value];
        emit('update:modelValue', next);
        return;
    }
    // 单选：点选后关闭（再次点已选项且允许清除则取消）
    emit('update:modelValue', isSelected(value) && props.clearable ? null : value);
    dialog.value = false;
}
const __VLS_defaults = {
    items: () => [],
    itemTitle: 'title',
    itemValue: 'value',
    multiple: false,
    disabled: false,
    clearable: false,
    density: 'compact',
    variant: 'outlined',
    hideDetails: true,
    dense: false,
    searchable: false,
};
void __VLS_defaults;
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
    __VLS_withDotValue(isMobile, {});
    __VLS_withDotValue(dialog, {});
    __VLS_withDotValue(filteredItems, {});
    __VLS_withDotValue(hasValue, {});
    __VLS_withDotValue(selectedValues, {});
    void {};
    /** @type {__VLS_StyleScopedClasses['ss-row']} */ ;
    /** @type {__VLS_StyleScopedClasses['ss-row__title']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "smart-select" },
    });
    /** @type {__VLS_StyleScopedClasses['smart-select']} */ ;
    if (isMobile.value) {
        let __VLS_0;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
            // @ts-ignore
            ...{ 'onClick': {} }, modelValue: (__VLS_unwrap(summary, {})), label: (__VLS_ctx.label), readonly: true, variant: (__VLS_ctx.variant), density: (__VLS_ctx.density), hideDetails: (__VLS_ctx.hideDetails), disabled: (__VLS_ctx.disabled), hint: (__VLS_ctx.hint), persistentHint: (!!__VLS_ctx.hint), placeholder: (__VLS_unwrap(placeholderText, {})),
        }));
        const __VLS_2 = __VLS_1({
            ...{ 'onClick': {} },
            modelValue: (__VLS_unwrap(summary, {})),
            label: (__VLS_ctx.label),
            readonly: true,
            variant: (__VLS_ctx.variant),
            density: (__VLS_ctx.density),
            hideDetails: (__VLS_ctx.hideDetails),
            disabled: (__VLS_ctx.disabled),
            hint: (__VLS_ctx.hint),
            persistentHint: (!!__VLS_ctx.hint),
            placeholder: (__VLS_unwrap(placeholderText, {})),
        }, ...__VLS_functionalComponentArgsRest(__VLS_1));
        let __VLS_5;
        const __VLS_6 = {
            /** @type {typeof __VLS_5.click} */
            onClick: (openDialog),
        };
        void __VLS_6;
        var __VLS_3;
        var __VLS_4;
        const { default: __VLS_7 } = __VLS_nonNull(__VLS_3.slots);
        {
            const { 'append-inner': __VLS_8 } = __VLS_nonNull(__VLS_3.slots);
            let __VLS_9;
            /** @ts-ignore @type { | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon']} */
            vIcon;
            // @ts-ignore
            const __VLS_10 = __VLS_asFunctionalComponent1(__VLS_9, new __VLS_9({
                // @ts-ignore
                icon: "mdi-chevron-down", size: "20",
            }));
            const __VLS_11 = __VLS_10({
                icon: "mdi-chevron-down",
                size: "20",
            }, ...__VLS_functionalComponentArgsRest(__VLS_10));
            // @ts-ignore
            [isMobile, summary, label, variant, density, hideDetails, disabled, hint, hint, placeholderText,];
        }
        // @ts-ignore
        [];
        let __VLS_14;
        /** @ts-ignore @type { | typeof __VLS_components.vDialog | typeof __VLS_components.VDialog | typeof __VLS_components['v-dialog'] | typeof __VLS_components.vDialog | typeof __VLS_components.VDialog | typeof __VLS_components['v-dialog']} */
        vDialog;
        // @ts-ignore
        const __VLS_15 = __VLS_asFunctionalComponent1(__VLS_14, new __VLS_14({
            // @ts-ignore
            modelValue: (dialog.value), fullscreen: true, transition: "dialog-bottom-transition",
        }));
        const __VLS_16 = __VLS_15({
            modelValue: (dialog.value),
            fullscreen: true,
            transition: "dialog-bottom-transition",
        }, ...__VLS_functionalComponentArgsRest(__VLS_15));
        var __VLS_17;
        const { default: __VLS_19 } = __VLS_nonNull(__VLS_17.slots);
        let __VLS_20;
        /** @ts-ignore @type { | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card'] | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card']} */
        vCard;
        // @ts-ignore
        const __VLS_21 = __VLS_asFunctionalComponent1(__VLS_20, new __VLS_20({
        // @ts-ignore
        }));
        const __VLS_22 = __VLS_21({}, ...__VLS_functionalComponentArgsRest(__VLS_21));
        var __VLS_23;
        const { default: __VLS_25 } = __VLS_nonNull(__VLS_23.slots);
        let __VLS_26;
        /** @ts-ignore @type { | typeof __VLS_components.vToolbar | typeof __VLS_components.VToolbar | typeof __VLS_components['v-toolbar'] | typeof __VLS_components.vToolbar | typeof __VLS_components.VToolbar | typeof __VLS_components['v-toolbar']} */
        vToolbar;
        // @ts-ignore
        const __VLS_27 = __VLS_asFunctionalComponent1(__VLS_26, new __VLS_26({
            // @ts-ignore
            density: "compact",
        }));
        const __VLS_28 = __VLS_27({
            density: "compact",
        }, ...__VLS_functionalComponentArgsRest(__VLS_27));
        var __VLS_29;
        const { default: __VLS_31 } = __VLS_nonNull(__VLS_29.slots);
        let __VLS_32;
        /** @ts-ignore @type { | typeof __VLS_components.vToolbarTitle | typeof __VLS_components.VToolbarTitle | typeof __VLS_components['v-toolbar-title'] | typeof __VLS_components.vToolbarTitle | typeof __VLS_components.VToolbarTitle | typeof __VLS_components['v-toolbar-title']} */
        vToolbarTitle;
        // @ts-ignore
        const __VLS_33 = __VLS_asFunctionalComponent1(__VLS_32, new __VLS_32({
        // @ts-ignore
        }));
        const __VLS_34 = __VLS_33({}, ...__VLS_functionalComponentArgsRest(__VLS_33));
        var __VLS_35;
        const { default: __VLS_37 } = __VLS_nonNull(__VLS_35.slots);
        (__VLS_ctx.label || '请选择');
        // @ts-ignore
        [label, dialog,];
        let __VLS_38;
        /** @ts-ignore @type { | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer'] | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer']} */
        vSpacer;
        // @ts-ignore
        const __VLS_39 = __VLS_asFunctionalComponent1(__VLS_38, new __VLS_38({
        // @ts-ignore
        }));
        const __VLS_40 = __VLS_39({}, ...__VLS_functionalComponentArgsRest(__VLS_39));
        let __VLS_43;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_44 = __VLS_asFunctionalComponent1(__VLS_43, new __VLS_43({
            // @ts-ignore
            ...{ 'onClick': {} }, icon: "mdi-close",
        }));
        const __VLS_45 = __VLS_44({
            ...{ 'onClick': {} },
            icon: "mdi-close",
        }, ...__VLS_functionalComponentArgsRest(__VLS_44));
        let __VLS_48;
        const __VLS_49 = {
            /** @type {typeof __VLS_48.click} */
            onClick: (...[$event]) => {
                void $event;
                if (!(isMobile.value))
                    throw 0;
                return (dialog.value = false);
                // @ts-ignore
                [dialog,];
            },
        };
        void __VLS_49;
        var __VLS_46;
        var __VLS_47;
        // @ts-ignore
        [];
        let __VLS_50;
        /** @ts-ignore @type { | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider'] | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider']} */
        vDivider;
        // @ts-ignore
        const __VLS_51 = __VLS_asFunctionalComponent1(__VLS_50, new __VLS_50({
        // @ts-ignore
        }));
        const __VLS_52 = __VLS_51({}, ...__VLS_functionalComponentArgsRest(__VLS_51));
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "pa-3" },
        });
        /** @type {__VLS_StyleScopedClasses['pa-3']} */ ;
        let __VLS_55;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_56 = __VLS_asFunctionalComponent1(__VLS_55, new __VLS_55({
            // @ts-ignore
            modelValue: (__VLS_unwrap(search, {})), label: "搜索", prependInnerIcon: "mdi-magnify", variant: "outlined", density: "compact", hideDetails: true, clearable: true,
        }));
        const __VLS_57 = __VLS_56({
            modelValue: (__VLS_unwrap(search, {})),
            label: "搜索",
            prependInnerIcon: "mdi-magnify",
            variant: "outlined",
            density: "compact",
            hideDetails: true,
            clearable: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_56));
        let __VLS_60;
        /** @ts-ignore @type { | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider'] | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider']} */
        vDivider;
        // @ts-ignore
        const __VLS_61 = __VLS_asFunctionalComponent1(__VLS_60, new __VLS_60({
        // @ts-ignore
        }));
        const __VLS_62 = __VLS_61({}, ...__VLS_functionalComponentArgsRest(__VLS_61));
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "ss-list" },
        });
        /** @type {__VLS_StyleScopedClasses['ss-list']} */ ;
        const __VLS_65 = __VLS_tryAsConstant((filteredItems.value));
        for (const [opt] of __VLS_vFor(__VLS_nonNull(__VLS_65))) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                ...{ onClick: (...[$event]) => {
                        void $event;
                        if (!(isMobile.value))
                            throw 0;
                        return (pick(opt.value));
                        // @ts-ignore
                        [search, filteredItems,];
                    } },
                key: (String(opt.value)),
                ...{ class: "ss-row" },
                ...{ class: ({ 'ss-row--on': isSelected(opt.value) }) },
            });
            /** @type {__VLS_StyleScopedClasses['ss-row']} */ ;
            /** @type {__VLS_StyleScopedClasses['ss-row--on']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
                ...{ class: "ss-row__title" },
            });
            /** @type {__VLS_StyleScopedClasses['ss-row__title']} */ ;
            (opt.title);
            let __VLS_66;
            /** @ts-ignore @type { | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon'] | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon']} */
            vIcon;
            // @ts-ignore
            const __VLS_67 = __VLS_asFunctionalComponent1(__VLS_66, new __VLS_66({
                // @ts-ignore
                size: "22", color: (isSelected(opt.value) ? 'primary' : 'grey'), icon: (isSelected(opt.value) ? 'mdi-check-circle' : 'mdi-circle-outline'),
            }));
            const __VLS_68 = __VLS_67({
                size: "22",
                color: (isSelected(opt.value) ? 'primary' : 'grey'),
                icon: (isSelected(opt.value) ? 'mdi-check-circle' : 'mdi-circle-outline'),
            }, ...__VLS_functionalComponentArgsRest(__VLS_67));
            // @ts-ignore
            [];
        }
        if (filteredItems.value.length === 0) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                ...{ class: "pa-6 text-center text-caption text-grey" },
            });
            /** @type {__VLS_StyleScopedClasses['pa-6']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-center']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-grey']} */ ;
        }
        let __VLS_71;
        /** @ts-ignore @type { | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider'] | typeof __VLS_components.vDivider | typeof __VLS_components.VDivider | typeof __VLS_components['v-divider']} */
        vDivider;
        // @ts-ignore
        const __VLS_72 = __VLS_asFunctionalComponent1(__VLS_71, new __VLS_71({
        // @ts-ignore
        }));
        const __VLS_73 = __VLS_72({}, ...__VLS_functionalComponentArgsRest(__VLS_72));
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "pa-3 d-flex align-center ga-2" },
        });
        /** @type {__VLS_StyleScopedClasses['pa-3']} */ ;
        /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
        /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
        /** @type {__VLS_StyleScopedClasses['ga-2']} */ ;
        if (__VLS_ctx.clearable) {
            let __VLS_76;
            /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
            vBtn;
            // @ts-ignore
            const __VLS_77 = __VLS_asFunctionalComponent1(__VLS_76, new __VLS_76({
                // @ts-ignore
                ...{ 'onClick': {} }, variant: "text", ...{ class: "flex-grow-1" }, disabled: (!hasValue.value),
            }));
            const __VLS_78 = __VLS_77({
                ...{ 'onClick': {} },
                variant: "text",
                ...{ class: "flex-grow-1" },
                disabled: (!hasValue.value),
            }, ...__VLS_functionalComponentArgsRest(__VLS_77));
            let __VLS_81;
            const __VLS_82 = {
                /** @type {typeof __VLS_81.click} */
                onClick: (clearAndClose),
            };
            void __VLS_82;
            /** @type {__VLS_StyleScopedClasses['flex-grow-1']} */ ;
            var __VLS_79;
            var __VLS_80;
            const { default: __VLS_83 } = __VLS_nonNull(__VLS_79.slots);
            // @ts-ignore
            [filteredItems, clearable, hasValue,];
        }
        let __VLS_84;
        /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
        vBtn;
        // @ts-ignore
        const __VLS_85 = __VLS_asFunctionalComponent1(__VLS_84, new __VLS_84({
            // @ts-ignore
            ...{ 'onClick': {} }, color: "primary", variant: "tonal", ...{ class: "flex-grow-1" },
        }));
        const __VLS_86 = __VLS_85({
            ...{ 'onClick': {} },
            color: "primary",
            variant: "tonal",
            ...{ class: "flex-grow-1" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_85));
        let __VLS_89;
        const __VLS_90 = {
            /** @type {typeof __VLS_89.click} */
            onClick: (...[$event]) => {
                void $event;
                if (!(isMobile.value))
                    throw 0;
                return (dialog.value = false);
                // @ts-ignore
                [dialog,];
            },
        };
        void __VLS_90;
        /** @type {__VLS_StyleScopedClasses['flex-grow-1']} */ ;
        var __VLS_87;
        var __VLS_88;
        const { default: __VLS_91 } = __VLS_nonNull(__VLS_87.slots);
        (__VLS_ctx.multiple ? `（已选 ${selectedValues.value.length}）` : '');
        // @ts-ignore
        [multiple, selectedValues,];
        // @ts-ignore
        [];
        // @ts-ignore
        [];
    }
    else {
        const __VLS_92 = (__VLS_ctx.searchable ? 'v-autocomplete' : 'v-select');
        // @ts-ignore
        const __VLS_93 = __VLS_asFunctionalComponent1(__VLS_92, new __VLS_92({
            // @ts-ignore
            ...{ 'onUpdate:modelValue': {} }, modelValue: (__VLS_ctx.modelValue), items: (__VLS_ctx.items), itemTitle: (__VLS_ctx.itemTitle), itemValue: (__VLS_ctx.itemValue), label: (__VLS_ctx.label), multiple: (__VLS_ctx.multiple), chips: (__VLS_ctx.multiple), closableChips: (__VLS_ctx.multiple), disabled: (__VLS_ctx.disabled), clearable: (__VLS_ctx.clearable), density: (__VLS_ctx.density), variant: (__VLS_ctx.variant), hideDetails: (__VLS_ctx.hideDetails), hint: (__VLS_ctx.hint), persistentHint: (!!__VLS_ctx.hint),
        }));
        const __VLS_94 = __VLS_93({
            ...{ 'onUpdate:modelValue': {} },
            modelValue: (__VLS_ctx.modelValue),
            items: (__VLS_ctx.items),
            itemTitle: (__VLS_ctx.itemTitle),
            itemValue: (__VLS_ctx.itemValue),
            label: (__VLS_ctx.label),
            multiple: (__VLS_ctx.multiple),
            chips: (__VLS_ctx.multiple),
            closableChips: (__VLS_ctx.multiple),
            disabled: (__VLS_ctx.disabled),
            clearable: (__VLS_ctx.clearable),
            density: (__VLS_ctx.density),
            variant: (__VLS_ctx.variant),
            hideDetails: (__VLS_ctx.hideDetails),
            hint: (__VLS_ctx.hint),
            persistentHint: (!!__VLS_ctx.hint),
        }, ...__VLS_functionalComponentArgsRest(__VLS_93));
        let __VLS_97;
        const __VLS_98 = {
            /** @type {typeof __VLS_97.'update:modelValue'} */
            'onUpdate:modelValue': (onSelect),
        };
        void __VLS_98;
        var __VLS_95;
        var __VLS_96;
    }
    // @ts-ignore
    [label, variant, density, hideDetails, disabled, hint, hint, clearable, multiple, multiple, multiple, searchable, modelValue, items, itemTitle, itemValue,];
    return {};
};
void [__VLS_template];
const __VLS_export = (await import('vue')).defineComponent({
    __typeEmits: {},
    __defaults: __VLS_defaults,
    __typeProps: {},
});
export default {};
