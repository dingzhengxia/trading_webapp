import { onMounted, ref, watch } from 'vue';
import apiClient from '@/services/api';
import { useUiStore } from '@/stores/uiStore';
import { getErrorMessage } from '@/utils/errors';
const uiStore = useUiStore();
const records = ref([]);
const loading = ref(false);
const openedPanel = ref(0);
const fetchHistory = async () => {
    loading.value = true;
    try {
        const response = await apiClient.get('/api/trading/open-history', { params: { limit: 50 } });
        records.value = Array.isArray(response.data?.records) ? response.data.records : [];
    }
    catch (error) {
        uiStore.logStore.addLog({
            message: `[后端] ❌ 读取开仓记录失败: ${getErrorMessage(error)}`,
            level: 'error',
            timestamp: new Date().toLocaleTimeString(),
        });
    }
    finally {
        loading.value = false;
    }
};
// 任务跑完自动刷新一次，避免手动点刷新
watch(() => uiStore.isRunning, (running, prev) => {
    if (prev && !running)
        fetchHistory();
});
onMounted(fetchHistory);
const formatTime = (ts) => {
    if (!ts)
        return '—';
    const d = new Date(ts);
    return d.toLocaleString('zh-CN', { hour12: false });
};
const formatValue = (value) => {
    const num = Number(value);
    if (!Number.isFinite(num))
        return '—';
    return `¥${num.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`;
};
const SOURCE_META = {
    plan: { label: '自动开仓', color: 'primary' },
    signal: { label: '信号开仓', color: 'teal' },
    manual: { label: '手动交易', color: 'warning' },
    rebalance: { label: '再平衡', color: 'purple' },
};
const sourceLabel = (source) => SOURCE_META[source ?? '']?.label ?? source ?? '—';
const sourceColor = (source) => SOURCE_META[source ?? '']?.color ?? 'grey';
const sideLabel = (item) => {
    const side = String(item.side || '').toLowerCase();
    if (side === 'close')
        return item.close_ratio != null ? `平仓 ${Math.round(item.close_ratio * 100)}%` : '平仓';
    if (side === 'buy')
        return '做多';
    if (side === 'sell')
        return '做空';
    return item.side || '—';
};
const sideColor = (side) => {
    // 配色约定：绿涨红跌；平仓用中性灰
    const s = String(side || '').toLowerCase();
    if (s === 'buy')
        return '#1D9E75';
    if (s === 'sell')
        return '#E24B4A';
    return '#888780';
};
const resultLabel = (item) => {
    if (item.skip_reason)
        return '跳过';
    return item.success ? '成功' : '失败';
};
const resultColor = (item) => {
    if (item.skip_reason)
        return 'grey';
    return item.success ? 'success' : 'error';
};
const itemNote = (item) => {
    const parts = [];
    if (item.strategy)
        parts.push(`策略 ${item.strategy}`);
    if (item.error)
        parts.push(item.error);
    if (item.skip_reason)
        parts.push(item.skip_reason);
    return parts.join(' · ') || '—';
};
const snapshotText = (rec) => {
    const snap = rec.snapshot;
    if (!snap || typeof snap !== 'object')
        return '';
    const parts = [];
    const longCoins = Array.isArray(snap.long_coin_list) ? snap.long_coin_list : [];
    const shortCoins = Array.isArray(snap.short_coin_list) ? snap.short_coin_list : [];
    if (snap.enable_long_trades && longCoins.length) {
        parts.push(`做多 ${longCoins.join('/')}${snap.total_long_position_value ? `（总 ${snap.total_long_position_value} USD）` : ''}`);
    }
    if (snap.enable_short_trades && shortCoins.length) {
        parts.push(`做空 ${shortCoins.join('/')}${snap.total_short_position_value ? `（总 ${snap.total_short_position_value} USD）` : ''}`);
    }
    if (rec.trigger && rec.source !== 'plan')
        parts.push(rec.trigger);
    return parts.join(' · ');
};
const __VLS_ctx = {};
let __VLS_components;
let __VLS_intrinsics;
let __VLS_directives;
void __VLS_ctx, __VLS_components, __VLS_intrinsics, __VLS_directives;
const __VLS_template = () => {
    __VLS_withDotValue(records, {});
    __VLS_withDotValue(loading, {});
    void {};
    let __VLS_0;
    /** @ts-ignore @type { | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card'] | typeof __VLS_components.vCard | typeof __VLS_components.VCard | typeof __VLS_components['v-card']} */
    vCard;
    // @ts-ignore
    const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
        // @ts-ignore
        variant: "outlined",
    }));
    const __VLS_2 = __VLS_1({
        variant: "outlined",
    }, ...__VLS_functionalComponentArgsRest(__VLS_1));
    var __VLS_3;
    const { default: __VLS_5 } = __VLS_nonNull(__VLS_3.slots);
    let __VLS_6;
    /** @ts-ignore @type { | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title'] | typeof __VLS_components.vCardTitle | typeof __VLS_components.VCardTitle | typeof __VLS_components['v-card-title']} */
    vCardTitle;
    // @ts-ignore
    const __VLS_7 = __VLS_asFunctionalComponent1(__VLS_6, new __VLS_6({
        // @ts-ignore
        ...{ class: "text-subtitle-1 d-flex align-center" },
    }));
    const __VLS_8 = __VLS_7({
        ...{ class: "text-subtitle-1 d-flex align-center" },
    }, ...__VLS_functionalComponentArgsRest(__VLS_7));
    /** @type {__VLS_StyleScopedClasses['text-subtitle-1']} */ ;
    /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
    /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
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
    if (records.value.length) {
        let __VLS_17;
        /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
        vChip;
        // @ts-ignore
        const __VLS_18 = __VLS_asFunctionalComponent1(__VLS_17, new __VLS_17({
            // @ts-ignore
            size: "small", variant: "tonal", color: "info", ...{ class: "mr-2" },
        }));
        const __VLS_19 = __VLS_18({
            size: "small",
            variant: "tonal",
            color: "info",
            ...{ class: "mr-2" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_18));
        /** @type {__VLS_StyleScopedClasses['mr-2']} */ ;
        var __VLS_20;
        const { default: __VLS_22 } = __VLS_nonNull(__VLS_20.slots);
        (records.value.length);
        // @ts-ignore
        [records, records,];
    }
    let __VLS_23;
    /** @ts-ignore @type { | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn'] | typeof __VLS_components.vBtn | typeof __VLS_components.VBtn | typeof __VLS_components['v-btn']} */
    vBtn;
    // @ts-ignore
    const __VLS_24 = __VLS_asFunctionalComponent1(__VLS_23, new __VLS_23({
        // @ts-ignore
        ...{ 'onClick': {} }, size: "small", variant: "tonal", color: "info", loading: (loading.value),
    }));
    const __VLS_25 = __VLS_24({
        ...{ 'onClick': {} },
        size: "small",
        variant: "tonal",
        color: "info",
        loading: (loading.value),
    }, ...__VLS_functionalComponentArgsRest(__VLS_24));
    let __VLS_28;
    const __VLS_29 = {
        /** @type {typeof __VLS_28.click} */
        onClick: (__VLS_unwrap(fetchHistory, {})),
    };
    void __VLS_29;
    var __VLS_26;
    var __VLS_27;
    const { default: __VLS_30 } = __VLS_nonNull(__VLS_26.slots);
    let __VLS_31;
    /** @ts-ignore @type { | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon'] | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon']} */
    vIcon;
    // @ts-ignore
    const __VLS_32 = __VLS_asFunctionalComponent1(__VLS_31, new __VLS_31({
        // @ts-ignore
        start: true,
    }));
    const __VLS_33 = __VLS_32({
        start: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_32));
    var __VLS_34;
    const { default: __VLS_36 } = __VLS_nonNull(__VLS_34.slots);
    // @ts-ignore
    [loading, fetchHistory,];
    // @ts-ignore
    [];
    // @ts-ignore
    [];
    let __VLS_37;
    /** @ts-ignore @type { | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text'] | typeof __VLS_components.vCardText | typeof __VLS_components.VCardText | typeof __VLS_components['v-card-text']} */
    vCardText;
    // @ts-ignore
    const __VLS_38 = __VLS_asFunctionalComponent1(__VLS_37, new __VLS_37({
    // @ts-ignore
    }));
    const __VLS_39 = __VLS_38({}, ...__VLS_functionalComponentArgsRest(__VLS_38));
    var __VLS_40;
    const { default: __VLS_42 } = __VLS_nonNull(__VLS_40.slots);
    if (!records.value.length && !loading.value) {
        let __VLS_43;
        /** @ts-ignore @type { | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert'] | typeof __VLS_components.vAlert | typeof __VLS_components.VAlert | typeof __VLS_components['v-alert']} */
        vAlert;
        // @ts-ignore
        const __VLS_44 = __VLS_asFunctionalComponent1(__VLS_43, new __VLS_43({
            // @ts-ignore
            type: "info", variant: "tonal", density: "compact",
        }));
        const __VLS_45 = __VLS_44({
            type: "info",
            variant: "tonal",
            density: "compact",
        }, ...__VLS_functionalComponentArgsRest(__VLS_44));
        var __VLS_46;
        const { default: __VLS_48 } = __VLS_nonNull(__VLS_46.slots);
        // @ts-ignore
        [records, loading,];
    }
    else {
        let __VLS_49;
        /** @ts-ignore @type { | typeof __VLS_components.vExpansionPanels | typeof __VLS_components.VExpansionPanels | typeof __VLS_components['v-expansion-panels'] | typeof __VLS_components.vExpansionPanels | typeof __VLS_components.VExpansionPanels | typeof __VLS_components['v-expansion-panels']} */
        vExpansionPanels;
        // @ts-ignore
        const __VLS_50 = __VLS_asFunctionalComponent1(__VLS_49, new __VLS_49({
            // @ts-ignore
            modelValue: (__VLS_unwrap(openedPanel, {})),
        }));
        const __VLS_51 = __VLS_50({
            modelValue: (__VLS_unwrap(openedPanel, {})),
        }, ...__VLS_functionalComponentArgsRest(__VLS_50));
        var __VLS_52;
        const { default: __VLS_54 } = __VLS_nonNull(__VLS_52.slots);
        const __VLS_55 = __VLS_tryAsConstant((records.value));
        for (const [rec] of __VLS_vFor(__VLS_nonNull(__VLS_55))) {
            let __VLS_56;
            /** @ts-ignore @type { | typeof __VLS_components.vExpansionPanel | typeof __VLS_components.VExpansionPanel | typeof __VLS_components['v-expansion-panel'] | typeof __VLS_components.vExpansionPanel | typeof __VLS_components.VExpansionPanel | typeof __VLS_components['v-expansion-panel']} */
            vExpansionPanel;
            // @ts-ignore
            const __VLS_57 = __VLS_asFunctionalComponent1(__VLS_56, new __VLS_56({
                // @ts-ignore
                key: (rec.id),
            }));
            const __VLS_58 = __VLS_57({
                key: (rec.id),
            }, ...__VLS_functionalComponentArgsRest(__VLS_57));
            var __VLS_59;
            const { default: __VLS_61 } = __VLS_nonNull(__VLS_59.slots);
            let __VLS_62;
            /** @ts-ignore @type { | typeof __VLS_components.vExpansionPanelTitle | typeof __VLS_components.VExpansionPanelTitle | typeof __VLS_components['v-expansion-panel-title'] | typeof __VLS_components.vExpansionPanelTitle | typeof __VLS_components.VExpansionPanelTitle | typeof __VLS_components['v-expansion-panel-title']} */
            vExpansionPanelTitle;
            // @ts-ignore
            const __VLS_63 = __VLS_asFunctionalComponent1(__VLS_62, new __VLS_62({
            // @ts-ignore
            }));
            const __VLS_64 = __VLS_63({}, ...__VLS_functionalComponentArgsRest(__VLS_63));
            var __VLS_65;
            const { default: __VLS_67 } = __VLS_nonNull(__VLS_65.slots);
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                ...{ class: "d-flex align-center ga-3" },
                ...{ style: {} },
            });
            /** @type {__VLS_StyleScopedClasses['d-flex']} */ ;
            /** @type {__VLS_StyleScopedClasses['align-center']} */ ;
            /** @type {__VLS_StyleScopedClasses['ga-3']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
                ...{ class: "text-no-wrap text-caption" },
            });
            /** @type {__VLS_StyleScopedClasses['text-no-wrap']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
            (__VLS_unwrap(formatTime, {})(rec.ts));
            let __VLS_68;
            /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
            vChip;
            // @ts-ignore
            const __VLS_69 = __VLS_asFunctionalComponent1(__VLS_68, new __VLS_68({
                // @ts-ignore
                size: "x-small", color: (__VLS_unwrap(sourceColor, {})(rec.source)), ...{ class: "text-no-wrap" },
            }));
            const __VLS_70 = __VLS_69({
                size: "x-small",
                color: (__VLS_unwrap(sourceColor, {})(rec.source)),
                ...{ class: "text-no-wrap" },
            }, ...__VLS_functionalComponentArgsRest(__VLS_69));
            /** @type {__VLS_StyleScopedClasses['text-no-wrap']} */ ;
            var __VLS_71;
            const { default: __VLS_73 } = __VLS_nonNull(__VLS_71.slots);
            (__VLS_unwrap(sourceLabel, {})(rec.source));
            // @ts-ignore
            [records, openedPanel, formatTime, sourceColor, sourceLabel,];
            let __VLS_74;
            /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
            vChip;
            // @ts-ignore
            const __VLS_75 = __VLS_asFunctionalComponent1(__VLS_74, new __VLS_74({
                // @ts-ignore
                size: "x-small", color: (rec.summary?.failed ? 'error' : 'success'), variant: "tonal", ...{ class: "text-no-wrap" },
            }));
            const __VLS_76 = __VLS_75({
                size: "x-small",
                color: (rec.summary?.failed ? 'error' : 'success'),
                variant: "tonal",
                ...{ class: "text-no-wrap" },
            }, ...__VLS_functionalComponentArgsRest(__VLS_75));
            /** @type {__VLS_StyleScopedClasses['text-no-wrap']} */ ;
            var __VLS_77;
            const { default: __VLS_79 } = __VLS_nonNull(__VLS_77.slots);
            (rec.summary?.success ?? 0);
            (rec.summary?.failed ?? 0);
            // @ts-ignore
            [];
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
                ...{ class: "text-caption text-medium-emphasis text-truncate" },
            });
            /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-medium-emphasis']} */ ;
            /** @type {__VLS_StyleScopedClasses['text-truncate']} */ ;
            (__VLS_unwrap(snapshotText, {})(rec));
            // @ts-ignore
            [snapshotText,];
            let __VLS_80;
            /** @ts-ignore @type { | typeof __VLS_components.vExpansionPanelText | typeof __VLS_components.VExpansionPanelText | typeof __VLS_components['v-expansion-panel-text'] | typeof __VLS_components.vExpansionPanelText | typeof __VLS_components.VExpansionPanelText | typeof __VLS_components['v-expansion-panel-text']} */
            vExpansionPanelText;
            // @ts-ignore
            const __VLS_81 = __VLS_asFunctionalComponent1(__VLS_80, new __VLS_80({
            // @ts-ignore
            }));
            const __VLS_82 = __VLS_81({}, ...__VLS_functionalComponentArgsRest(__VLS_81));
            var __VLS_83;
            const { default: __VLS_85 } = __VLS_nonNull(__VLS_83.slots);
            if (__VLS_unwrap(snapshotText, {})(rec)) {
                __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                    ...{ class: "text-caption mb-2 text-medium-emphasis" },
                });
                /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
                /** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
                /** @type {__VLS_StyleScopedClasses['text-medium-emphasis']} */ ;
                let __VLS_86;
                /** @ts-ignore @type { | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon'] | typeof __VLS_components.vIcon | typeof __VLS_components.VIcon | typeof __VLS_components['v-icon']} */
                vIcon;
                // @ts-ignore
                const __VLS_87 = __VLS_asFunctionalComponent1(__VLS_86, new __VLS_86({
                    // @ts-ignore
                    size: "14", ...{ class: "mr-1" },
                }));
                const __VLS_88 = __VLS_87({
                    size: "14",
                    ...{ class: "mr-1" },
                }, ...__VLS_functionalComponentArgsRest(__VLS_87));
                /** @type {__VLS_StyleScopedClasses['mr-1']} */ ;
                var __VLS_89;
                const { default: __VLS_91 } = __VLS_nonNull(__VLS_89.slots);
                // @ts-ignore
                [snapshotText,];
                (__VLS_unwrap(snapshotText, {})(rec));
            }
            let __VLS_92;
            /** @ts-ignore @type { | typeof __VLS_components.vTable | typeof __VLS_components.VTable | typeof __VLS_components['v-table'] | typeof __VLS_components.vTable | typeof __VLS_components.VTable | typeof __VLS_components['v-table']} */
            vTable;
            // @ts-ignore
            const __VLS_93 = __VLS_asFunctionalComponent1(__VLS_92, new __VLS_92({
                // @ts-ignore
                density: "compact", ...{ class: "open-history-table" },
            }));
            const __VLS_94 = __VLS_93({
                density: "compact",
                ...{ class: "open-history-table" },
            }, ...__VLS_functionalComponentArgsRest(__VLS_93));
            /** @type {__VLS_StyleScopedClasses['open-history-table']} */ ;
            var __VLS_95;
            const { default: __VLS_97 } = __VLS_nonNull(__VLS_95.slots);
            __VLS_asFunctionalElement1(__VLS_intrinsics.thead, __VLS_intrinsics.thead)({});
            __VLS_asFunctionalElement1(__VLS_intrinsics.tr, __VLS_intrinsics.tr)({});
            __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
                ...{ class: "text-left" },
            });
            /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
                ...{ class: "text-left" },
            });
            /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
                ...{ class: "text-right" },
            });
            /** @type {__VLS_StyleScopedClasses['text-right']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
                ...{ class: "text-left" },
            });
            /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.th, __VLS_intrinsics.th)({
                ...{ class: "text-left" },
            });
            /** @type {__VLS_StyleScopedClasses['text-left']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.tbody, __VLS_intrinsics.tbody)({});
            const __VLS_98 = __VLS_tryAsConstant((rec.items));
            for (const [item, idx] of __VLS_vFor(__VLS_nonNull(__VLS_98))) {
                __VLS_asFunctionalElement1(__VLS_intrinsics.tr, __VLS_intrinsics.tr)({
                    key: (idx),
                });
                __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({});
                (item.coin || '—');
                __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({});
                __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({
                    ...{ style: ({ color: __VLS_unwrap(sideColor, {})(item.side) }) },
                });
                (__VLS_unwrap(sideLabel, {})(item));
                __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                    ...{ class: "text-right" },
                });
                /** @type {__VLS_StyleScopedClasses['text-right']} */ ;
                (item.target_value != null ? __VLS_unwrap(formatValue, {})(item.target_value) : '—');
                __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({});
                let __VLS_99;
                /** @ts-ignore @type { | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip'] | typeof __VLS_components.vChip | typeof __VLS_components.VChip | typeof __VLS_components['v-chip']} */
                vChip;
                // @ts-ignore
                const __VLS_100 = __VLS_asFunctionalComponent1(__VLS_99, new __VLS_99({
                    // @ts-ignore
                    size: "x-small", variant: "tonal", color: (__VLS_unwrap(resultColor, {})(item)),
                }));
                const __VLS_101 = __VLS_100({
                    size: "x-small",
                    variant: "tonal",
                    color: (__VLS_unwrap(resultColor, {})(item)),
                }, ...__VLS_functionalComponentArgsRest(__VLS_100));
                var __VLS_102;
                const { default: __VLS_104 } = __VLS_nonNull(__VLS_102.slots);
                (__VLS_unwrap(resultLabel, {})(item));
                // @ts-ignore
                [snapshotText, sideColor, sideLabel, formatValue, resultColor, resultLabel,];
                __VLS_asFunctionalElement1(__VLS_intrinsics.td, __VLS_intrinsics.td)({
                    ...{ class: "text-caption text-medium-emphasis" },
                });
                /** @type {__VLS_StyleScopedClasses['text-caption']} */ ;
                /** @type {__VLS_StyleScopedClasses['text-medium-emphasis']} */ ;
                (__VLS_unwrap(itemNote, {})(item));
                // @ts-ignore
                [itemNote,];
            }
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
const __VLS_export = (await import('vue')).defineComponent({});
export default {};
