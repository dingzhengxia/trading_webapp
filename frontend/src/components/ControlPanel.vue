<!-- frontend/src/components/ControlPanel.vue -->
<!-- 交易参数表单：自身不再带卡片外框与 Tab 骨架，作为内容注入 ConfigDrawer 的
     general / rebalance 两个插槽（由 section prop 决定渲染哪一段）。
     内部逻辑、settingsStore 交互、保存/自动保存行为全部保留，只改变了出现的位置。 -->
<template>
  <div v-if="draft">
    <!-- 保存状态与手动保存：两个 Tab 都可见（原来在卡片标题行上） -->
    <div class="d-flex align-center flex-wrap ga-2 mb-3">
      <span v-if="lastSavedAt" class="text-caption text-medium-emphasis">
        已保存 {{ formatClockTime(lastSavedAt) }}
      </span>
      <v-spacer></v-spacer>
      <v-btn
        size="small"
        variant="tonal"
        color="success"
        :loading="saving"
        @click="persistNow(true)"
      >
        <v-icon start>mdi-content-save</v-icon>
        保存
      </v-btn>
    </div>

    <!-- ============ Tab 1：通用开仓设置 ============ -->
    <template v-if="section === 'general'">
      <v-row>
        <!-- 多头设置 -->
        <v-col cols="12" md="6">
          <v-card variant="outlined" class="d-flex flex-column" style="height: 100%">
            <v-card-title>多头设置</v-card-title>
            <v-card-text class="flex-grow-1">
              <v-switch
                v-model="draft.enable_long_trades"
                label="开启多头交易"
                color="success"
                inset
              ></v-switch>
              <v-text-field
                v-model.number="draft.total_long_position_value"
                label="多头总价值 (USD)"
                type="number"
                :disabled="!draft.enable_long_trades"
              ></v-text-field>

              <SmartSelect
                :model-value="sortedLongCoinList"
                :items="longListItems"
                label="从备选池中选择做多币种（可搜索）"
                multiple
                clearable
                searchable
                :disabled="!draft.enable_long_trades"
                @update:model-value="setLongCoinList"
              ></SmartSelect>
              <div v-if="longOutsidePool.length" class="text-caption text-warning mt-1">
                已选币种中有 {{ longOutsidePool.join('/') }} 不在做多备选池内，仍会按已选列表开仓。
              </div>

              <v-btn
                size="small"
                @click="uiStore.showWeightDialog = true"
                :disabled="!draft.enable_long_trades"
                >配置权重</v-btn
              >
              <v-divider class="my-4"></v-divider>
              <v-switch
                v-model="draft.enable_long_sl_tp"
                label="开启多头固定 SL/TP"
                color="info"
                inset
                :disabled="!draft.enable_long_trades"
              ></v-switch>
              <v-row dense>
                <v-col cols="6"
                  ><v-text-field
                    v-model.number="draft.long_stop_loss_percentage"
                    label="止损 (%)"
                    type="number"
                    :disabled="!draft.enable_long_sl_tp"
                     hint="设为0则不设置止损"
                    persistent-hint
                  ></v-text-field
                ></v-col>
                <v-col cols="6"
                  ><v-text-field
                    v-model.number="draft.long_take_profit_percentage"
                    label="止盈 (%)"
                    type="number"
                    :disabled="!draft.enable_long_sl_tp"
                    hint="设为0则不设置止盈"
                    persistent-hint
                  ></v-text-field
                ></v-col>
              </v-row>

              <!-- 新增: 多头移动止盈 -->
              <v-divider class="my-4"></v-divider>
              <v-switch
                v-model="draft.enable_long_trailing_stop"
                label="开启多头移动止盈 (Trailing)"
                color="purple-accent-2"
                inset
                :disabled="!draft.enable_long_trades"
              ></v-switch>
              <v-text-field
                v-model.number="draft.long_trailing_stop_callback_rate"
                label="回调率 (%)"
                type="number"
                step="0.1"
                min="0.1"
                max="5.0"
                :disabled="!draft.enable_long_trailing_stop"
                hint="价格回撤多少百分比时平仓 (建议 0.5% - 5.0%)"
                persistent-hint
              ></v-text-field>

            </v-card-text>
          </v-card>
        </v-col>
        <!-- 空头设置 -->
        <v-col cols="12" md="6">
          <v-card variant="outlined" class="d-flex flex-column" style="height: 100%">
            <v-card-title>空头设置</v-card-title>
            <v-card-text class="flex-grow-1">
              <v-switch
                v-model="draft.enable_short_trades"
                label="开启空头交易"
                color="error"
                inset
              ></v-switch>
              <v-text-field
                v-model.number="draft.total_short_position_value"
                label="空头总价值 (USD)"
                type="number"
                :disabled="!draft.enable_short_trades"
              ></v-text-field>

              <SmartSelect
                :model-value="sortedShortCoinList"
                :items="shortListItems"
                label="从备选池中选择空头币种（可搜索）"
                multiple
                clearable
                searchable
                :disabled="!draft.enable_short_trades"
                @update:model-value="setShortCoinList"
              ></SmartSelect>
              <div v-if="shortOutsidePool.length" class="text-caption text-warning mt-1">
                已选币种中有 {{ shortOutsidePool.join('/') }} 不在做空备选池内，仍会按已选列表开仓。
              </div>

              <v-divider class="my-4"></v-divider>
              <v-switch
                v-model="draft.enable_short_sl_tp"
                label="开启空头固定 SL/TP"
                color="info"
                inset
                :disabled="!draft.enable_short_trades"
              ></v-switch>
              <v-row dense>
                <v-col cols="6"
                  ><v-text-field
                    v-model.number="draft.short_stop_loss_percentage"
                    label="止损 (%)"
                    type="number"
                    :disabled="!draft.enable_short_sl_tp"
                    hint="设为0则不设置止损"
                    persistent-hint
                  ></v-text-field
                ></v-col>
                <v-col cols="6"
                  ><v-text-field
                    v-model.number="draft.short_take_profit_percentage"
                    label="止盈 (%)"
                    type="number"
                    :disabled="!draft.enable_short_sl_tp"
                    hint="设为0则不设置止盈"
                    persistent-hint
                  ></v-text-field
                ></v-col>
              </v-row>

              <!-- 新增: 空头移动止盈 -->
              <v-divider class="my-4"></v-divider>
              <v-switch
                v-model="draft.enable_short_trailing_stop"
                label="开启空头移动止盈 (Trailing)"
                color="purple-accent-2"
                inset
                :disabled="!draft.enable_short_trades"
              ></v-switch>
              <v-text-field
                v-model.number="draft.short_trailing_stop_callback_rate"
                label="反弹率 (%)"
                type="number"
                step="0.1"
                min="0.1"
                max="5.0"
                :disabled="!draft.enable_short_trailing_stop"
                hint="价格反弹多少百分比时平仓 (建议 0.5% - 5.0%)"
                persistent-hint
              ></v-text-field>

            </v-card-text>
          </v-card>
        </v-col>
      </v-row>

      <v-card variant="outlined" class="mt-4">
          <v-card-title>高级执行参数</v-card-title>
          <v-card-text>
              <v-row>
                  <v-col cols="12" sm="6">
                      <v-text-field
                        v-model.number="draft.leverage"
                        label="合约杠杆倍数"
                        type="number"
                        min="1"
                        max="125"
                        step="1"
                        suffix="x"
                        hint="1–125 整数；新开仓直接按此杠杆下单，已有持仓在点「校准 SL/TP」时一并推送（改杠杆会改变清算价）"
                        persistent-hint
                      ></v-text-field>
                  </v-col>
                  <v-col cols="12" sm="6">
                      <v-text-field
                        v-model.number="draft.open_maker_retries"
                        label="开仓重试次数"
                        type="number"
                        hint="挂单失败或超时后重试的次数"
                        persistent-hint
                      ></v-text-field>
                  </v-col>
                  <v-col cols="12" sm="6">
                      <v-text-field
                        v-model.number="draft.open_order_fill_timeout_seconds"
                        label="开仓订单超时 (秒)"
                        type="number"
                        hint="挂单后等待成交的最大时间"
                        persistent-hint
                      ></v-text-field>
                  </v-col>
                  <v-col cols="12" sm="6">
                      <v-text-field
                        v-model.number="draft.close_maker_retries"
                        label="平仓重试次数"
                        type="number"
                      ></v-text-field>
                  </v-col>
                  <v-col cols="12" sm="6">
                      <v-text-field
                        v-model.number="draft.close_order_fill_timeout_seconds"
                        label="平仓订单超时 (秒)"
                        type="number"
                      ></v-text-field>
                  </v-col>
              </v-row>
          </v-card-text>
      </v-card>
    </template>

    <!-- ============ Tab 2：智能再平衡 ============ -->
    <template v-else>
      <p class="mb-4">根据市场指标动态筛选弱势币种，并生成调整空头仓位的交易计划。</p>
      <v-row>
        <v-col cols="12" md="6">
          <SmartSelect
            v-model="draft.rebalance_method"
            :items="rebalanceMethods"
            item-title="text"
            item-value="value"
            label="筛选策略"
          ></SmartSelect>
          <v-text-field
            v-model.number="draft.rebalance_top_n"
            label="目标币种数量 (Top N)"
            type="number"
            variant="outlined"
            density="compact"
          ></v-text-field>
          <v-text-field
            v-model.number="draft.rebalance_min_volume_usd"
            label="最小24h交易额 (USD)"
            type="number"
            variant="outlined"
            density="compact"
          ></v-text-field>
          <v-text-field
            v-model.number="draft.rebalance_volume_ma_days"
            label="成交量均线天数 (MA)"
            type="number"
            hint="用于计算平均成交量"
            persistent-hint
            variant="outlined"
            density="compact"
          ></v-text-field>
        </v-col>
        <v-col cols="12" md="6">
          <div v-if="draft.rebalance_method === 'multi_factor_weakest'">
            <SmartSelect
              :model-value="draft.rebalance_benchmark_coin"
              :items="longListItems"
              label="相对强度基准币种"
              multiple
              searchable
              persistent-hint
              hint="用于计算相对强度"
              @update:model-value="setBenchmarkCoins"
            ></SmartSelect>
            <v-text-field
              v-model.number="draft.rebalance_abs_momentum_days"
              label="绝对动量天数"
              type="number"
              variant="outlined"
              density="compact"
            ></v-text-field>
            <v-text-field
              v-model.number="draft.rebalance_rel_strength_days"
              label="相对强度天数"
              type="number"
              variant="outlined"
              density="compact"
            ></v-text-field>
          </div>
          <v-text-field
            v-model.number="draft.rebalance_volume_spike_ratio"
            label="成交量放大过滤倍数"
            type="number"
            hint="最近成交量 > N倍均量则过滤"
            persistent-hint
            variant="outlined"
            density="compact"
          ></v-text-field>
        </v-col>
      </v-row>

      <v-card variant="outlined" class="mt-4">
        <v-card-title class="d-flex align-center">
          <span>防反弹过滤参数</span>
          <v-spacer></v-spacer>
          <v-switch
            v-model="draft.enable_rebalance_filters"
            label="启用"
            color="primary"
            hide-details
            inset
          ></v-switch>
        </v-card-title>
        <v-divider></v-divider>
        <v-card-text :class="{ 'disabled-overlay': !draft.enable_rebalance_filters }">
          <v-row>
            <v-col cols="12" sm="6" md="4">
              <div class="text-subtitle-2 mb-1">RSI超卖过滤</div>
              <v-text-field
                v-model.number="draft.rebalance_rsi_period"
                label="RSI 周期"
                type="number"
                density="compact"
              ></v-text-field>
              <v-text-field
                v-model.number="draft.rebalance_rsi_threshold"
                label="RSI 最低门槛"
                type="number"
                hint="低于此值将被剔除"
                persistent-hint
                density="compact"
              ></v-text-field>
            </v-col>
            <v-col cols="12" sm="6" md="4">
               <div class="text-subtitle-2 mb-1">短期反弹过滤</div>
              <v-text-field
                v-model.number="draft.rebalance_short_term_momentum_days"
                label="考察天数"
                type="number"
                density="compact"
              ></v-text-field>
              <v-text-field
                v-model.number="draft.rebalance_short_term_momentum_threshold"
                label="最大涨幅 (%)"
                type="number"
                hint="短期涨幅过高将剔除"
                persistent-hint
                density="compact"
              ></v-text-field>
            </v-col>
            <v-col cols="12" sm="6" md="4">
              <div class="text-subtitle-2 mb-1">波动率放大过滤</div>
               <v-text-field
                v-model.number="draft.rebalance_bollinger_period"
                label="布林带周期"
                type="number"
                density="compact"
              ></v-text-field>
               <v-text-field
                v-model.number="draft.rebalance_bollinger_std_dev"
                label="布林带标准差"
                type="number"
                density="compact"
              ></v-text-field>
              <v-text-field
                v-model.number="draft.rebalance_bollinger_width_spike_ratio"
                label="宽度放大倍数"
                type="number"
                hint="当前宽度/均值 > 此值则剔除"
                persistent-hint
                density="compact"
              ></v-text-field>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 生成再平衡计划：依赖本 Tab 的参数，从 dock 移到这里（规格 A8/A9） -->
      <v-divider class="my-4" />
      <div class="d-flex justify-end">
        <v-btn
          color="primary"
          variant="tonal"
          prepend-icon="mdi-calendar-refresh"
          :loading="isGeneratingPlan"
          :disabled="isGeneratingPlan"
          @click="emit('generate-rebalance')"
        >
          生成再平衡计划
        </v-btn>
      </div>
    </template>
  </div>
  <v-skeleton-loader v-else type="article"></v-skeleton-loader>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useSettingsStore } from '@/stores/settingsStore'
