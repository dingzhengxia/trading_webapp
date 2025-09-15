<template>
  <v-card>
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
            <v-col cols="12" md="6">
              <v-card variant="outlined">
                <v-card-title>多头设置</v-card-title>
                <v-card-text>
                  <v-switch v-model="form.enable_long_trades" label="开启多头交易" color="success" inset></v-switch>
                  <v-text-field v-model.number="form.total_long_position_value" label="多头总价值 (USD)" type="number"
                    :disabled="!form.enable_long_trades"></v-text-field>
                  <v-autocomplete v-model="form.long_coin_list" :items="settingsStore.available_long_coins"
                    label="多头币种列表" multiple chips closable-chips :disabled="!form.enable_long_trades">
                  </v-autocomplete>
                  <v-btn size="small" @click="isWeightDialogVisible = true" :disabled="!form.enable_long_trades">配置权重</v-btn>
                </v-card-text>
              </v-card>
            </v-col>

            <v-col cols="12" md="6">
              <v-card variant="outlined">
                <v-card-title>空头设置</v-card-title>
                <v-card-text>
                  <v-switch v-model="form.enable_short_trades" label="开启空头交易" color="error" inset></v-switch>
                  <v-text-field v-model.number="form.total_short_position_value" label="空头总价值 (USD)" type="number"
                    :disabled="!form.enable_short_trades"></v-text-field>
                  <v-autocomplete v-model="form.short_coin_list" :items="settingsStore.available_short_coins"
                    label="空头币种列表" multiple chips closable-chips :disabled="!form.enable_short_trades">
                  </v-autocomplete>
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
              <v-select v-model="form.rebalance_method" :items="['multi_factor_weakest', 'foam']" label="筛选策略">
              </v-select>
              <v-text-field v-model.number="form.rebalance_top_n" label="目标币种数量 (Top N)" type="number"></v-text-field>
              <v-text-field v-model.number="form.rebalance_min_volume_usd" label="最小24h交易额 (USD)"
                type="number"></v-text-field>
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model.number="form.rebalance_abs_momentum_days" label="绝对动量天数" type="number"></v-text-field>
              <v-text-field v-model.number="form.rebalance_rel_strength_days" label="相对强度天数 (vs BTC)"
                type="number"></v-text-field>
              <v-text-field v-model.number="form.rebalance_foam_days" label="FOAM动量天数" type="number"></v-text-field>
            </v-col>
          </v-row>
        </v-window-item>
      </v-window>
    </v-card-text>

    <v-divider></v-divider>

    <v-card-actions class="pa-4">
      <!-- 按钮的 disabled 状态现在由父组件的 isRunning prop 决定 -->
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

  <WeightConfigDialog v-model="isWeightDialogVisible" :coins="form.long_coin_list"
    :weights="form.long_custom_weights" @save="updateWeights" />
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue';
import { useSettingsStore } from '@/stores/settings';
import WeightConfigDialog from './WeightConfigDialog.vue';
import type { TradePlan } from '@/types/trading';

// 步骤1: 定义从父组件接收的 props 和要发出的 emits
const props = defineProps<{
  isRunning: boolean;
}>();

const emit = defineEmits<{
  (e: 'startTrading', plan: TradePlan): void;
  (e: 'syncSltp', settings: any): void;
  (e: 'generateRebalancePlan', criteria: any): void;
}>();


// 组件内部不再需要 isRunning, apiClient, snackbarStore, WebSocket 等
// 它只关心自己的表单数据
const settingsStore = useSettingsStore();

const tab = ref('general');
const isWeightDialogVisible = ref(false);

const form = ref<Partial<TradePlan>>({
  long_coin_list: [],
  short_coin_list: [],
  long_custom_weights: {},
  rebalance_method: 'multi_factor_weakest',
  rebalance_top_n: 50,
  rebalance_min_volume_usd: 20000000,
  rebalance_abs_momentum_days: 30,
  rebalance_rel_strength_days: 60,
  rebalance_foam_days: 1,
});

onMounted(() => {
  form.value = { ...settingsStore.user_settings };
});

watch(() => settingsStore.user_settings, (newSettings) => {
  form.value = { ...newSettings };
}, { deep: true });

// 步骤2: 修改点击事件处理函数，让它们发出 emit 通知父组件
const onStartTrading = () => {
  const plan: TradePlan = { ...settingsStore.default_settings, ...form.value };
  emit('startTrading', plan);
};

const onSyncSlTp = () => {
  const settings = { ...settingsStore.user_settings };
  emit('syncSltp', settings);
};

const onGenerateRebalancePlan = () => {
  const criteria = {
    method: form.value.rebalance_method || 'multi_factor_weakest',
    top_n: form.value.rebalance_top_n || 50,
    min_volume_usd: form.value.rebalance_min_volume_usd || 20000000.0,
    abs_momentum_days: form.value.rebalance_abs_momentum_days || 30,
    rel_strength_days: form.value.rebalance_rel_strength_days || 60,
    foam_days: form.value.rebalance_foam_days || 1,
  };
  emit('generateRebalancePlan', criteria);
};

const updateWeights = (newWeights: { [key: string]: number }) => {
  form.value.long_custom_weights = newWeights;
};
</script>
