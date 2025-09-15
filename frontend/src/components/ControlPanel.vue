<!-- frontend/src/components/ControlPanel.vue (最终完整版) -->
<template>
  <v-card v-if="settingsStore.settings">
    <v-card-title class="text-h6">交易参数</v-card-title>

    <v-tabs v-model="tab" bg-color="primary">
      <v-tab value="general">通用开仓设置</v-tab>
      <v-tab value="rebalance">智能再平衡</v-tab>
    </v-tabs>

    <v-card-text>
      <v-window v-model="tab">
        <!-- 通用开仓设置 -->
        <v-window-item value="general">
          <v-row>
            <!-- 多头设置 -->
            <v-col cols="12" md="6">
              <v-card variant="outlined" class="d-flex flex-column" style="height: 100%;">
                <v-card-title>多头设置</v-card-title>
                <v-card-text class="flex-grow-1">
                  <v-switch v-model="settingsStore.settings.enable_long_trades" label="开启多头交易" color="success" inset></v-switch>
                  <v-text-field v-model.number="settingsStore.settings.total_long_position_value" label="多头总价值 (USD)" type="number"
                    :disabled="!settingsStore.settings.enable_long_trades"></v-text-field>
                  <v-autocomplete v-model="settingsStore.settings.long_coin_list" :items="settingsStore.availableLongCoins"
                    label="多头币种列表" multiple chips closable-chips :disabled="!settingsStore.settings.enable_long_trades">
                  </v-autocomplete>
                  <v-btn size="small" @click="uiStore.showWeightDialog = true" :disabled="!settingsStore.settings.enable_long_trades">配置权重</v-btn>

                  <!-- === 新增：多头止盈止损设置 === -->
                  <v-divider class="my-4"></v-divider>
                  <v-switch v-model="settingsStore.settings.enable_long_sl_tp" label="开启多头 SL/TP" color="info" inset :disabled="!settingsStore.settings.enable_long_trades"></v-switch>
                  <v-row dense>
                    <v-col cols="6">
                      <v-text-field v-model.number="settingsStore.settings.long_stop_loss_percentage" label="止损 (%)" type="number" :disabled="!settingsStore.settings.enable_long_sl_tp"></v-text-field>
                    </v-col>
                    <v-col cols="6">
                      <v-text-field v-model.number="settingsStore.settings.long_take_profit_percentage" label="止盈 (%)" type="number" :disabled="!settingsStore.settings.enable_long_sl_tp"></v-text-field>
                    </v-col>
                  </v-row>
                  <!-- ============================ -->

                </v-card-text>
              </v-card>
            </v-col>

            <!-- 空头设置 -->
            <v-col cols="12" md="6">
              <v-card variant="outlined" class="d-flex flex-column" style="height: 100%;">
                <v-card-title>空头设置</v-card-title>
                <v-card-text class="flex-grow-1">
                  <v-switch v-model="settingsStore.settings.enable_short_trades" label="开启空头交易" color="error" inset></v-switch>
                  <v-text-field v-model.number="settingsStore.settings.total_short_position_value" label="空头总价值 (USD)" type="number"
                    :disabled="!settingsStore.settings.enable_short_trades"></v-text-field>
                  <v-autocomplete v-model="settingsStore.settings.short_coin_list" :items="settingsStore.availableShortCoins"
                    label="空头币种列表" multiple chips closable-chips :disabled="!settingsStore.settings.enable_short_trades">
                  </v-autocomplete>

                  <!-- === 新增：空头止盈止损设置 === -->
                  <v-divider class="my-4"></v-divider>
                   <v-switch v-model="settingsStore.settings.enable_short_sl_tp" label="开启空头 SL/TP" color="info" inset :disabled="!settingsStore.settings.enable_short_trades"></v-switch>
                  <v-row dense>
                    <v-col cols="6">
                      <v-text-field v-model.number="settingsStore.settings.short_stop_loss_percentage" label="止损 (%)" type="number" :disabled="!settingsStore.settings.enable_short_sl_tp"></v-text-field>
                    </v-col>
                    <v-col cols="6">
                      <v-text-field v-model.number="settingsStore.settings.short_take_profit_percentage" label="止盈 (%)" type="number" :disabled="!settingsStore.settings.enable_short_sl_tp"></v-text-field>
                    </v-col>
                  </v-row>
                  <!-- ============================ -->

                </v-card-text>
              </v-card>
            </v-col>
          </v-row>
        </v-window-item>

        <!-- 智能再平衡 -->
        <v-window-item value="rebalance">
          <p class="mb-4">根据市场指标动态筛选弱势币种，并生成调整空头仓位的交易计划。</p>
          <v-row>
            <v-col cols="12" md="6">
              <v-select v-model="settingsStore.settings.rebalance_method" :items="['multi_factor_weakest', 'foam']" label="筛选策略">
              </v-select>
              <v-text-field v-model.number="settingsStore.settings.rebalance_top_n" label="目标币种数量 (Top N)" type="number"></v-text-field>
              <v-text-field v-model.number="settingsStore.settings.rebalance_min_volume_usd" label="最小24h交易额 (USD)"
                type="number"></v-text-field>
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model.number="settingsStore.settings.rebalance_abs_momentum_days" label="绝对动量天数" type="number"></v-text-field>
              <v-text-field v-model.number="settingsStore.settings.rebalance_rel_strength_days" label="相对强度天数 (vs BTC)"
                type="number"></v-text-field>
              <v-text-field v-model.number="settingsStore.settings.rebalance_foam_days" label="FOAM动量天数" type="number"></v-text-field>
            </v-col>
          </v-row>
        </v-window-item>
      </v-window>
    </v-card-text>

    <v-divider></v-divider>

    <v-card-actions class="pa-4">
      <v-btn color="info" @click="onSyncSlTp" :disabled="props.isRunning">校准 SL/TP</v-btn>
      <v-spacer></v-spacer>

      <template v-if="tab === 'general'">
        <v-btn
          color="success"
          prepend-icon="mdi-play"
          @click="onStartTrading"
          :loading="props.isRunning"
          :disabled="props.isRunning"
        >
          开始开仓
        </v-btn>
      </template>

      <template v-if="tab === 'rebalance'">
        <v-btn color="primary" @click="onGenerateRebalancePlan" :disabled="props.isRunning">
          生成再平衡计划
        </v-btn>
      </template>
    </v-card-actions>
  </v-card>

  <v-skeleton-loader v-else type="card, article"></v-skeleton-loader>

  <WeightConfigDialog
    v-if="settingsStore.settings"
    v-model="uiStore.showWeightDialog"
    :coins="settingsStore.settings.long_coin_list"
    :weights="settingsStore.settings.long_custom_weights || {}"
    @save="updateWeights"
  />
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUiStore } from '@/stores/uiStore';
import WeightConfigDialog from './WeightConfigDialog.vue';
import type { UserSettings } from '@/models/types';