import { useUiStore } from '@/stores/uiStore'
import { useDraftSettings } from '@/composables/useDraftSettings'
import { formatClockTime } from '@/utils/format'
import SmartSelect from '@/components/SmartSelect.vue'

withDefaults(
  defineProps<{
    /** 渲染哪一段内容：general=通用开仓设置 / rebalance=智能再平衡（对应抽屉插槽） */
    section: 'general' | 'rebalance'
    isGeneratingPlan?: boolean
  }>(),
  { isGeneratingPlan: false },
)

const emit = defineEmits<{
  (e: 'generate-rebalance'): void
}>()

const settingsStore = useSettingsStore()
const uiStore = useUiStore()

// T11 草稿模式：3 个深 watch 收敛为 useDraftSettings 内部的单向数据流
// （draft 单向绑定 + diff 提交 + 防抖自动保存），组件内不再直接侦听 store。
// lastSavedAt 由 composable 的模块级单例提供（抽屉动作区读同一个值），
// commitDraft 成功时会自行写入，本组件不再自己 set。
const { draft, commitDraft, flushDraftSave, lastSavedAt } = useDraftSettings()

const MAX_VISIBLE_CHIPS = 3
const isLongListExpanded = ref(false)
const isShortListExpanded = ref(false)

// 多/空交易币种从各自备选池中选择；v-autocomplete 自带搜索过滤，无需手工过滤
// 并上「当前已选」：选中的币若不在备选池（例如从总池移除过），只给 items=备选池 时
// Vuetify 找不到对应项就渲染不出 chip，看起来像“保存丢失”，实际后端已存着。
const unionSorted = (pool: string[], selected?: string[]) =>
  [...new Set([...(pool ?? []), ...(selected ?? [])])].sort()

