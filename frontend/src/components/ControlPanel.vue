<!-- frontend/src/components/ControlPanel.vue (排序和选择行为优化版) -->
<template>
  <v-card v-if="settingsStore.settings">
    <v-card-title class="text-h6">交易参数</v-card-title>
    <v-tabs
      :model-value="modelValue"
      @update:modelValue="$emit('update:modelValue', $event)"
      bg-color="primary"
    >
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

                  <v-select
                    v-model="settingsStore.settings.long_coin_list"
                    :items="filteredLongListItems"
                    label="从备选池中选择做多币种"
                    multiple
                    hide-selected <!-- 关键修改 -->
                    :close-on-content-click="false"
                    :disabled="!settingsStore.settings.enable_long_trades"
                  >
                    <template v-slot:selection="{ item, index }">
                      <div
                        v-if="index === 0"
                        class="selection-wrapper"
                        :class="{ 'is-expanded': isLongListExpanded }"
                      >
                        <v-chip
                          v-for="(coin, chipIndex) in settingsStore.settings.long_coin_list"
                          :key="`long-trade-${coin}`"
                          v-show="isLongListExpanded || chipIndex < MAX_VISIBLE_CHIPS"
                          class="ma-1"
                          closable
                          @click:close="removeListItemValue('long', coin)"
                        >
                          <span>{{ coin }}</span>
                        </v-chip>

                        <v-chip
                          v-if="
                            !isLongListExpanded &&
                            settingsStore.settings.long_coin_list.length > MAX_VISIBLE_CHIPS
                          "
                          class="ma-1"
                          @mousedown.stop="isLongListExpanded = true"
                          size="small"
                        >
                          +{{
                            settingsStore.settings.long_coin_list.length - MAX_VISIBLE_CHIPS
                          }}
                        </v-chip>

                        <v-btn
                          v-if="isLongListExpanded"
                          icon="mdi-chevron-up"
                          variant="text"
                          size="x-small"
                          @mousedown.stop="isLongListExpanded = false"
                          class="ml-1"
                        ></v-btn>
                      </div>
                    </template>

                    <template v-slot:prepend-item>
                      <v-text-field
                        v-model="longListSearch"
                        placeholder="搜索币种..."
                        variant="underlined"
                        density="compact"
                        hide-details
                        class="px-4 mb-2"
                        @click.stop
                      ></v-text-field>
                      <v-divider></v-divider>
                    </template>
                  </v-select>

                  <v-btn
                    size="small"
                    @click="uiStore.showWeightDialog = true"
                    :disabled="!settingsStore.settings.enable_long_trades"
                    >配置权重</v-btn
                  >
                  <v-divider class="my-4"></v-divider>
                  <v-switch
                    v-model="settingsStore.settings.enable_long_sl_tp"
                    label="开启多头 SL/TP"
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
                      ></v-text-field
                    ></v-col>
                    <v-col cols="6"
                      ><v-text-field
                        v-model.number="settingsStore.settings.long_take_profit_percentage"
                        label="止盈 (%)"
                        type="number"
                        :disabled="!settingsStore.settings.enable_long_sl_tp"
                      ></v-text-field
                    ></v-col>
                  </v-row>
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

                  <v-select
                    v-model="settingsStore.settings.short_coin_list"
                    :items="filteredShortListItems"
                    label="从备选池中选择空头币种"
                    multiple
                    hide-selected <!-- 关键修改 -->
                    :close-on-content-click="false"
                    :disabled="!settingsStore.settings.enable_short_trades"
                  >
                    <template v-slot:selection="{ item, index }">
                      <div
                        v-if="index === 0"
                        class="selection-wrapper"
                        :class="{ 'is-expanded': isShortListExpanded }"
                      >
                        <v-chip
                          v-for="(coin, chipIndex) in settingsStore.settings.short_coin_list"
                          :key="`short-trade-${coin}`"
                          v-show="isShortListExpanded || chipIndex < MAX_VISIBLE_CHIPS"
                          class="ma-1"
                          closable
                          @click:close="removeListItemValue('short', coin)"
                        >
                          <span>{{ coin }}</span>
                        </v-chip>

                        <v-chip
                          v-if="
                            !isShortListExpanded &&
                            settingsStore.settings.short_coin_list.length > MAX_VISIBLE_CHIPS
                          "
                          class="ma-1"
                          @mousedown.stop="isShortListExpanded = true"
                          size="small"
                        >
                          +{{
                            settingsStore.settings.short_coin_list.length - MAX_VISIBLE_CHIPS
                          }}
                        </v-chip>

                        <v-btn
                          v-if="isShortListExpanded"
                          icon="mdi-chevron-up"
                          variant="text"
                          size="x-small"
                          @mousedown.stop="isShortListExpanded = false"
                          class="ml-1"
                        ></v-btn>
                      </div>
                    </template>

                    <template v-slot:prepend-item>
                      <v-text-field
                        v-model="shortListSearch"
                        placeholder="搜索币种..."
                        variant="underlined"
                        density="compact"
                        hide-details
                        class="px-4 mb-2"
                        @click.stop
                      ></v-text-field>
                      <v-divider></v-divider>
                    </template>
                  </v-select>

                  <v-divider class="my-4"></v-divider>
                  <v-switch
                    v-model="settingsStore.settings.enable_short_sl_tp"
                    label="开启空头 SL/TP"
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
                      ></v-text-field
                    ></v-col>
                    <v-col cols="6"
                      ><v-text-field
                        v-model.number="settingsStore.settings.short_take_profit_percentage"
                        label="止盈 (%)"
                        type="number"
                        :disabled="!settingsStore.settings.enable_short_sl_tp"
                      ></v-text-field
                    ></v-col>
                  </v-row>
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>
        </v-window-item>

        <v-window-item value="rebalance">
          <!-- Rebalance settings UI remains unchanged -->
        </v-window-item>
      </v-window>
    </v-card-text>
  </v-card>
  <v-skeleton-loader v-else type="card, article"></v-skeleton-loader>
  <WeightConfigDialog v-if="settingsStore.settings" v-model="uiStore.showWeightDialog" />
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useSettingsStore } from '@/stores/settingsStore'
import { useUiStore } from '@/stores/uiStore'
import WeightConfigDialog from './WeightConfigDialog.vue'
import { debounce } from 'lodash-es'

