<!-- frontend/src/components/ControlPanel.vue -->
<!-- 交易参数表单：自身不再带卡片外框与 Tab 骨架，作为内容注入 ConfigDrawer 的
     general / rebalance 两个插槽（由 section prop 决定渲染哪一段）。
     内部逻辑、settingsStore 交互、保存/自动保存行为全部保留，只改变了出现的位置。 -->
<template>
  <div v-if="settingsStore.settings">
    <!-- 保存状态与手动保存：两个 Tab 都可见（原来在卡片标题行上） -->
    <div class="d-flex align-center flex-wrap ga-2 mb-3">
      <span v-if="lastSavedAt" class="text-caption text-medium-emphasis">
        已保存 {{ formatClock(lastSavedAt) }}
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
                v-model="settingsStore.settings.enable_long_trades"
                label="开启多头交易"
                color="success"
                inset
              ></v-switch>
              <v-text-field
                v-model.number="settingsStore.settings.total_long_position_value"
                label="多头总价值 (USD)"
                type="number"
                :disabled="!settingsStore.settings.enable_long_trades"
              ></v-text-field>

              <SmartSelect
                :model-value="settingsStore.settings.long_coin_list"
                :items="longListItems"
                label="从备选池中选择做多币种（可搜索）"
                multiple
                clearable
                searchable
                :disabled="!settingsStore.settings.enable_long_trades"
                @update:model-value="setLongCoinList"
              ></SmartSelect>
              <div v-if="longOutsidePool.length" class="text-caption text-warning mt-1">
                已选币种中有 {{ longOutsidePool.join('/') }} 不在做多备选池内，仍会按已选列表开仓。
              </div>

              <v-btn
                size="small"
                @click="uiStore.showWeightDialog = true"
                :disabled="!settingsStore.settings.enable_long_trades"
                >配置权重</v-btn
              >
              <v-divider class="my-4"></v-divider>
              <v-switch
                v-model="settingsStore.settings.enable_long_sl_tp"
                label="开启多头固定 SL/TP"
                color="info"
                inset
                :disabled="!settingsStore.settings.enable_long_trades"
              ></v-switch>
              <v-row dense>
                <v-col cols="6"
                  ><v-text-field
                    v-model.number="settingsStore.settings.long_stop_loss_percentage"
                    label="止损 (%)"
                    type="number"
                    :disabled="!settingsStore.settings.enable_long_sl_tp"
                     hint="设为0则不设置止损"
                    persistent-hint
                  ></v-text-field
                ></v-col>
                <v-col cols="6"
                  ><v-text-field
                    v-model.number="settingsStore.settings.long_take_profit_percentage"
                    label="止盈 (%)"
                    type="number"
                    :disabled="!settingsStore.settings.enable_long_sl_tp"
                    hint="设为0则不设置止盈"
                    persistent-hint
                  ></v-text-field
                ></v-col>
              </v-row>

              <!-- 新增: 多头移动止盈 -->
              <v-divider class="my-4"></v-divider>
              <v-switch
                v-model="settingsStore.settings.enable_long_trailing_stop"
                label="开启多头移动止盈 (Trailing)"
                color="purple-accent-2"
                inset
                :disabled="!settingsStore.settings.enable_long_trades"
              ></v-switch>
              <v-text-field
                v-model.number="settingsStore.settings.long_trailing_stop_callback_rate"
                label="回调率 (%)"
                type="number"
                step="0.1"
                min="0.1"
                max="5.0"
                :disabled="!settingsStore.settings.enable_long_trailing_stop"
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
                v-model="settingsStore.settings.enable_short_trades"
                label="开启空头交易"
                color="error"
                inset
              ></v-switch>
              <v-text-field
                v-model.number="settingsStore.settings.total_short_position_value"
                label="空头总价值 (USD)"
                type="number"
                :disabled="!settingsStore.settings.enable_short_trades"
              ></v-text-field>

              <SmartSelect
                :model-value="settingsStore.settings.short_coin_list"
                :items="shortListItems"
                label="从备选池中选择空头币种（可搜索）"
                multiple
                clearable
                searchable
                :disabled="!settingsStore.settings.enable_short_trades"
                @update:model-value="setShortCoinList"
              ></SmartSelect>
              <div v-if="shortOutsidePool.length" class="text-caption text-warning mt-1">
                已选币种中有 {{ shortOutsidePool.join('/') }} 不在做空备选池内，仍会按已选列表开仓。
              </div>

              <v-divider class="my-4"></v-divider>
              <v-switch
                v-model="settingsStore.settings.enable_short_sl_tp"
                label="开启空头固定 SL/TP"
                color="info"
                inset
                :disabled="!settingsStore.settings.enable_short_trades"
              ></v-switch>
              <v-row dense>
                <v-col cols="6"
                  ><v-text-field
                    v-model.number="settingsStore.settings.short_stop_loss_percentage"
                    label="止损 (%)"
                    type="number"
                    :disabled="!settingsStore.settings.enable_short_sl_tp"
                    hint="设为0则不设置止损"
                    persistent-hint
                  ></v-text-field
                ></v-col>
                <v-col cols="6"
                  ><v-text-field
                    v-model.number="settingsStore.settings.short_take_profit_percentage"
                    label="止盈 (%)"
                    type="number"
                    :disabled="!settingsStore.settings.enable_short_sl_tp"
                    hint="设为0则不设置止盈"
                    persistent-hint
                  ></v-text-field
                ></v-col>
              </v-row>

              <!-- 新增: 空头移动止盈 -->
              <v-divider class="my-4"></v-divider>
              <v-switch
                v-model="settingsStore.settings.enable_short_trailing_stop"
                label="开启空头移动止盈 (Trailing)"
                color="purple-accent-2"
                inset
                :disabled="!settingsStore.settings.enable_short_trades"
              ></v-switch>
              <v-text-field
                v-model.number="settingsStore.settings.short_trailing_stop_callback_rate"
                label="反弹率 (%)"
                type="number"
                step="0.1"
                min="0.1"
                max="5.0"
                :disabled="!settingsStore.settings.enable_short_trailing_stop"
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
                        v-model.number="settingsStore.settings.open_maker_retries"
                        label="开仓重试次数"
                        type="number"
                        hint="挂单失败或超时后重试的次数"
                        persistent-hint
                      ></v-text-field>
                  </v-col>
                  <v-col cols="12" sm="6">
                      <v-text-field
                        v-model.number="settingsStore.settings.open_order_fill_timeout_seconds"
                        label="开仓订单超时 (秒)"
                        type="number"
                        hint="挂单后等待成交的最大时间"
                        persistent-hint
                      ></v-text-field>
                  </v-col>
                  <v-col cols="12" sm="6">
                      <v-text-field
                        v-model.number="settingsStore.settings.close_maker_retries"
                        label="平仓重试次数"
                        type="number"
                      ></v-text-field>
                  </v-col>
                  <v-col cols="12" sm="6">
                      <v-text-field
                        v-model.number="settingsStore.settings.close_order_fill_timeout_seconds"
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
            v-model="settingsStore.settings.rebalance_method"
            :items="rebalanceMethods"
            item-title="text"
            item-value="value"
            label="筛选策略"
          ></SmartSelect>
          <v-text-field
            v-model.number="settingsStore.settings.rebalance_top_n"
            label="目标币种数量 (Top N)"
            type="number"
            variant="outlined"
            density="compact"
          ></v-text-field>
          <v-text-field
            v-model.number="settingsStore.settings.rebalance_min_volume_usd"
            label="最小24h交易额 (USD)"
            type="number"
            variant="outlined"
            density="compact"
          ></v-text-field>
          <v-text-field
            v-model.number="settingsStore.settings.rebalance_volume_ma_days"
            label="成交量均线天数 (MA)"
            type="number"
            hint="用于计算平均成交量"
            persistent-hint
            variant="outlined"
            density="compact"
          ></v-text-field>
        </v-col>
        <v-col cols="12" md="6">
          <div v-if="settingsStore.settings.rebalance_method === 'multi_factor_weakest'">
            <SmartSelect
              :model-value="settingsStore.settings.rebalance_benchmark_coin"
              :items="longListItems"
              label="相对强度基准币种"
              multiple
              searchable
              persistent-hint
              hint="用于计算相对强度"
              @update:model-value="setBenchmarkCoins"
            ></SmartSelect>
            <v-text-field
              v-model.number="settingsStore.settings.rebalance_abs_momentum_days"
              label="绝对动量天数"
              type="number"
              variant="outlined"
              density="compact"
            ></v-text-field>
            <v-text-field
              v-model.number="settingsStore.settings.rebalance_rel_strength_days"
              label="相对强度天数"
              type="number"
              variant="outlined"
              density="compact"
            ></v-text-field>
          </div>
          <v-text-field
            v-model.number="settingsStore.settings.rebalance_volume_spike_ratio"
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
            v-model="settingsStore.settings.enable_rebalance_filters"
            label="启用"
            color="primary"
            hide-details
            inset
          ></v-switch>
        </v-card-title>
        <v-divider></v-divider>
        <v-card-text :class="{ 'disabled-overlay': !settingsStore.settings.enable_rebalance_filters }">
          <v-row>
            <v-col cols="12" sm="6" md="4">
              <div class="text-subtitle-2 mb-1">RSI超卖过滤</div>
              <v-text-field
                v-model.number="settingsStore.settings.rebalance_rsi_period"
                label="RSI 周期"
                type="number"
                density="compact"
              ></v-text-field>
              <v-text-field
                v-model.number="settingsStore.settings.rebalance_rsi_threshold"
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
                v-model.number="settingsStore.settings.rebalance_short_term_momentum_days"
                label="考察天数"
                type="number"
                density="compact"
              ></v-text-field>
              <v-text-field
                v-model.number="settingsStore.settings.rebalance_short_term_momentum_threshold"
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
                v-model.number="settingsStore.settings.rebalance_bollinger_period"
                label="布林带周期"
                type="number"
                density="compact"
              ></v-text-field>
               <v-text-field
                v-model.number="settingsStore.settings.rebalance_bollinger_std_dev"
                label="布林带标准差"
                type="number"
                density="compact"
              ></v-text-field>
              <v-text-field
                v-model.number="settingsStore.settings.rebalance_bollinger_width_spike_ratio"
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