const longListItems = computed(() =>
  unionSorted(settingsStore.availableLongCoins, draft.value?.long_coin_list),
)
const shortListItems = computed(() =>
  unionSorted(settingsStore.availableShortCoins, draft.value?.short_coin_list),
)

// 币种列表展示永远有序（原 watch 内 in-place sort 的 computed 化）
const sortedLongCoinList = computed(() => [...(draft.value?.long_coin_list ?? [])].sort())
const sortedShortCoinList = computed(() => [...(draft.value?.short_coin_list ?? [])].sort())

const longOutsidePool = computed(() =>
  (draft.value?.long_coin_list ?? []).filter(
    (coin) => !(settingsStore.availableLongCoins ?? []).includes(coin),
  ),
)
const shortOutsidePool = computed(() =>
  (draft.value?.short_coin_list ?? []).filter(
    (coin) => !(settingsStore.availableShortCoins ?? []).includes(coin),
  ),
)

// SmartSelect 回写：草稿可能尚未灌入（hydrated 闸门），这里统一兜底
const toList = (value: string | number | (string | number)[] | null | undefined): string[] =>
  Array.isArray(value) ? value.map(String) : []

// ---- 保存状态：让“到底存没存”在界面上可见，而不是只写进日志抽屉 ----
const saving = ref(false)

