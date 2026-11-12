import { usePositionStore } from '@/stores/positionStore';
import PositionsTable from '@/components/PositionsTable.vue';
const { defineExpose, } = {};
const positionStore = usePositionStore();
const __VLS_exposed = {
    refresh: () => positionStore.fetchPositions(),
};
defineExpose(__VLS_exposed);
const __VLS_ctx = {};
let __VLS_components;
let __VLS_intrinsics;
let __VLS_directives;
void __VLS_ctx, __VLS_components, __VLS_intrinsics, __VLS_directives;
const __VLS_template = () => {
    __VLS_withDotValue(positionStore, {});
    let __VLS_0;
    /** @ts-ignore @type { | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row'] | typeof __VLS_components.vRow | typeof __VLS_components.VRow | typeof __VLS_components['v-row']} */
    vRow;
    // @ts-ignore
    const __VLS_1 = __VLS_asFunctionalComponent1(__VLS_0, new __VLS_0({
    // @ts-ignore
    }));
    const __VLS_2 = __VLS_1({}, ...__VLS_functionalComponentArgsRest(__VLS_1));
    var __VLS_3;
    const { default: __VLS_5 } = __VLS_nonNull(__VLS_3.slots);
    let __VLS_6;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_7 = __VLS_asFunctionalComponent1(__VLS_6, new __VLS_6({
        // @ts-ignore
        cols: "12",
    }));
    const __VLS_8 = __VLS_7({
        cols: "12",
    }, ...__VLS_functionalComponentArgsRest(__VLS_7));
    var __VLS_9;
    const { default: __VLS_11 } = __VLS_nonNull(__VLS_9.slots);
    const __VLS_12 = PositionsTable;
    // @ts-ignore
    const __VLS_13 = __VLS_asFunctionalComponent1(__VLS_12, new __VLS_12({
        // @ts-ignore
        ...{ 'onRefresh': {} }, title: "▲ 多头仓位", side: "long", positions: (positionStore.value.longPositions), loading: (positionStore.value.loading),
    }));
    const __VLS_14 = __VLS_13({
        ...{ 'onRefresh': {} },
        title: "▲ 多头仓位",
        side: "long",
        positions: (positionStore.value.longPositions),
        loading: (positionStore.value.loading),
    }, ...__VLS_functionalComponentArgsRest(__VLS_13));
    let __VLS_17;
    const __VLS_18 = {
        /** @type {typeof __VLS_17.refresh} */
        onRefresh: (...[$event]) => {
            void $event;
            return (positionStore.value.fetchPositions());
            // @ts-ignore
            [positionStore, positionStore, positionStore,];
        },
    };
    void __VLS_18;
    var __VLS_15;
    var __VLS_16;
    // @ts-ignore
    [];
    let __VLS_19;
    /** @ts-ignore @type { | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col'] | typeof __VLS_components.vCol | typeof __VLS_components.VCol | typeof __VLS_components['v-col']} */
    vCol;
    // @ts-ignore
    const __VLS_20 = __VLS_asFunctionalComponent1(__VLS_19, new __VLS_19({
        // @ts-ignore
        cols: "12",
    }));
    const __VLS_21 = __VLS_20({
        cols: "12",
    }, ...__VLS_functionalComponentArgsRest(__VLS_20));
    var __VLS_22;
    const { default: __VLS_24 } = __VLS_nonNull(__VLS_22.slots);
    const __VLS_25 = PositionsTable;
    // @ts-ignore
    const __VLS_26 = __VLS_asFunctionalComponent1(__VLS_25, new __VLS_25({
        // @ts-ignore
        ...{ 'onRefresh': {} }, title: "▼ 空头仓位", side: "short", positions: (positionStore.value.shortPositions), loading: (positionStore.value.loading),
    }));
    const __VLS_27 = __VLS_26({
        ...{ 'onRefresh': {} },
        title: "▼ 空头仓位",
        side: "short",
        positions: (positionStore.value.shortPositions),
        loading: (positionStore.value.loading),
    }, ...__VLS_functionalComponentArgsRest(__VLS_26));
    let __VLS_30;
    const __VLS_31 = {
        /** @type {typeof __VLS_30.refresh} */
        onRefresh: (...[$event]) => {
            void $event;
            return (positionStore.value.fetchPositions());
            // @ts-ignore
            [positionStore, positionStore, positionStore,];
        },
    };
    void __VLS_31;
    var __VLS_28;
    var __VLS_29;
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
    setup: () => __VLS_exposed,
});
export default {};