<script lang="ts">
// 模块级共享状态：本组件在 ConfigDrawer 的 general / rebalance 两个插槽里各挂一个实例，
// 两个实例都会深度 watch settingsStore.settings；去重守卫保证同一次修改只提交一次。
import { ref } from 'vue'

const lastSavedAt = ref<number | null>(null)
let lastSavedJson = ''
let saveInFlight = false
</script>

<script setup lang="ts">
import { watch, computed, onBeforeUnmount } from 'vue'
import { useSettingsStore } from '@/stores/settingsStore'
import { useUiStore } from '@/stores/uiStore'
import { useSnackbarStore } from '@/stores/snackbar'
import { debounce } from '@/utils/debounce'
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

const MAX_VISIBLE_CHIPS = 3
const isLongListExpanded = ref(false)
const isShortListExpanded = ref(false)

const longListShowAll = ref(false)
const shortListShowAll = ref(false)

// 多/空交易币种从各自备选池中选择；v-autocomplete 自带搜索过滤，无需手工过滤
// 并上「当前已选」：选中的币若不在备选池（例如从总池移除过），只给 items=备选池 时
// Vuetify 找不到对应项就渲染不出 chip，看起来像“保存丢失”，实际后端已存着。
const unionSorted = (pool: string[], selected?: string[]) =>
  [...new Set([...(pool ?? []), ...(selected ?? [])])].sort()