const persistNow = async (force = false) => {
  if (!draft.value || saving.value) return
  saving.value = true
  // commitDraft 成功时会写入共享的 lastSavedAt，这里不再重复记时间
  await commitDraft(force)
  saving.value = false
}

// 选币等列表项立即提交（沿用原 patchSettings 即时保存行为）；
// 其余字段由 useDraftSettings 内部的防抖 diff 提交兜底。
const setLongCoinList = (value: string | number | (string | number)[] | null | undefined) => {
  if (!draft.value) return
  const list = toList(value)
  draft.value.long_coin_list = list
  if (list.length <= MAX_VISIBLE_CHIPS) isLongListExpanded.value = false
  void persistNow()
}

const setShortCoinList = (value: string | number | (string | number)[] | null | undefined) => {
  if (!draft.value) return
  const list = toList(value)
  draft.value.short_coin_list = list
  if (list.length <= MAX_VISIBLE_CHIPS) isShortListExpanded.value = false
  void persistNow()
}

const setBenchmarkCoins = (value: string | number | (string | number)[] | null | undefined) => {
  if (!draft.value) return
  const list = toList(value)
  draft.value.rebalance_benchmark_coin = list
  void persistNow()
}

const rebalanceMethods = [{ value: 'multi_factor_weakest', text: '多因子弱势策略' }]

// 离开页面时把还没落库的修改立刻提交，避免“改完就切页”丢失
onBeforeUnmount(() => {
  flushDraftSave()
})
</script>

<style scoped>
.disabled-overlay {
  opacity: 0.5;
  pointer-events: none;
}
</style>
