<!-- frontend/src/components/ControlPanel.vue (完整代码) -->
<template>
  <v-card v-if="settingsStore.settings">
    <v-card-title class="text-h6">交易参数</v-card-title>
    <v-tabs v-model="modelValue" bg-color="primary">
      <v-tab value="general">通用开仓设置</v-tab>
      <v-tab value="rebalance">智能再平衡</v-tab>
    </v-tabs>
    <v-card-text>
      <v-window :model-value="modelValue">
        <v-window-item value="general">
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

        </v-window-item>

        <v-window-item value="rebalance">
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
        </v-window-item>
      </v-window>
    </v-card-text>
  </v-card>
  <v-skeleton-loader v-else type="card, article"></v-skeleton-loader>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useSettingsStore } from '@/stores/settingsStore'
import { useUiStore } from '@/stores/uiStore'
import { debounce } from '@/utils/debounce'
import SmartSelect from '@/components/SmartSelect.vue'

const modelValue = defineModel<string>()

const settingsStore = useSettingsStore()
const uiStore = useUiStore()

const MAX_VISIBLE_CHIPS = 3
const isLongListExpanded = ref(false)
const isShortListExpanded = ref(false)

const longListShowAll = ref(false)
const shortListShowAll = ref(false)

// 多/空交易币种从各自备选池中选择；v-autocomplete 自带搜索过滤，无需手工过滤
const longListItems = computed(() => [...settingsStore.availableLongCoins].sort())
const shortListItems = computed(() => [...settingsStore.availableShortCoins].sort())

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

const setLongCoinList = (value: string | number | (string | number)[] | null | undefined) => {
  if (!settingsStore.settings) return
  settingsStore.settings.long_coin_list = toList(value)
}

const setShortCoinList = (value: string | number | (string | number)[] | null | undefined) => {
  if (!settingsStore.settings) return
  settingsStore.settings.short_coin_list = toList(value)
}

const setBenchmarkCoins = (value: string | number | (string | number)[] | null | undefined) => {
  if (!settingsStore.settings) return
  settingsStore.settings.rebalance_benchmark_coin = toList(value)
}

const rebalanceMethods = [{ value: 'multi_factor_weakest', text: '多因子弱势策略' }]

const saveSettingsDebounced = debounce(() => {
  if (settingsStore.settings) {
    settingsStore.saveGeneralSettings(settingsStore.settings)
  }
}, 1500)

watch(
  () => settingsStore.settings,
  () => {
    saveSettingsDebounced()
  },
  { deep: true },
)

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