const longListItems = computed(() =>
  unionSorted(settingsStore.availableLongCoins, settingsStore.settings?.long_coin_list),
)
const shortListItems = computed(() =>
  unionSorted(settingsStore.availableShortCoins, settingsStore.settings?.short_coin_list),
)

const longOutsidePool = computed(() =>
  (settingsStore.settings?.long_coin_list ?? []).filter(
    (coin) => !(settingsStore.availableLongCoins ?? []).includes(coin),
  ),
)
const shortOutsidePool = computed(() =>
  (settingsStore.settings?.short_coin_list ?? []).filter(
    (coin) => !(settingsStore.availableShortCoins ?? []).includes(coin),
  ),
)

const removeListItemValue = (listType: 'long' | 'short', value: string) => {
  if (!settingsStore.settings) return
  const list =
    listType === 'long'
      ? settingsStore.settings.long_coin_list
      : settingsStore.settings.short_coin_list
  const index = list.indexOf(value)
  if (index >= 0) {
    list.splice(index, 1)
  }
}

// SmartSelect 回写：settings 可能为 null（未加载完成），这里统一兜底
const toList = (value: string | number | (string | number)[] | null | undefined): string[] =>
  Array.isArray(value) ? value.map(String) : []

// 只提交被改动的那几个键：避免某个历史遗留的越界值把整包保存一起拖死
const persistPartial = async (partial: Record<string, unknown>, label: string) => {
  const result = await settingsStore.patchSettings(partial)
  if (result.ok) {
    lastSavedAt.value = Date.now()
    lastSavedJson = snapshot()
  } else {
    useSnackbarStore().show({
      message: `${label}保存失败：${result.detail}`,
      color: 'error',
      timeout: 8000,
    })
  }
}