const modelValue = defineModel<string>()

const settingsStore = useSettingsStore()
const uiStore = useUiStore()

const longListSearch = ref('')
const shortListSearch = ref('')

const MAX_VISIBLE_CHIPS = 3
const isLongListExpanded = ref(false)
const isShortListExpanded = ref(false)

// 关键修改：确保下拉列表源数据是排序的
const sortedLongListItems = computed(() => [...settingsStore.availableLongCoins].sort())
const sortedShortListItems = computed(() => [...settingsStore.availableShortCoins].sort())


const filteredLongListItems = computed(() => {
  const source = sortedLongListItems.value
  if (!longListSearch.value) return source
  return source.filter((c) =>
    c.toLowerCase().includes(longListSearch.value.toLowerCase()),
  )
})

const filteredShortListItems = computed(() => {
  const source = sortedShortListItems.value
  if (!shortListSearch.value) return source
  return source.filter((c) =>
    c.toLowerCase().includes(shortListSearch.value.toLowerCase()),
  )
})

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

const rebalanceMethods = [
  { value: 'multi_factor_weakest', text: '多因子弱势策略' },
  { value: 'foam', text: 'FOAM强势动量' },
]

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
        newList.sort() // 关键修改：确保v-model数组本身也是有序的
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
        newList.sort() // 关键修改：确保v-model数组本身也是有序的
    }
  },
  { deep: true },
)
</script>

<style scoped>
.selection-wrapper {
  display: flex;
  flex-wrap: wrap;
  width: 100%;
  align-items: center;
}

.selection-wrapper.is-expanded {
  max-height: 150px;
  overflow-y: auto;
}
</style>
