import { ref, onMounted } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';
import CoinPoolsManager from '@/components/CoinPoolsManager.vue';
import AppDockFooter from '@/components/AppDockFooter.vue';
const settingsStore = useSettingsStore();
const activeTab = ref('general');
const coinPoolsManagerRef = ref(null);
// handleSave 函数本身是正确的，无需修改
const handleSave = () => {
    if (activeTab.value === 'general') {
        if (settingsStore.settings) {
            settingsStore.saveGeneralSettings(settingsStore.settings);
        }
    }
    else if (activeTab.value === 'coin_pools') {
        if (coinPoolsManagerRef.value) {
            coinPoolsManagerRef.value.savePools();
        }
    }
};
onMounted(() => {
    // 确保在进入页面时获取设置
    if (!settingsStore.settings) {
        settingsStore.fetchSettings();
    }
});
const __VLS_ctx = {};
let __VLS_components;
let __VLS_intrinsics;
let __VLS_directives;
void __VLS_ctx, __VLS_components, __VLS_intrinsics, __VLS_directives;
const __VLS_template = () => {
    __VLS_withDotValue(settingsStore, {});
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ style: ({ paddingBottom: __VLS_ctx.$vuetify.display.smAndDown ? '128px' : '80px' }) },
    });
    let __VLS_0;
    /** @ts-ignore @type { | typeof __VLS_components.vContainer | typeof __VLS_components.VContainer | typeof __VLS_components['v-container'] | typeof __VLS_components.vContainer | typeof __VLS_components.VContainer | typeof __VLS_components['v-container']} */
    vContainer;
    // @ts-ignore
    const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
    // @ts-ignore
    }));
    const __VLS_2 = __VLS_1({}, ...__VLS_functionalComponentArgsRest(__VLS_1));
    var __VLS_3;
    const { default: __VLS_5 } = __VLS_nonNull(__VLS_3.slots);
    let __VLS_6;
    /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
    vRow;
    // @ts-ignore
    const __VLS_7 = __VLS_asFunctionalComponent1(__VLS_6, new __VLS_6({
        // @ts-ignore
        justify: "center",
    }));
    const __VLS_8 = __VLS_7({
        justify: "center",
    }, ...__VLS_functionalComponentArgsRest(__VLS_7));
    var __VLS_9;
    const { default: __VLS_11 } = __VLS_nonNull(__VLS_9.slots);
    let __VLS_12;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_13 = __VLS_asFunctionalComponent1(__VLS_12, new __VLS_12({
        // @ts-ignore
        cols: "12", md: "10", lg: "8", xl: "6",
    }));
    const __VLS_14 = __VLS_13({
        cols: "12",
        md: "10",
        lg: "8",
        xl: "6",
    }, ...__VLS_functionalComponentArgsRest(__VLS_13));
    var __VLS_15;
    const { default: __VLS_17 } = __VLS_nonNull(__VLS_15.slots);
    if (settingsStore.value.loading) {
        let __VLS_18;
        /** @ts-ignore @type { | typeof __VLS_components.vSkeletonLoader | typeof __VLS_components.VSkeletonLoader | typeof __VLS_components['v-skeleton-loader'] | typeof __VLS_components.vSkeletonLoader | typeof __VLS_components.VSkeletonLoader | typeof __VLS_components['v-skeleton-loader']} */
        vSkeletonLoader;
        // @ts-ignore
        const __VLS_19 = __VLS_asFunctionalComponent1(__VLS_18, new __VLS_18({
            // @ts-ignore
            type: "card, article, actions",
        }));
        const __VLS_20 = __VLS_19({
            type: "card, article, actions",
        }, ...__VLS_functionalComponentArgsRest(__VLS_19));
    }
    else if (settingsStore.value.settings) {
        let __VLS_23;
        /** @ts-ignore @type { | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card'] | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card']} */
        vCard;
        // @ts-ignore
        const __VLS_24 = __VLS_asFunctionalComponent1(__VLS_23, new __VLS_23({
        // @ts-ignore
        }));
        const __VLS_25 = __VLS_24({}, ...__VLS_functionalComponentArgsRest(__VLS_24));
        var __VLS_26;
        const { default: __VLS_28 } = __VLS_nonNull(__VLS_26.slots);
        let __VLS_29;
        /** @ts-ignore @type { | typeof __VLS_components.vTabs | typeof __VLS_components.VTabs | typeof __VLS_components['v-tabs'] | typeof __VLS_components.vTabs | typeof __VLS_components.VTabs | typeof __VLS_components['v-tabs']} */
        vTabs;
        // @ts-ignore
        const __VLS_30 = __VLS_asFunctionalComponent1(__VLS_29, new __VLS_29({
            // @ts-ignore
            modelValue: (__VLS_unwrap(activeTab, {})), bgColor: "primary", grow: true,
        }));
        const __VLS_31 = __VLS_30({
            modelValue: (__VLS_unwrap(activeTab, {})),
            bgColor: "primary",
            grow: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_30));
        var __VLS_32;
        const { default: __VLS_34 } = __VLS_nonNull(__VLS_32.slots);
        let __VLS_35;
        /** @ts-ignore @type { | typeof __VLS_components.vTab | typeof __VLS_components.VTab | typeof __VLS_components['v-tab'] | typeof __VLS_components.vTab | typeof __VLS_components.VTab | typeof __VLS_components['v-tab']} */
        vTab;
        // @ts-ignore
        const __VLS_36 = __VLS_asFunctionalComponent1(__VLS_35, new __VLS_35({
            // @ts-ignore
            value: "general",
        }));
        const __VLS_37 = __VLS_36({
            value: "general",
        }, ...__VLS_functionalComponentArgsRest(__VLS_36));
        var __VLS_38;
        const { default: __VLS_40 } = __VLS_nonNull(__VLS_38.slots);
        // @ts-ignore
        [$vuetify, settingsStore, settingsStore, activeTab,];
        let __VLS_41;
        /** @ts-ignore @type { | typeof __VLS_components.vTab | typeof __VLS_components.VTab | typeof __VLS_components['v-tab'] | typeof __VLS_components.vTab | typeof __VLS_components.VTab | typeof __VLS_components['v-tab']} */
        vTab;
        // @ts-ignore
        const __VLS_42 = __VLS_asFunctionalComponent1(__VLS_41, new __VLS_41({
            // @ts-ignore
            value: "coin_pools",
        }));
        const __VLS_43 = __VLS_42({
            value: "coin_pools",
        }, ...__VLS_functionalComponentArgsRest(__VLS_42));
        var __VLS_44;
        const { default: __VLS_46 } = __VLS_nonNull(__VLS_44.slots);
        // @ts-ignore
        [];
        // @ts-ignore
        [];
        let __VLS_47;
        /** @ts-ignore @type { | typeof __VLS_components.vWindow | typeof __VLS_components.VWindow | typeof __VLS_components['v-window'] | typeof __VLS_components.vWindow | typeof __VLS_components.VWindow | typeof __VLS_components['v-window']} */
        vWindow;
        // @ts-ignore
        const __VLS_48 = __VLS_asFunctionalComponent1(__VLS_47, new __VLS_47({
            // @ts-ignore
            modelValue: (__VLS_unwrap(activeTab, {})),
        }));
        const __VLS_49 = __VLS_48({
            modelValue: (__VLS_unwrap(activeTab, {})),
        }, ...__VLS_functionalComponentArgsRest(__VLS_48));
        var __VLS_50;
        const { default: __VLS_52 } = __VLS_nonNull(__VLS_50.slots);
        let __VLS_53;
        /** @ts-ignore @type { | typeof __VLS_components.vWindowItem | typeof __VLS_components.VWindowItem | typeof __VLS_components['v-window-item'] | typeof __VLS_components.vWindowItem | typeof __VLS_components.VWindowItem | typeof __VLS_components['v-window-item']} */
        vWindowItem;
        // @ts-ignore
        const __VLS_54 = __VLS_asFunctionalComponent1(__VLS_53, new __VLS_53({
            // @ts-ignore
            value: "general",
        }));
        const __VLS_55 = __VLS_54({
            value: "general",
        }, ...__VLS_functionalComponentArgsRest(__VLS_54));
        var __VLS_56;
        const { default: __VLS_58 } = __VLS_nonNull(__VLS_56.slots);
        let __VLS_59;
        /** @ts-ignore @type { | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text'] | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text']} */
        vCardText;
        // @ts-ignore
        const __VLS_60 = __VLS_asFunctionalComponent1(__VLS_59, new __VLS_59({
        // @ts-ignore
        }));
        const __VLS_61 = __VLS_60({}, ...__VLS_functionalComponentArgsRest(__VLS_60));
        var __VLS_62;
        const { default: __VLS_64 } = __VLS_nonNull(__VLS_62.slots);
        __VLS_asFunctionalElement1(__VLS_intrinsics.h3, __VLS_intrinsics.h3)({
            ...{ class: "text-subtitle-1 font-weight-medium my-4" },
        });
        /** @type {__VLS_StyleScopedClasses['text-subtitle-1']} */ ;
        /** @type {__VLS_StyleScopedClasses['font-weight-medium']} */ ;
        /** @type {__VLS_StyleScopedClasses['my-4']} */ ;
        let __VLS_65;
        /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
        vRow;
        // @ts-ignore
        const __VLS_66 = __VLS_asFunctionalComponent1(__VLS_65, new __VLS_65({
            // @ts-ignore
            dense: true,
        }));
        const __VLS_67 = __VLS_66({
            dense: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_66));
        var __VLS_68;
        const { default: __VLS_70 } = __VLS_nonNull(__VLS_68.slots);
        let __VLS_71;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_72 = __VLS_asFunctionalComponent1(__VLS_71, new __VLS_71({
            // @ts-ignore
            cols: "12",
        }));
        const __VLS_73 = __VLS_72({
            cols: "12",
        }, ...__VLS_functionalComponentArgsRest(__VLS_72));
        var __VLS_74;
        const { default: __VLS_76 } = __VLS_nonNull(__VLS_74.slots);
        let __VLS_77;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_78 = __VLS_asFunctionalComponent1(__VLS_77, new __VLS_77({
            // @ts-ignore
            label: "API Key", modelValue: (settingsStore.value.settings.api_key), variant: "outlined", density: "compact", hideDetails: true,
        }));
        const __VLS_79 = __VLS_78({
            label: "API Key",
            modelValue: (settingsStore.value.settings.api_key),
            variant: "outlined",
            density: "compact",
            hideDetails: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_78));
        // @ts-ignore
        [settingsStore, activeTab,];
        let __VLS_82;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_83 = __VLS_asFunctionalComponent1(__VLS_82, new __VLS_82({
            // @ts-ignore
            cols: "12",
        }));
        const __VLS_84 = __VLS_83({
            cols: "12",
        }, ...__VLS_functionalComponentArgsRest(__VLS_83));
        var __VLS_85;
        const { default: __VLS_87 } = __VLS_nonNull(__VLS_85.slots);
        let __VLS_88;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_89 = __VLS_asFunctionalComponent1(__VLS_88, new __VLS_88({
            // @ts-ignore
            label: "API Secret", modelValue: (settingsStore.value.settings.api_secret), type: "password", variant: "outlined", density: "compact", hideDetails: true,
        }));
        const __VLS_90 = __VLS_89({
            label: "API Secret",
            modelValue: (settingsStore.value.settings.api_secret),
            type: "password",
            variant: "outlined",
            density: "compact",
            hideDetails: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_89));
        // @ts-ignore
        [settingsStore,];
        let __VLS_93;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_94 = __VLS_asFunctionalComponent1(__VLS_93, new __VLS_93({
            // @ts-ignore
            cols: "12",
        }));
        const __VLS_95 = __VLS_94({
            cols: "12",
        }, ...__VLS_functionalComponentArgsRest(__VLS_94));
        var __VLS_96;
        const { default: __VLS_98 } = __VLS_nonNull(__VLS_96.slots);
        let __VLS_99;
        /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
        vSwitch;
        // @ts-ignore
        const __VLS_100 = __VLS_asFunctionalComponent1(__VLS_99, new __VLS_99({
            // @ts-ignore
            label: "使用测试网", modelValue: (settingsStore.value.settings.use_testnet), color: "primary", inset: true, hideDetails: true,
        }));
        const __VLS_101 = __VLS_100({
            label: "使用测试网",
            modelValue: (settingsStore.value.settings.use_testnet),
            color: "primary",
            inset: true,
            hideDetails: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_100));
        // @ts-ignore
        [settingsStore,];
        let __VLS_104;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_105 = __VLS_asFunctionalComponent1(__VLS_104, new __VLS_104({
            // @ts-ignore
            cols: "12",
        }));
        const __VLS_106 = __VLS_105({
            cols: "12",
        }, ...__VLS_functionalComponentArgsRest(__VLS_105));
        var __VLS_107;
        const { default: __VLS_109 } = __VLS_nonNull(__VLS_107.slots);
        let __VLS_110;
        /** @ts-ignore @type { | typeof __VLS_components.vSwitch | typeof __VLS_components.VSwitch | typeof __VLS_components['v-switch']} */
        vSwitch;
        // @ts-ignore
        const __VLS_111 = __VLS_asFunctionalComponent1(__VLS_110, new __VLS_110({
            // @ts-ignore
            label: "使用代理", modelValue: (settingsStore.value.settings.enable_proxy), color: "primary", inset: true, hideDetails: true,
        }));
        const __VLS_112 = __VLS_111({
            label: "使用代理",
            modelValue: (settingsStore.value.settings.enable_proxy),
            color: "primary",
            inset: true,
            hideDetails: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_111));
        // @ts-ignore
        [settingsStore,];
        let __VLS_115;
        /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
        vCol;
        // @ts-ignore
        const __VLS_116 = __VLS_asFunctionalComponent1(__VLS_115, new __VLS_115({
            // @ts-ignore
            cols: "12",
        }));
        const __VLS_117 = __VLS_116({
            cols: "12",
        }, ...__VLS_functionalComponentArgsRest(__VLS_116));
        var __VLS_118;
        const { default: __VLS_120 } = __VLS_nonNull(__VLS_118.slots);
        let __VLS_121;
        /** @ts-ignore @type { | typeof __VLS_components.vTextField | typeof __VLS_components.VTextField | typeof __VLS_components['v-text-field']} */
        vTextField;
        // @ts-ignore
        const __VLS_122 = __VLS_asFunctionalComponent1(__VLS_121, new __VLS_121({
            // @ts-ignore
            label: "代理地址", modelValue: (settingsStore.value.settings.proxy_url), variant: "outlined", density: "compact", disabled: (!settingsStore.value.settings.enable_proxy), hideDetails: true,
        }));
        const __VLS_123 = __VLS_122({
            label: "代理地址",
            modelValue: (settingsStore.value.settings.proxy_url),
            variant: "outlined",
            density: "compact",
            disabled: (!settingsStore.value.settings.enable_proxy),
            hideDetails: true,
        }, ...__VLS_functionalComponentArgsRest(__VLS_122));
        // @ts-ignore
        [settingsStore, settingsStore,];
        // @ts-ignore
        [];
        // @ts-ignore
        [];
        // @ts-ignore
        [];
        let __VLS_126;
        /** @ts-ignore @type { | typeof __VLS_components.vWindowItem | typeof __VLS_components.VWindowItem | typeof __VLS_components['v-window-item'] | typeof __VLS_components.vWindowItem | typeof __VLS_components.VWindowItem | typeof __VLS_components['v-window-item']} */
        vWindowItem;
        // @ts-ignore
        const __VLS_127 = __VLS_asFunctionalComponent1(__VLS_126, new __VLS_126({
            // @ts-ignore
            value: "coin_pools",
        }));
        const __VLS_128 = __VLS_127({
            value: "coin_pools",
        }, ...__VLS_functionalComponentArgsRest(__VLS_127));
        var __VLS_129;
        const { default: __VLS_131 } = __VLS_nonNull(__VLS_129.slots);
        let __VLS_132;
        /** @ts-ignore @type { | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text'] | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text']} */
        vCardText;
        // @ts-ignore
        const __VLS_133 = __VLS_asFunctionalComponent1(__VLS_132, new __VLS_132({
        // @ts-ignore
        }));
        const __VLS_134 = __VLS_133({}, ...__VLS_functionalComponentArgsRest(__VLS_133));
        var __VLS_135;
        const { default: __VLS_137 } = __VLS_nonNull(__VLS_135.slots);
        const __VLS_138 = CoinPoolsManager;
        // @ts-ignore
        const __VLS_139 = __VLS_asFunctionalComponent1(__VLS_138, new __VLS_138({
            // @ts-ignore
            ref: "coinPoolsManagerRef",
        }));
        const __VLS_140 = __VLS_139({
            ref: "coinPoolsManagerRef",
        }, ...__VLS_functionalComponentArgsRest(__VLS_139));
        // @ts-ignore
        [];
        // @ts-ignore
        [];
        // @ts-ignore
        [];
        // @ts-ignore
        [];
    }
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    const __VLS_143 = AppDockFooter || AppDockFooter;
    // @ts-ignore
    const __VLS_144 = __VLS_asFunctionalComponent1(__VLS_143, new __VLS_143({
    // @ts-ignore
    }));
    const __VLS_145 = __VLS_144({}, ...__VLS_functionalComponentArgsRest(__VLS_144));
    var __VLS_146;
    const { default: __VLS_148 } = __VLS_nonNull(__VLS_146.slots);
    let __VLS_149;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_150 = __VLS_asFunctionalComponent1(__VLS_149, new __VLS_149({
        // @ts-ignore
        ...{ 'onClick': {} }, color: "success", variant: "tonal",
    }));
    const __VLS_151 = __VLS_150({
        ...{ 'onClick': {} },
        color: "success",
        variant: "tonal",
    }, ...__VLS_functionalComponentArgsRest(__VLS_150));
    let __VLS_154;
    const __VLS_155 = {
        /** @type {typeof __VLS_154.click} */
        onClick: (__VLS_unwrap(handleSave, {})),
    };
    void __VLS_155;
    var __VLS_152;
    var __VLS_153;
    const { default: __VLS_156 } = __VLS_nonNull(__VLS_152.slots);
    let __VLS_157;
    /** @ts-ignore @type { | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon'] | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon']} */
    vIcon;
    // @ts-ignore
    const __VLS_158 = __VLS_asFunctionalComponent1(__VLS_157, new __VLS_157({
        // @ts-ignore
        left: true,
    }));
    const __VLS_159 = __VLS_158({
        left: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_158));
    var __VLS_160;
    const { default: __VLS_162 } = __VLS_nonNull(__VLS_160.slots);
    // @ts-ignore
    [handleSave,];
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
