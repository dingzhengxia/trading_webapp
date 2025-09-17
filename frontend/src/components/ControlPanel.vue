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
                    multiple chips closable-chips clearable
                    variant="outlined" hide-details
                    :menu-props="{ maxHeight: '300px' }"
                  ></v-autocomplete>

                  <v-divider class="my-4"></v-divider>

                  <v-autocomplete
                    v-model="settingsStore.selectedLongCoins"
                    :items="settingsStore.availableLongCoins"
                    label="交易终端 - 实时做多币种"
                    multiple chips closable-chips clearable
                    variant="outlined" hide-details
                    :menu-props="{ maxHeight: '300px' }"
                  ></v-autocomplete>
                </v-card-text>
              </v-card>
            </v-col>

            <v-col cols="12" md="6">
              <v-card variant="outlined" class="d-flex flex-column" style="height: 100%;">
                <v-card-title>空头设置</v-card-title>
                <v-card-text class="flex-grow-1">
                  <v-switch v-model="settingsStore.settings.enable_short_trades" label="开启空头交易" color="success" inset></v-switch>
                  <v-text-field v-model.number="settingsStore.settings.total_short_position_value" label="空头总价值 (USD)" type="number" :disabled="!settingsStore.settings.enable_short_trades"></v-text-field>

                  <v-autocomplete
                    v-model="settingsStore.settings.short_coin_list"
                    :items="settingsStore.availableShortCoins"
                    label="从备选池中选择做空币种"
                    multiple chips closable-chips clearable
                    variant="outlined" hide-details
                    :menu-props="{ maxHeight: '300px' }"
                  ></v-autocomplete>

                  <v-divider class="my-4"></v-divider>

                  <v-autocomplete
                    v-model="settingsStore.selectedShortCoins"
                    :items="settingsStore.availableShortCoins"
                    label="交易终端 - 实时做空币种"
                    multiple chips closable-chips clearable
                    variant="outlined" hide-details
                    :menu-props="{ maxHeight: '300px' }"
                  ></v-autocomplete>
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>
        </v-window-item>
        <v-window-item value="rebalance">
          <v-row>
            <v-col cols="12" md="6">
              <v-card variant="outlined" class="d-flex flex-column" style="height: 100%;">
                <v-card-title>再平衡设置</v-card-title>
                <v-card-text class="flex-grow-1">
                  <v-select
                    v-model="settingsStore.settings.rebalance_method"
                    :items="rebalanceMethods"
                    label="再平衡方法"
                    item-title="title"
                    item-value="value"
                    variant="outlined"
                  ></v-select>
                  <v-text-field v-model.number="settingsStore.settings.rebalance_top_n" label="Top N 币种" type="number"></v-text-field>
                  <v-text-field v-model.number="settingsStore.settings.rebalance_min_volume_usd" label="最小交易量 (USD)" type="number"></v-text-field>
                  <div v-if="settingsStore.settings.rebalance_method === 'multi_factor' || settingsStore.settings.rebalance_method === 'multi_factor_weakness'"><v-text-field v-model.number="settingsStore.settings.rebalance_abs_momentum_days" label="绝对动量天数" type="number"></v-text-field><v-text-field v-model.number="settingsStore.settings.rebalance_rel_strength_days" label="相对强度天数 (vs BTC)" type="number"></v-text-field></div>
                  <div v-if="settingsStore.settings.rebalance_method === 'foam'"><v-text-field v-model.number="settingsStore.settings.rebalance_foam_days" label="FOAM动量天数" type="number"></v-text-field></div>
                </v-card-text>
              </v-card>
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
import { useSettingsStore } from '@/stores/settingsStore';
import { useUiStore } from '@/stores/uiStore';
import WeightConfigDialog from './WeightConfigDialog.vue';

const modelValue = defineModel<string>();

const settingsStore = useSettingsStore();
const uiStore = useUiStore();

const rebalanceMethods = [
  { value: 'multi_factor_weakness', title: '多因子-弱势' },
  { value: 'multi_factor', title: '多因子-强势' },
  { value: 'reversal', title: '反转' },
  { value: 'momentum', title: '动量' },
  { value: 'foam', title: 'FOAM' }
];

const updateWeights = (newWeights: { [key: string]: number }) => {
  if (settingsStore.settings) {
    settingsStore.settings.long_custom_weights = newWeights;
    settingsStore.saveGeneralSettings(settingsStore.settings);
  }
};
</script>