const setLongCoinList = (value: string | number | (string | number)[] | null | undefined) => {
  if (!settingsStore.settings) return
  const list = toList(value)
  settingsStore.settings.long_coin_list = list
  persistPartial({ long_coin_list: list }, '做多币种')
}

const setShortCoinList = (value: string | number | (string | number)[] | null | undefined) => {
  if (!settingsStore.settings) return
  const list = toList(value)
  settingsStore.settings.short_coin_list = list
  persistPartial({ short_coin_list: list }, '做空币种')
}

const setBenchmarkCoins = (value: string | number | (string | number)[] | null | undefined) => {
  if (!settingsStore.settings) return
  const list = toList(value)
  settingsStore.settings.rebalance_benchmark_coin = list
  persistPartial({ rebalance_benchmark_coin: list }, '基准币种')
}

const rebalanceMethods = [{ value: 'multi_factor_weakest', text: '多因子弱势策略' }]

// ---- 保存状态：让“到底存没存”在界面上可见，而不是只写进日志抽屉 ----
// lastSavedAt / lastSavedJson / saveInFlight 为模块级共享（见文件顶部说明）
const saving = ref(false)

const snapshot = () => JSON.stringify(settingsStore.settings ?? {})
const formatClock = (ts: number) =>
  new Date(ts).toLocaleTimeString('zh-CN', { hour12: false })

const persistNow = async (force = false) => {
  if (!settingsStore.settings || saving.value) return
  const before = snapshot()
  // 自动保存路径：另一个实例正在保存同一份 settings（或内容已是已保存基线）时跳过，
  // 避免同一批修改被 general / rebalance 两个实例重复提交；手动点「保存」永远执行
  if (!force && (saveInFlight || before === lastSavedJson)) return
  saveInFlight = true
  saveSettingsDebounced.cancel()
  saving.value = true
  const result = await settingsStore.saveGeneralSettings(settingsStore.settings)
  saving.value = false
  saveInFlight = false
  if (result.ok) {
    lastSavedAt.value = Date.now()
    lastSavedJson = before
  } else {
    // 直接把服务端原因贴出来（例如“open_maker_retries 超出允许范围 [0,10]”），
    // 不要让用户为了看原因再去翻日志抽屉
    useSnackbarStore().show({
      message: `保存失败：${result.detail}`,
      color: 'error',
      timeout: 8000,
    })
  }
}

const saveSettingsDebounced = debounce(() => {
  // 与上次成功保存内容相同就不重复提交（选币已经即时保存过）
  if (settingsStore.settings && snapshot() !== lastSavedJson) persistNow()
}, 1500)

watch(
  () => settingsStore.settings,
  () => {
    if (!settingsStore.settings) return
    // 首次加载（或刷新回来的数据）不算用户修改，只记基线
    if (!lastSavedJson) {
      lastSavedJson = snapshot()
      return
    }
    saveSettingsDebounced()
  },
  { deep: true },
)

// 离开页面时把还没落库的修改立刻提交，避免“改完就切页”丢失
onBeforeUnmount(() => {
  saveSettingsDebounced.flush()
})

watch(
  () => settingsStore.settings?.long_coin_list,
  (newList) => {
    if (newList) {
      if (newList.length <= MAX_VISIBLE_CHIPS) {
        isLongListExpanded.value = false
      }
      newList.sort()
    }
  },
  { deep: true },
)

watch(
  () => settingsStore.settings?.short_coin_list,
  (newList) => {
    if (newList) {
      if (newList.length <= MAX_VISIBLE_CHIPS) {
        isShortListExpanded.value = false
      }
      newList.sort()
    }
  },
  { deep: true },
)
</script>

<style scoped>
.disabled-overlay {
  opacity: 0.5;
  pointer-events: none;
}
</style>
