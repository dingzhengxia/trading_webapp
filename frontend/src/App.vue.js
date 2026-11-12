import { onMounted, ref, watch, computed } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useDisplay, useTheme } from 'vuetify';
import { useUiStore } from '@/stores/uiStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { useAuthStore } from '@/stores/authStore';
import websocketService from '@/services/websocket';
// 导入所有全局组件
import LogDrawer from '@/components/LogDrawer.vue';
import RebalanceDialog from '@/components/RebalanceDialog.vue';
import CloseDialog from '@/components/CloseDialog.vue';
import WeightConfigDialog from '@/components/WeightConfigDialog.vue';
import ProgressBar from '@/components/ProgressBar.vue';
import AccessKeyDialog from '@/components/AccessKeyDialog.vue';
import AppSnackbar from '@/components/AppSnackbar.vue';
const router = useRouter();
const routes = router.getRoutes().filter((r) => r.meta && r.meta.title && r.meta.icon);
// 初始化所有需要的 store
const uiStore = useUiStore();
const settingsStore = useSettingsStore();
const authStore = useAuthStore();
// Vuetify 响应式和主题相关的 hooks
const { mdAndUp } = useDisplay();
const theme = useTheme();
// 根据当前主题动态计算图标
const themeIcon = computed(() => uiStore.theme === 'dark' ? 'mdi-weather-sunny' : 'mdi-weather-night');
const drawer = ref(mdAndUp.value);
// 手机端：路由变化后自动收起抽屉，避免抽屉盖住页面让用户误以为点击无效
const currentRoute = useRoute();
watch(() => currentRoute.path, () => {
    if (!mdAndUp.value)
        drawer.value = false;
});
// 应用初始化函数
const initializeApp = async () => {
    // 只有在认证通过后才执行初始化
    if (authStore.isAuthenticated) {
        try {
            await settingsStore.fetchSettings();
            await uiStore.checkInitialStatus();
            websocketService.connect();
        }
        catch (error) {
            console.error('应用初始化失败:', error);
            if (!String(error).includes('403')) {
                uiStore.setStatus('应用初始化失败', false);
            }
        }
    }
};
// 组件挂载时尝试初始化
onMounted(() => {
    initializeApp();
});
// 监听认证状态的变化
// 当用户输入密钥后，isAuthenticated会变为true，从而触发初始化
watch(() => authStore.isAuthenticated, (isAuth) => {
    if (isAuth) {
        initializeApp();
    }
});
const __VLS_ctx = {};
let __VLS_components;
let __VLS_intrinsics;
let __VLS_directives;
void __VLS_ctx, __VLS_components, __VLS_intrinsics, __VLS_directives;
const __VLS_template = () => {
    __VLS_withDotValue(uiStore, {});
    __VLS_withDotValue(drawer, {});
    let __VLS_0;
    /** @ts-ignore @type { | typeof __VLS_components.vApp | typeof __VLS_components.VApp | typeof __VLS_components['v-app'] | typeof __VLS_components.vApp | typeof __VLS_components.VApp | typeof __VLS_components['v-app']} */
    vApp;
    // @ts-ignore
    const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
    // @ts-ignore
    }));
    const __VLS_2 = __VLS_1({}, ...__VLS_functionalComponentArgsRest(__VLS_1));
    var __VLS_3;
    const { default: __VLS_5 } = __VLS_nonNull(__VLS_3.slots);
    let __VLS_6;
    /** @ts-ignore @type { | typeof __VLS_components.vAppBar | typeof __VLS_components.VAppBar | typeof __VLS_components['v-app-bar'] | typeof __VLS_components.vAppBar | typeof __VLS_components.VAppBar | typeof __VLS_components['v-app-bar']} */
    vAppBar;
    // @ts-ignore
    const __VLS_7 = __VLS_asFunctionalComponent1(__VLS_6, new __VLS_6({
        // @ts-ignore
        app: true, density: "compact",
    }));
    const __VLS_8 = __VLS_7({
        app: true,
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
    }));
    const __VLS_14 = __VLS_13({}, ...__VLS_functionalComponentArgsRest(__VLS_13));
    var __VLS_15;
    const { default: __VLS_17 } = __VLS_nonNull(__VLS_15.slots);
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
        color: (uiStore.value.statusColor), ...{ class: "mr-2" }, label: true,
    }));
    const __VLS_25 = __VLS_24({
        color: (uiStore.value.statusColor),
        ...{ class: "mr-2" },
        label: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_24));
    /** @type {__VLS_StyleScopedClasses['mr-2']} */ ;
    var __VLS_26;
    const { default: __VLS_28 } = __VLS_nonNull(__VLS_26.slots);
    (uiStore.value.statusMessage);
    // @ts-ignore
    [uiStore, uiStore,];
    let __VLS_29;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_30 = __VLS_asFunctionalComponent1(__VLS_29, new __VLS_29({
        // @ts-ignore
        ...{ 'onClick': {} }, icon: true, ...{ class: "d-md-none" },
    }));
    const __VLS_31 = __VLS_30({
        ...{ 'onClick': {} },
        icon: true,
        ...{ class: "d-md-none" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_30));
    let __VLS_34;
    const __VLS_35 = {
        /** @type {typeof __VLS_34.click} */
        onClick: (...[$event]) => {
            void $event;
            return (drawer.value = !drawer.value);
            // @ts-ignore
            [drawer, drawer,];
        },
    };
    void __VLS_35;
    /** @type {__VLS_StyleScopedClasses['d-md-none']} */ ;
    var __VLS_32;
    var __VLS_33;
    const { default: __VLS_36 } = __VLS_nonNull(__VLS_32.slots);
    let __VLS_37;
    /** @ts-ignore @type { | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon'] | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon']} */
    vIcon;
    // @ts-ignore
    const __VLS_38 = __VLS_asFunctionalComponent1(__VLS_37, new __VLS_37({
    // @ts-ignore
    }));
    const __VLS_39 = __VLS_38({}, ...__VLS_functionalComponentArgsRest(__VLS_38));
    var __VLS_40;
    const { default: __VLS_42 } = __VLS_nonNull(__VLS_40.slots);
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    let __VLS_43;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_44 = __VLS_asFunctionalComponent1(__VLS_43, new __VLS_43({
        // @ts-ignore
        ...{ 'onClick': {} }, icon: true, title: (`切换到${uiStore.value.theme === 'dark' ? '浅色' : '深色'}模式`),
    }));
    const __VLS_45 = __VLS_44({
        ...{ 'onClick': {} },
        icon: true,
        title: (`切换到${uiStore.value.theme === 'dark' ? '浅色' : '深色'}模式`),
    }, ...__VLS_functionalComponentArgsRest(__VLS_44));
    let __VLS_48;
    const __VLS_49 = {
        /** @type {typeof __VLS_48.click} */
        onClick: (...[$event]) => {
            void $event;
            return (uiStore.value.toggleTheme(__VLS_unwrap(theme, {})));
            // @ts-ignore
            [uiStore, uiStore, theme,];
        },
    };
    void __VLS_49;
    var __VLS_46;
    var __VLS_47;
    const { default: __VLS_50 } = __VLS_nonNull(__VLS_46.slots);
    let __VLS_51;
    /** @ts-ignore @type { | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon'] | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon']} */
    vIcon;
    // @ts-ignore
    const __VLS_52 = __VLS_asFunctionalComponent1(__VLS_51, new __VLS_51({
    // @ts-ignore
    }));
    const __VLS_53 = __VLS_52({}, ...__VLS_functionalComponentArgsRest(__VLS_52));
    var __VLS_54;
    const { default: __VLS_56 } = __VLS_nonNull(__VLS_54.slots);
    (__VLS_unwrap(themeIcon, {}));
    // @ts-ignore
    [themeIcon,];
    // @ts-ignore
    [];
    let __VLS_57;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_58 = __VLS_asFunctionalComponent1(__VLS_57, new __VLS_57({
        // @ts-ignore
        ...{ 'onClick': {} }, icon: true,
    }));
    const __VLS_59 = __VLS_58({
        ...{ 'onClick': {} },
        icon: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_58));
    let __VLS_62;
    const __VLS_63 = {
        /** @type {typeof __VLS_62.click} */
        onClick: (...[$event]) => {
            void $event;
            return (uiStore.value.toggleLogDrawer());
            // @ts-ignore
            [uiStore,];
        },
    };
    void __VLS_63;
    var __VLS_60;
    var __VLS_61;
    const { default: __VLS_64 } = __VLS_nonNull(__VLS_60.slots);
    let __VLS_65;
    /** @ts-ignore @type { | typeof __VLS_components.vBadge | typeof __VLS_components.VBadge | typeof __VLS_components['v-badge'] | typeof __VLS_components.vBadge | typeof __VLS_components.VBadge | typeof __VLS_components['v-badge']} */
    vBadge;
    // @ts-ignore
    const __VLS_66 = __VLS_asFunctionalComponent1(__VLS_65, new __VLS_65({
        // @ts-ignore
        content: (uiStore.value.logStore.logs.length), color: "error", modelValue: (uiStore.value.logStore.logs.length > 0),
    }));
    const __VLS_67 = __VLS_66({
        content: (uiStore.value.logStore.logs.length),
        color: "error",
        modelValue: (uiStore.value.logStore.logs.length > 0),
    }, ...__VLS_functionalComponentArgsRest(__VLS_66));
    var __VLS_68;
    const { default: __VLS_70 } = __VLS_nonNull(__VLS_68.slots);
    let __VLS_71;
    /** @ts-ignore @type { | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon'] | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon']} */
    vIcon;
    // @ts-ignore
    const __VLS_72 = __VLS_asFunctionalComponent1(__VLS_71, new __VLS_71({
    // @ts-ignore
    }));
    const __VLS_73 = __VLS_72({}, ...__VLS_functionalComponentArgsRest(__VLS_72));
    var __VLS_74;
    const { default: __VLS_76 } = __VLS_nonNull(__VLS_74.slots);
    // @ts-ignore
    [uiStore, uiStore,];
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    let __VLS_77;
    /** @ts-ignore @type { | typeof __VLS_components.vNavigationDrawer | typeof __VLS_components.VNavigationDrawer | typeof __VLS_components['v-navigation-drawer'] | typeof __VLS_components.vNavigationDrawer | typeof __VLS_components.VNavigationDrawer | typeof __VLS_components['v-navigation-drawer']} */
    vNavigationDrawer;
    // @ts-ignore
    const __VLS_78 = __VLS_asFunctionalComponent1(__VLS_77, new __VLS_77({
        // @ts-ignore
        modelValue: (drawer.value), permanent: (__VLS_ctx.$vuetify.display.mdAndUp), app: true,
    }));
    const __VLS_79 = __VLS_78({
        modelValue: (drawer.value),
        permanent: (__VLS_ctx.$vuetify.display.mdAndUp),
        app: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_78));
    var __VLS_80;
    const { default: __VLS_82 } = __VLS_nonNull(__VLS_80.slots);
    let __VLS_83;
    /** @ts-ignore @type { | typeof __VLS_components.vList | typeof __VLS_components.VList | typeof __VLS_components['v-list'] | typeof __VLS_components.vList | typeof __VLS_components.VList | typeof __VLS_components['v-list']} */
    vList;
    // @ts-ignore
    const __VLS_84 = __VLS_asFunctionalComponent1(__VLS_83, new __VLS_83({
        // @ts-ignore
        nav: true,
    }));
    const __VLS_85 = __VLS_84({
        nav: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_84));
    var __VLS_86;
    const { default: __VLS_88 } = __VLS_nonNull(__VLS_86.slots);
    const __VLS_89 = __VLS_tryAsConstant((__VLS_unwrap(routes, {})));
    for (const [route] of __VLS_vFor(__VLS_nonNull(__VLS_89))) {
        let __VLS_90;
        /** @ts-ignore @type { | typeof __VLS_components.vListItem | typeof __VLS_components.VListItem | typeof __VLS_components['v-list-item'] | typeof __VLS_components.vListItem | typeof __VLS_components.VListItem | typeof __VLS_components['v-list-item']} */
        vListItem;
        // @ts-ignore
        const __VLS_91 = __VLS_asFunctionalComponent1(__VLS_90, new __VLS_90({
            // @ts-ignore
            key: (route.name?.toString()), prependIcon: (route.meta.icon), title: (route.meta.title), to: (route.path), exact: true,
        }));
        const __VLS_92 = __VLS_91({
            key: (route.name?.toString()),
            prependIcon: (route.meta.icon),
            title: (route.meta.title),
            to: (route.path),
            exact: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_91));
        // @ts-ignore
        [drawer, $vuetify, routes,];
    }
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    let __VLS_95;
    /** @ts-ignore @type { | typeof __VLS_components.vMain | typeof __VLS_components.VMain | typeof __VLS_components['v-main'] | typeof __VLS_components.vMain | typeof __VLS_components.VMain | typeof __VLS_components['v-main']} */
    vMain;
    // @ts-ignore
    const __VLS_96 = __VLS_asFunctionalComponent1(__VLS_95, new __VLS_95({
    // @ts-ignore
    }));
    const __VLS_97 = __VLS_96({}, ...__VLS_functionalComponentArgsRest(__VLS_96));
    var __VLS_98;
    const { default: __VLS_100 } = __VLS_nonNull(__VLS_98.slots);
    let __VLS_101;
    /** @ts-ignore @type { | typeof __VLS_components.vContainer | typeof __VLS_components.VContainer | typeof __VLS_components['v-container'] | typeof __VLS_components.vContainer | typeof __VLS_components.VContainer | typeof __VLS_components['v-container']} */
    vContainer;
    // @ts-ignore
    const __VLS_102 = __VLS_asFunctionalComponent1(__VLS_101, new __VLS_101({
        // @ts-ignore
        fluid: true,
    }));
    const __VLS_103 = __VLS_102({
        fluid: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_102));
    var __VLS_104;
    const { default: __VLS_106 } = __VLS_nonNull(__VLS_104.slots);
    let __VLS_107;
    /** @ts-ignore @type { | typeof __VLS_components.routerView | typeof __VLS_components.RouterView | typeof __VLS_components['router-view']} */
    routerView;
    // @ts-ignore
    const __VLS_108 = __VLS_asFunctionalComponent1(__VLS_107, new __VLS_107({
    // @ts-ignore
    }));
    const __VLS_109 = __VLS_108({}, ...__VLS_functionalComponentArgsRest(__VLS_108));
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    const __VLS_112 = LogDrawer;
    // @ts-ignore
    const __VLS_113 = __VLS_asFunctionalComponent1(__VLS_112, new __VLS_112({
        // @ts-ignore
        modelValue: (uiStore.value.showLogDrawer),
    }));
    const __VLS_114 = __VLS_113({
        modelValue: (uiStore.value.showLogDrawer),
    }, ...__VLS_functionalComponentArgsRest(__VLS_113));
    const __VLS_117 = RebalanceDialog;
    // @ts-ignore
    const __VLS_118 = __VLS_asFunctionalComponent1(__VLS_117, new __VLS_117({
    // @ts-ignore
    }));
    const __VLS_119 = __VLS_118({}, ...__VLS_functionalComponentArgsRest(__VLS_118));
    const __VLS_122 = CloseDialog;
    // @ts-ignore
    const __VLS_123 = __VLS_asFunctionalComponent1(__VLS_122, new __VLS_122({
    // @ts-ignore
    }));
    const __VLS_124 = __VLS_123({}, ...__VLS_functionalComponentArgsRest(__VLS_123));
    const __VLS_127 = WeightConfigDialog;
    // @ts-ignore
    const __VLS_128 = __VLS_asFunctionalComponent1(__VLS_127, new __VLS_127({
        // @ts-ignore
        modelValue: (uiStore.value.showWeightDialog),
    }));
    const __VLS_129 = __VLS_128({
        modelValue: (uiStore.value.showWeightDialog),
    }, ...__VLS_functionalComponentArgsRest(__VLS_128));
    const __VLS_132 = ProgressBar;
    // @ts-ignore
    const __VLS_133 = __VLS_asFunctionalComponent1(__VLS_132, new __VLS_132({
    // @ts-ignore
    }));
    const __VLS_134 = __VLS_133({}, ...__VLS_functionalComponentArgsRest(__VLS_133));
    const __VLS_137 = AccessKeyDialog;
    // @ts-ignore
    const __VLS_138 = __VLS_asFunctionalComponent1(__VLS_137, new __VLS_137({
    // @ts-ignore
    }));
    const __VLS_139 = __VLS_138({}, ...__VLS_functionalComponentArgsRest(__VLS_138));
    const __VLS_142 = AppSnackbar;
    // @ts-ignore
    const __VLS_143 = __VLS_asFunctionalComponent1(__VLS_142, new __VLS_142({
    // @ts-ignore
    }));
    const __VLS_144 = __VLS_143({}, ...__VLS_functionalComponentArgsRest(__VLS_143));
    // @ts-ignore
    [uiStore, uiStore,];
    // @ts-ignore
    [];
    return {};
};
void [__VLS_template];
const __VLS_export = (await import('vue')).defineComponent({});
export default {};
