<!-- frontend/src/views/SettingsView.vue -->
<template>
  <v-container>
    <v-row justify="center">
      <v-col cols="12" md="10" lg="8" xl="6">
        <v-skeleton-loader v-if="settingsStore.loading" type="card, article, actions"></v-skeleton-loader>

        <v-card v-else-if="settingsStore.settings">
          <v-card-title class="text-h5">应用设置</v-card-title>

          <v-card-text>
            <!-- API 设置 -->
            <h3 class="settings-subtitle">API 配置</h3>
            <v-row dense>
              <v-col cols="12">
                <v-text-field label="API Key" v-model="settingsStore.settings.api_key" variant="outlined" density="compact" hide-details />
              </v-col>
              <v-col cols="12">
                <v-text-field label="API Secret" v-model="settingsStore.settings.api_secret" type="password" variant="outlined" density="compact" hide-details />
              </v-col>
              <v-col cols="12">
                <v-switch label="使用测试网" v-model="settingsStore.settings.use_testnet" color="primary" inset hide-details />
              </v-col>
            </v-row>

            <v-divider class="my-6"></v-divider>

            <!-- 币种选择 -->
            <h3 class="settings-subtitle">币种选择</h3>
            <v-row dense>
              <v-col cols="12" md="6">
                <!-- --- 修改：使用 Transfer List 组件（或 v-select）来选择做多币种 --- -->
                <!-- 假设我们这里先用 v-select，如果需要更复杂的转移功能，再更换组件 -->
                <v-select
                  label="做多待选币种"
                  v-model="settingsStore.settings.user_selected_long_coins"
                  :items="settingsStore.availableCoins"
                  multiple
                  chips
                  closable-chips
                  variant="outlined"
                  density="compact"
                  clearable
                  @update:model-value="debouncedSavePoolSelection"
                  :disabled="!settingsStore.settings.enable_long_trades"
                  hint="将币种从总列表中选出作为做多目标"
                  persistent-hint
                ></v-select>
                <!-- --- 修改结束 --- -->
              </v-col>
              <v-col cols="12" md="6">
                <!-- --- 修改：使用 v-select 来选择做空币种 --- -->
                <v-select
                  label="做空待选币种"
                  v-model="settingsStore.settings.user_selected_short_coins"
                  :items="settingsStore.availableCoins"
                  multiple
                  chips
                  closable-chips
                  variant="outlined"
                  density="compact"
                  clearable
                  @update:model-value="debouncedSavePoolSelection"
                  :disabled="!settingsStore.settings.enable_short_trades"
                  hint="将币种从总列表中选出作为做空目标"
                  persistent-hint
                ></v-select>
                <!-- --- 修改结束 --- -->
              </v-col>
            </v-row>

            <!-- --- 优化：添加一个用于手动迁移币种的按钮（如果需要） --- -->
            <!-- <v-btn color="secondary" variant="tonal" class="mt-4" @click="openCoinTransferDialog">
              迁移币种到另一列表
            </v-btn> -->
            <!-- --- 优化结束 --- -->

            <v-divider class="my-6"></v-divider>

            <!-- 通用开仓设置 -->
            <h3 class="settings-subtitle">通用开仓设置</h3>
            <v-row dense>
              <v-col cols="12" sm="6"><v-text-field label="开仓重试次数" v-model.number="settingsStore.settings.open_maker_retries" type="number" variant="outlined" density="compact" /></v-col>
              <v-col cols="12" sm="6"><v-text-field label="开仓订单超时(s)" v-model.number="settingsStore.settings.open_order_fill_timeout_seconds" type="number" variant="outlined" density="compact" /></v-col>
              <v-col cols="12" sm="6"><v-text-field label="平仓重试次数" v-model.number="settingsStore.settings.close_maker_retries" type="number" variant="outlined" density="compact" /></v-col>
              <v-col cols="12" sm="6"><v-text-field label="平仓订单超时(s)" v-model.number="settingsStore.settings.close_order_fill_timeout_seconds" type="number" variant="outlined" density="compact" /></v-col>
            </v-row>

            <v-divider class="my-6"></v-divider>

            <!-- 代理设置 -->
            <h3 class="settings-subtitle">网络代理</h3>
            <v-row dense>
                <v-col cols="12">
                    <v-switch label="启用代理" v-model="settingsStore.settings.enable_proxy" color="primary" inset hide-details />
                </v-col>
                <v-col cols="12">
                    <v-text-field
                        label="代理 URL (e.g., http://127.0.0.1:19828)"
                        v-model="settingsStore.settings.proxy_url"
                        variant="outlined"
                        density="compact"
                        :disabled="!settingsStore.settings.enable_proxy"
                        hide-details
                    ></v-text-field>
                </v-col>
            </v-row>

          </v-card-text>
           <v-card-actions class="pa-4">
              <v-spacer></v-spacer>
              <v-btn color="success" variant="tonal" @click="saveAllSettings">
                <v-icon left>mdi-content-save</v-icon>
                手动保存全部
              </v-btn>
            </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUiStore } from '@/stores/uiStore';

// --- debounce ---
import { debounce } from 'lodash-es';
// --- debounce ---

const modelValue = defineModel<string>();

const settingsStore = useSettingsStore();
const uiStore = useUiStore();

const rebalanceMethods = [
  { value: 'multi_factor_weakest', text: '多因子弱势策略' },
  { value: 'foam', text: 'FOAM强势动量' }
];

// --- debounce 用于保存币种选择 ---
const debouncedSavePoolSelection = debounce(() => {
  if (settingsStore.settings) {
    settingsStore.updateCoinPoolSelection(
      settingsStore.settings.user_selected_long_coins,
      settingsStore.settings.user_selected_short_coins
    );
  }
}, 500);
// --- debounce 结束 ---

const saveAllSettings = () => {
  if (settingsStore.settings) {
    settingsStore.saveSettings();
  }
};

onMounted(() => {
  if (!settingsStore.settings) {
    settingsStore.fetchSettings();
  }
});

// --- 如果您需要一个专门的组件来处理币种在两个列表之间的转移，可以在这里添加 ---
// --- 例如：一个可用的币种列表，一个已选的做多列表，一个已选的做空列表，以及移动按钮 ---
// --- 但目前使用 v-select 的多选功能，也能实现基本的可选和保存 ---

</script>

<style scoped>
.settings-subtitle {
  font-size: 1rem;
  font-weight: 500;
  color: #a9b3c1;
  margin-bottom: 16px;
}
</style>
