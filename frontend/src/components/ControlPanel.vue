<!-- frontend/src/components/ControlPanel.vue (最终 Vue-Multiselect 版) -->
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

                  <label class="v-label text-caption text-medium-emphasis">从备选池中选择做多币种</label>
                  <Multiselect
                    v-model="settingsStore.settings.long_coin_list"
                    :options="settingsStore.availableLongCoins"
                    mode="tags"
                    placeholder="选择或搜索币种"
                    :searchable="true"
                    :close-on-select="false"
                    :disabled="!settingsStore.settings.enable_long_trades"
                    class="mt-2 mb-4"
                  />

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

                  <label class="v-label text-caption text-medium-emphasis">从备选池中选择空头币种</label>
                  <Multiselect
                    v-model="settingsStore.settings.short_coin_list"
                    :options="settingsStore.availableShortCoins"
                    mode="tags"
                    placeholder="选择或搜索币种"
                    :searchable="true"
                    :close-on-select="false"
                    :disabled="!settingsStore.settings.enable_short_trades"
                    class="mt-2 mb-4"
                  />

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
              <v-select v-model="settingsStore.settings.rebalance_method" :items="rebalanceMethods" item-title="text" item-value="value" label="筛选策略" variant="outlined" density="compact"></v-select>
              <v-text-field v-model.number="settingsStore.settings.rebalance_top_n" label="目标币种数量 (Top N)" type="number" variant="outlined" density="compact"></v-text-field>
              <v-text-field v-model.number="settingsStore.settings.rebalance_min_volume_usd" label="最小24h交易额 (USD)" type="number" variant="outlined" density="compact"></v-text-field>
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
                <v-text-field v-model.number="settingsStore.settings.rebalance_abs_momentum_days" label="绝对动量天数" type="number" variant="outlined" density="compact"></v-text-field>
                <v-text-field v-model.number="settingsStore.settings.rebalance_rel_strength_days" label="相对强度天数 (vs BTC)" type="number" variant="outlined" density="compact"></v-text-field>
              </div>
              <div v-if="settingsStore.settings.rebalance_method === 'foam'">
                <v-text-field v-model.number="settingsStore.settings.rebalance_foam_days" label="FOAM动量天数" type="number" variant="outlined" density="compact"></v-text-field>
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
        </v-window-item>
      </v-window>
    </v-card-text>
  </v-card>
  <v-skeleton-loader v-else type="card, article"></v-skeleton-loader>
  <WeightConfigDialog v-if="settingsStore.settings" v-model="uiStore.showWeightDialog" />
</template>

<script setup lang="ts">
import { watch } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUiStore } from '@/stores/uiStore';
import WeightConfigDialog from './WeightConfigDialog.vue';
import { debounce } from 'lodash-es';
import Multiselect from 'vue-multiselect';

const modelValue = defineModel<string>();
const settingsStore = useSettingsStore();
const uiStore = useUiStore();

const rebalanceMethods = [
  { value: 'multi_factor_weakest', text: '多因子弱势策略' },
  { value: 'foam', text: 'FOAM强势动量' }
];

const saveSettingsDebounced = debounce(() => {
  if (settingsStore.settings) {
    settingsStore.saveGeneralSettings(settingsStore.settings);
  }
}, 1500);

watch(
  () => settingsStore.settings,
  () => {
    saveSettingsDebounced();
  },
  { deep: true }
);
</script>
