<template>
  <v-card class="d-flex flex-column fill-height">
    <!-- 顶部标签页 -->
    <v-tabs v-model="tab" bg-color="blue-grey-darken-4" grow>
      <v-tab value="trade">开仓参数</v-tab>
      <v-tab value="rebalance">智能再平衡</v-tab>
    </v-tabs>

    <!-- 中间内容区，可滚动 -->
    <v-card-text class="flex-grow-1 pa-4" style="overflow-y: auto;">
      <v-skeleton-loader v-if="settingsStore.loading" type="article, actions"></v-skeleton-loader>

      <v-window v-else v-model="tab">
        <!-- 交易参数 Tab -->
        <v-window-item value="trade" class="pa-1">
          <v-form v-if="settingsStore.settings">
            <h3 class="tab-subtitle">通用设置</h3>
            <v-text-field
              label="杠杆"
              v-model.number="settingsStore.settings.leverage"
              type="number"
              variant="outlined"
              density="compact"
              hide-details
            />

            <v-divider class="my-4"></v-divider>

            <h3 class="tab-subtitle d-flex justify-space-between align-center">
              <span>多头设置</span>
              <v-switch
                v-model="settingsStore.settings.enable_long_trades"
                color="success"
                inset
                dense
                hide-details
                class="ml-4 flex-grow-0"
              ></v-switch>
            </h3>
            <div :class="{ 'disabled-group': !settingsStore.settings.enable_long_trades }">
              <v-text-field label="多头总价值 (U)" v-model.number="settingsStore.settings.total_long_position_value" type="number" variant="outlined" density="compact" class="mb-3" hide-details />
              <v-combobox
                label="多头币种"
                v-model="settingsStore.settings.long_coin_list"
                :items="settingsStore.availableLongCoins"
                multiple chips closable-chips variant="outlined" density="compact" class="mb-3" hide-details
              ></v-combobox>
              <v-btn
                variant="tonal" size="small" block
                @click="uiStore.showWeightDialog = true"
                :disabled="!settingsStore.settings.long_coin_list || settingsStore.settings.long_coin_list.length === 0"
              >
                配置权重
              </v-btn>

              <v-switch v-model="settingsStore.settings.enable_long_sl_tp" label="多头止盈止损" color="success" inset hide-details class="mt-2"></v-switch>
              <v-row dense :class="{ 'disabled-group': !settingsStore.settings.enable_long_sl_tp }">
                <v-col cols="6">
                  <v-text-field label="止盈 (%)" v-model.number="settingsStore.settings.long_take_profit_percentage" type="number" variant="outlined" density="compact" hide-details :disabled="!settingsStore.settings.enable_long_sl_tp" />
                </v-col>
                <v-col cols="6">
                  <v-text-field label="止损 (%)" v-model.number="settingsStore.settings.long_stop_loss_percentage" type="number" variant="outlined" density="compact" hide-details :disabled="!settingsStore.settings.enable_long_sl_tp" />
                </v-col>
              </v-row>
            </div>

            <v-divider class="my-4"></v-divider>

            <h3 class="tab-subtitle d-flex justify-space-between align-center">
              <span>空头设置</span>
               <v-switch
                v-model="settingsStore.settings.enable_short_trades"
                color="error"
                inset
                dense
                hide-details
                class="ml-4 flex-grow-0"
              ></v-switch>
            </h3>
            <div :class="{ 'disabled-group': !settingsStore.settings.enable_short_trades }">
              <v-text-field label="空头总价值 (U)" v-model.number="settingsStore.settings.total_short_position_value" type="number" variant="outlined" density="compact" class="mb-3" hide-details />
              <v-combobox
                label="空头币种"
                v-model="settingsStore.settings.short_coin_list"
                :items="settingsStore.availableShortCoins"
                multiple chips closable-chips variant="outlined" density="compact" hide-details
              ></v-combobox>

              <v-switch v-model="settingsStore.settings.enable_short_sl_tp" label="空头止盈止损" color="error" inset hide-details class="mt-2"></v-switch>
              <v-row dense :class="{ 'disabled-group': !settingsStore.settings.enable_short_sl_tp }">
                <v-col cols="6">
                  <v-text-field label="止盈 (%)" v-model.number="settingsStore.settings.short_take_profit_percentage" type="number" variant="outlined" density="compact" hide-details :disabled="!settingsStore.settings.enable_short_sl_tp" />
                </v-col>
                <v-col cols="6">
                  <v-text-field label="止损 (%)" v-model.number="settingsStore.settings.short_stop_loss_percentage" type="number" variant="outlined" density="compact" hide-details :disabled="!settingsStore.settings.enable_short_sl_tp" />
                </v-col>
              </v-row>
            </div>
          </v-form>
        </v-window-item>

        <!-- 再平衡 Tab -->
        <v-window-item value="rebalance" class="pa-1">
          <v-form v-if="settingsStore.settings">
            <p class="text-caption mb-4">根据市场指标动态筛选弱势币种，并生成调整空头仓位的交易计划。</p>
            <v-select
              label="筛选策略"
              v-model="settingsStore.settings.rebalance_method"
              :items="[{title: '多因子做空弱势', value: 'multi_factor_weakest'}, {title: '做空泡沫', value: 'foam'}]"
              variant="outlined" density="compact" class="mb-3" hide-details
            ></v-select>
            <v-text-field
              label="选择币种数量"
              v-model.number="settingsStore.settings.rebalance_top_n"
              type="number" variant="outlined" density="compact" class="mb-3" hide-details
            />
            <v-text-field
              label="最小24h交易额 (U)"
              v-model.number="settingsStore.settings.rebalance_min_volume_usd"
              type="number" variant="outlined" density="compact" class="mb-3" hide-details
            />

            <div v-if="settingsStore.settings.rebalance_method === 'multi_factor_weakest'" class="mt-3">
              <v-text-field
                label="[弱势] 绝对动量周期(天)"
                v-model.number="settingsStore.settings.rebalance_abs_momentum_days"
                type="number" variant="outlined" density="compact" class="mb-3" hide-details
              />
              <v-text-field
                label="[弱势] 相对强度周期(天)"
                v-model.number="settingsStore.settings.rebalance_rel_strength_days"
                type="number" variant="outlined" density="compact" hide-details
              />
            </div>
            <div v-if="settingsStore.settings.rebalance_method === 'foam'" class="mt-3">
              <v-text-field
                label="[泡沫] 动量周期(天)"
                v-model.number="settingsStore.settings.rebalance_foam_days"
                type="number" variant="outlined" density="compact" hide-details
              />
            </div>
          </v-form>
        </v-window-item>
      </v-window>
    </v-card-text>

    <!-- 底部操作按钮区 -->
    <v-divider></v-divider>
    <div class="pa-4">
      <div v-if="tab === 'trade'">
        <v-btn block color="indigo" class="mb-3" @click="syncSlTp" :disabled="uiStore.isRunning">校准 SL/TP</v-btn>
        <v-btn block color="success" @click="startTrading" :loading="uiStore.isRunning" :disabled="uiStore.isRunning" size="large">▶ 开始开仓</v-btn>
        <v-btn block color="error" @click="stopTrading" :disabled="!uiStore.isRunning" size="large" class="mt-3">⏹ 停止执行</v-btn>
      </div>
      <div v-if="tab === 'rebalance'">
        <v-btn block color="info" @click="generatePlan" :loading="rebalanceLoading" size="large">生成再平衡计划</v-btn>
      </div>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useUiStore } from '@/stores/uiStore';
