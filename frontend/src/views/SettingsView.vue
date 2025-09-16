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
                <!-- --- 新增：做多币种选择 --- -->
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
                ></v-select>
                <!-- --- 新增结束 --- -->
              </v-col>
              <v-col cols="12" md="6">
                <!-- --- 新增：做空币种选择 --- -->
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
                ></v-select>
                <!-- --- 新增结束 --- -->
              </v-col>
            </v-row>

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

const settingsStore = useSettingsStore();
const uiStore = useUiStore();

// --- 新增：币种选择的 debounce 函数 ---
const debouncedSavePoolSelection = debounce(() => {
  if (settingsStore.settings) {
    settingsStore.updateCoinPoolSelection(
      settingsStore.settings.user_selected_long_coins,
      settingsStore.settings.user_selected_short_coins
    );
  }
}, 500); // 500ms 延迟
// --- 新增结束 ---

// 手动保存所有设置
const saveAllSettings = () => {
  if (settingsStore.settings) {
    settingsStore.saveSettings();
  }
};

onMounted(() => {
  // 确保在组件挂载时拉取最新的配置，包括用户选择的币种列表
  if (!settingsStore.settings) {
    settingsStore.fetchSettings();
  }
});

</script>

<style scoped>
.settings-subtitle {
  font-size: 1rem;
  font-weight: 500;
  color: #a9b3c1;
  margin-bottom: 16px;
}
</style>