const props = defineProps<{ isRunning: boolean }>();
const emit = defineEmits<{
  (e: 'startTrading', plan: UserSettings): void;
  (e: 'syncSltp', settings: any): void;
  (e: 'generateRebalancePlan', criteria: any): void;
}>();

const settingsStore = useSettingsStore();
const uiStore = useUiStore();
const tab = ref('general');

const onStartTrading = () => {
  if (settingsStore.settings) {
    emit('startTrading', settingsStore.settings);
  }
};

const onSyncSlTp = () => {
  if (settingsStore.settings) {
    emit('syncSltp', settingsStore.settings);
  }
};

const onGenerateRebalancePlan = () => {
  if (settingsStore.settings) {
    const criteria = {
      method: settingsStore.settings.rebalance_method,
      top_n: settingsStore.settings.rebalance_top_n,
      min_volume_usd: settingsStore.settings.rebalance_min_volume_usd,
      abs_momentum_days: settingsStore.settings.rebalance_abs_momentum_days,
      rel_strength_days: settingsStore.settings.rebalance_rel_strength_days,
      foam_days: settingsStore.settings.rebalance_foam_days,
    };
    emit('generateRebalancePlan', criteria);
  }
};

const updateWeights = (newWeights: { [key: string]: number }) => {
  if (settingsStore.settings) {
    settingsStore.settings.long_custom_weights = newWeights;
  }
};
</script>
