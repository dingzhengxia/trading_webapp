<template>
  <v-card v-if="settingsStore.settings">
    <v-card-title class="text-h6">交易参数</v-card-title>
    <v-tabs :model-value="modelValue" @update:modelValue="$emit('update:modelValue', $event)" bg-color="primary">
      <v-tab value="general">通用开仓设置</v-tab>
      <v-tab value="rebalance">智能再平衡</v-tab>
    </v-tabs>
    <v-card-text>
      <v-window :model-value="modelValue">
        <v-window-item value="general">
          <v-row>
            <v-col cols="12" md="6">
              <v-card variant="outlined" class="d-flex flex-column" style="height: 100%;">
                <v-card-title>多头设置</v-card-title>
                <v-card-text class="flex-grow-1">
                  <v-switch v-model="settingsStore.settings.enable_long_trades" label="开启多头交易" color="success" inset></v-switch>
                  <v-text-field v-model.number="settingsStore.settings.total_long_position_value" label="多头总价值 (USD)" type="number" :disabled="!settingsStore.settings.enable_long_trades"></v-text-field>

                  <v-autocomplete
                    v-model="settingsStore.settings.long_coin_list"
                    :items="settingsStore.availableLongCoins"
                    label="从备选池中选择做多币种"
                    multiple
                    chips
                    closable-chips
                    :disabled="!settingsStore.settings.enable_long_trades"
                  ></v-autocomplete>

                  <v-btn size="small" @click="uiStore.showWeightDialog = true" :disabled="!settingsStore.settings.enable_long_trades">配置权重</v-btn>
                  <v-divider class="my-4"></v-divider>
                  <v-switch v-model="settingsStore.settings.enable_long_sl_tp" label="开启多头 SL/TP" color="info" inset :disabled="!settingsStore.settings.enable_long_trades"></v-switch>
                  <v-row dense>
                    <v-col cols="6"><v-text-field v-model.number="settingsStore.settings.long_stop_loss_percentage" label="止损 (%)" type="number" :disabled="!settingsStore.settings.enable_long_sl_tp"></v-text-field></v-col>
                    <v-col cols="6"><v-text-field v-model.number="settingsStore.settings.long_take_profit_percentage" label="止盈 (%)" type="number" :disabled="!settingsStore.settings.enable_long_sl_tp"></v-text-field></v-col>
                  </v-row>
                </v-card-text>
              </v-card>
            </v-col>
            <v-col cols="12" md="6">
              <v-card variant="outlined" class="d-flex flex-column" style="height: 100%;">
                <v-card-title>空头设置</v-card-title>
                <v-card-text class="flex-grow-1">
                  <v-switch v-model="settingsStore.settings.enable_short_trades" label="开启空头交易" color="error" inset></v-switch>
                  <v-text-field v-model.number="settingsStore.settings.total_short_position_value" label="空头总价值 (USD)" type="number" :disabled="!settingsStore.settings.enable_short_trades"></v-text-field>

                  <v-autocomplete
                    v-model="settingsStore.settings.short_coin_list"
                    :items="settingsStore.availableShortCoins"
                    label="从备选池中选择空头币种"
                    multiple
                    chips
                    closable-chips
                    :disabled="!settingsStore.settings.enable_short_trades"
                  ></v-autocomplete>

                  <v-divider class="my-4"></v-divider>
                   <v-switch v-model="settingsStore.settings.enable_short_sl_tp" label="开启空头 SL/TP" color="info" inset :disabled="!settingsStore.settings.enable_short_trades"></v-switch>
                  <v-row dense>
                    <v-col cols="6"><v-text-field v-model.number="settingsStore.settings.short_stop_loss_percentage" label="止损 (%)" type="number" :disabled="!settingsStore.settings.enable_short_sl_tp"></v-text-field></v-col>
                    <v-col cols="6"><v-text-field v-model.number="settingsStore.settings.short_take_profit_percentage" label="止盈 (%)" type="number" :disabled="!settingsStore.settings.enable_short_sl_tp"></v-text-field></v-col>
                  </v-row>
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>
        </v-window-item>

        <v-window-item value="rebalance">
          <p class="mb-4">根据市场指标动态筛选弱势币种，并生成调整空头仓位的交易计划。</p>
          <v-row>
            <v-col cols="12" md="6">
              <v-select v-model="settingsStore.settings.rebalance_method" :items="rebalanceMethods" item-title="text" item-value="value" label="筛选策略"></v-select>
              <v-text-field v-model.number="settingsStore.settings.rebalance_top_n" label="目标币种数量 (Top N)" type="number"></v-text-field>
              <v-text-field v-model.number="settingsStore.settings.rebalance_min_volume_usd" label="最小24h交易额 (USD)" type="number"></v-text-field>
            </v-col>
            <v-col cols="12" md="6">
              <div v-if="settingsStore.settings.rebalance_method === 'multi_factor_weakest'"><v-text-field v-model.number="settingsStore.settings.rebalance_abs_momentum_days" label="绝对动量天数" type="number"></v-text-field><v-text-field v-model.number="settingsStore.settings.rebalance_rel_strength_days" label="相对强度天数 (vs BTC)" type="number"></v-text-field></div>
              <div v-if="settingsStore.settings.rebalance_method === 'foam'"><v-text-field v-model.number="settingsStore.settings.rebalance_foam_days" label="FOAM动量天数" type="number"></v-text-field></div>
            </v-col>
          </v-row>
        </v-window-item>
      </v-window>
    </v-card-text>
  </v-card>
  <v-skeleton-loader v-else type="card, article"></v-skeleton-loader>
  <WeightConfigDialog v-if="settingsStore.settings" v-model="uiStore.showWeightDialog" :coins="settingsStore.settings.long_coin_list" :weights="settingsStore.settings.long_custom_weights || {}" @save="updateWeights" />
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUiStore } from '@/stores/uiStore';
import WeightConfigDialog from './WeightConfigDialog.vue';
import { debounce } from 'lodash-es';

const modelValue = defineModel<string>();

const settingsStore = useSettingsStore();
const uiStore = useUiStore();

const rebalanceMethods = [
  { value: 'multi_factor_weakest', text: '多因子弱势策略' },
  { value: 'foam', text: 'FOAM强势动量' }
];

const updateWeights = (newWeights: { [key: string]: number }) => {
  if (settingsStore.settings) {
    settingsStore.settings.long_custom_weights = newWeights;
  }
};

// 统一的防抖保存函数
const saveGeneralSettingsDebounced = debounce(() => {
  if (settingsStore.settings) {
    settingsStore.saveGeneralSettings(settingsStore.settings);
  }
}, 2000);

// 专门为币种列表设置的防抖保存函数
const saveSelectedListsDebounced = debounce(() => {
  if (settingsStore.settings) {
    settingsStore.saveSelectedCoinLists(settingsStore.settings.long_coin_list, settingsStore.settings.short_coin_list);
  }
}, 2000);

// 深度监听settings对象，所有通用配置的变化都会触发此监听器
watch(
  () => settingsStore.settings,
  () => {
    saveGeneralSettingsDebounced();
  },
  { deep: true, immediate: true }
);

// 专门监听币种列表的变化
watch(
  () => [settingsStore.settings?.long_coin_list, settingsStore.settings?.short_coin_list],
  () => {
    saveSelectedListsDebounced();
  },
  { deep: true }
);
</script>
