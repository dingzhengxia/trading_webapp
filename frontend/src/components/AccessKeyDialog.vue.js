import { ref, computed } from 'vue';
import { useAuthStore } from '@/stores/authStore';
const authStore = useAuthStore();
const inputKey = ref('');
const error = ref('');
const dialog = computed(() => !authStore.isAuthenticated);
// --- 核心修改：重写 saveKey 逻辑 ---
const saveKey = async () => {
    const key = inputKey.value.trim();
    if (!key) {
        error.value = '密钥不能为空';
        return;
    }
    const validKeyRegex = /^[\x00-\xFF]*$/;
    if (!validKeyRegex.test(key)) {
        error.value = '密钥包含无效字符 (例如中文)，请只使用英文、数字和符号。';
        return;
    }
    error.value = '';
    // 调用新的验证 action
    const success = await authStore.validateAndSetKey(key);
    // 如果验证失败，在对话框中显示错误提示
    if (!success) {
        error.value = '访问密钥验证失败，请检查后重试。';
    }
    // 如果成功，isAuthenticated 会变为 true，对话框会自动关闭
};
// --- 修改结束 ---
const __VLS_ctx = {};
let __VLS_components;
let __VLS_intrinsics;
let __VLS_directives;
void __VLS_ctx, __VLS_components, __VLS_intrinsics, __VLS_directives;
const __VLS_template = () => {
    __VLS_withDotValue(error, {});
    __VLS_withDotValue(authStore, {});
    let __VLS_0;
    /** @ts-ignore @type { | typeof __VLS_components.vDialog | typeof __VLS_components.VDialog | typeof __VLS_components['v-dialog'] | typeof __VLS_components.vDialog | typeof __VLS_components.VDialog | typeof __VLS_components['v-dialog']} */
    vDialog;
    // @ts-ignore
    const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
        // @ts-ignore
        modelValue: (__VLS_unwrap(dialog, {})), persistent: true, maxWidth: "400px",
    }));
    const __VLS_2 = __VLS_1({
        modelValue: (__VLS_unwrap(dialog, {})),
        persistent: true,
        maxWidth: "400px",
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
    [dialog,];
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
        ...{ 'onSubmit': {} },
    }));
    const __VLS_26 = __VLS_25({
        ...{ 'onSubmit': {} },
    }, ...__VLS_functionalComponentArgsRest(__VLS_25));
    let __VLS_29;
    const __VLS_30 = {
        /** @type {typeof __VLS_29.submit} */
        onSubmit: (__VLS_unwrap(saveKey, {})),
    };
    void __VLS_30;
    var __VLS_27;
    var __VLS_28;
    const { default: __VLS_31 } = __VLS_nonNull(__VLS_27.slots);
    let __VLS_32;
    /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field'] | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
    vTextField;
    // @ts-ignore
    const __VLS_33 = __VLS_asFunctionalComponent1(__VLS_32, new __VLS_32({
        // @ts-ignore
        ...{ 'onInput': {} }, modelValue: (__VLS_unwrap(inputKey, {})), label: "Access Key", required: true, autofocus: true, errorMessages: (error.value), placeholder: "只能包含英文、数字和符号",
    }));
    const __VLS_34 = __VLS_33({
        ...{ 'onInput': {} },
        modelValue: (__VLS_unwrap(inputKey, {})),
        label: "Access Key",
        required: true,
        autofocus: true,
        errorMessages: (error.value),
        placeholder: "只能包含英文、数字和符号",
    }, ...__VLS_functionalComponentArgsRest(__VLS_33));
    let __VLS_37;
    const __VLS_38 = {
        /** @type {typeof __VLS_37.input} */
        onInput: (...[$event]) => {
            void $event;
            return (error.value = '');
            // @ts-ignore
            [saveKey, inputKey, error, error,];
        },
    };
    void __VLS_38;
    var __VLS_35;
    var __VLS_36;
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    let __VLS_39;
    /** @ts-ignore @type { | typeof __VLS_components.vCardActions | typeof __VLS_components.VCardActions | typeof __VLS_components['v-card-actions'] | typeof __VLS_components.vCardActions | typeof __VLS_components.VCardActions | typeof __VLS_components['v-card-actions']} */
    vCardActions;
    // @ts-ignore
    const __VLS_40 = __VLS_asFunctionalComponent1(__VLS_39, new __VLS_39({
    // @ts-ignore
    }));
    const __VLS_41 = __VLS_40({}, ...__VLS_functionalComponentArgsRest(__VLS_40));
    var __VLS_42;
    const { default: __VLS_44 } = __VLS_nonNull(__VLS_42.slots);
    let __VLS_45;
    /** @ts-ignore @type { | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer'] | typeof __VLS_components.vSpacer | typeof __VLS_components.VSpacer | typeof __VLS_components['v-spacer']} */
    vSpacer;
    // @ts-ignore
    const __VLS_46 = __VLS_asFunctionalComponent1(__VLS_45, new __VLS_45({
    // @ts-ignore
    }));
    const __VLS_47 = __VLS_46({}, ...__VLS_functionalComponentArgsRest(__VLS_46));
    let __VLS_50;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_51 = __VLS_asFunctionalComponent1(__VLS_50, new __VLS_50({
        // @ts-ignore
        ...{ 'onClick': {} }, color: "primary", variant: "tonal", loading: (authStore.value.isLoading), disabled: (authStore.value.isLoading),
    }));
    const __VLS_52 = __VLS_51({
        ...{ 'onClick': {} },
        color: "primary",
        variant: "tonal",
        loading: (authStore.value.isLoading),
        disabled: (authStore.value.isLoading),
    }, ...__VLS_functionalComponentArgsRest(__VLS_51));
    let __VLS_55;
    const __VLS_56 = {
        /** @type {typeof __VLS_55.click} */
        onClick: (__VLS_unwrap(saveKey, {})),
    };
    void __VLS_56;
    var __VLS_53;
    var __VLS_54;
    const { default: __VLS_57 } = __VLS_nonNull(__VLS_53.slots);
    // @ts-ignore
    [saveKey, authStore, authStore,];
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
const __VLS_export = (await import('vue')).defineComponent({});
export default {};