import { useSettingsStore } from '@/stores/settingsStore';
import api from '@/services/api';
import type { RebalancePlan } from '@/models/types';

const uiStore = useUiStore();
const settingsStore = useSettingsStore();
const tab = ref('trade');
const rebalanceLoading = ref(false);

const startTrading = async () => {
  if (!settingsStore.settings) {
    uiStore.logStore.addLog({ message: "配置尚未加载，无法开始交易。", level: "error", timestamp: new Date().toLocaleTimeString() });
    return;
  }
  uiStore.logStore.clearLogs();
  try {
    await api.post('/api/trading/start', settingsStore.settings);
  } catch(e: any) {
    uiStore.logStore.addLog({ message: `启动交易失败: ${e.message}`, level: "error", timestamp: new Date().toLocaleTimeString() });
  }
};

const stopTrading = async () => {
  try {
    await api.post('/api/trading/stop');
  } catch(e: any) {
    uiStore.logStore.addLog({ message: `发送停止指令失败: ${e.message}`, level: "error", timestamp: new Date().toLocaleTimeString() });
  }
};

const generatePlan = async () => {
  if (!settingsStore.settings) return;

  rebalanceLoading.value = true;
  uiStore.logStore.clearLogs();

  try {
    const criteria = {
      method: settingsStore.settings.rebalance_method,
      top_n: settingsStore.settings.rebalance_top_n,
      min_volume_usd: settingsStore.settings.rebalance_min_volume_usd,
      abs_momentum_days: settingsStore.settings.rebalance_abs_momentum_days,
      rel_strength_days: settingsStore.settings.rebalance_rel_strength_days,
      foam_days: settingsStore.settings.rebalance_foam_days,
    };
    const response = await api.post<RebalancePlan>('/api/rebalance/plan', criteria);

    if (response.data.error) {
       uiStore.logStore.addLog({ message: `计划生成失败: ${response.data.error}`, level: "error", timestamp: new Date().toLocaleTimeString() });
    } else {
       uiStore.rebalancePlan = response.data;
       uiStore.showRebalanceDialog = true;
    }
  } catch(e: any) {
    const errorMsg = e.response?.data?.detail || e.message;
    uiStore.logStore.addLog({ message: `生成计划请求失败: ${errorMsg}`, level: "error", timestamp: new Date().toLocaleTimeString() });
  } finally {
    rebalanceLoading.value = false;
  }
};

const syncSlTp = async () => {
  if (!settingsStore.settings) return;
  uiStore.logStore.clearLogs();
  uiStore.logStore.addLog({ message: "正在提交 SL/TP 校准任务...", level: 'info', timestamp: new Date().toLocaleTimeString() });
  try {
    await api.post('/api/trading/sync-sltp', settingsStore.settings);
  } catch(e: any) {
    uiStore.logStore.addLog({ message: `校准任务失败: ${e.message}`, level: "error", timestamp: new Date().toLocaleTimeString() });
  }
};
</script>

<style scoped>
.tab-subtitle {
  font-size: 0.9rem;
  font-weight: 500;
  color: #a9b3c1;
  margin-bottom: 8px;
  margin-top: 1.2rem;
}
.disabled-group {
  opacity: 0.6;
  pointer-events: none; /* 阻止组内所有鼠标事件 */
  transition: opacity 0.3s ease;
}
</style>
