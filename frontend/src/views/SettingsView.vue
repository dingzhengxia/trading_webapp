<!-- frontend/src/views/SettingsView.vue -->
<template>
  <v-container>
    <v-row justify="center">
      <v-col cols="12" md="10" lg="8" xl="6">
        <v-skeleton-loader v-if="settingsStore.loading" type="card, article, actions"></v-skeleton-loader>

        <v-card v-else-if="settingsStore.settings">
          <v-tabs v-model="activeTab" bg-color="primary" grow>
            <v-tab value="general">通用配置</v-tab>
            <v-tab value="coin_pools">币种列表管理</v-tab>
          </v-tabs>

          <v-window v-model="activeTab">
            <!-- 通用配置标签页 -->
            <v-window-item value="general">
              <v-card-text>
                <h3 class="settings-subtitle">API 配置</h3>
                <v-row dense>
                  <v-col cols="12"><v-text-field label="API Key" v-model="settingsStore.settings.api_key" variant="outlined" density="compact" hide-details /></v-col>
                  <v-col cols="12"><v-text-field label="API Secret" v-model="settingsStore.settings.api_secret" type="password" variant="outlined" density="compact" hide-details /></v-col>
                  <v-col cols="12"><v-switch label="使用测试网" v-model="settingsStore.settings.use_testnet" color="primary" inset hide-details /></v-col>
                </v-row>
                <v-divider class="my-6"></v-divider>
                <h3 class="settings-subtitle">通用交易参数</h3>
                <v-row dense>
                  <v-col cols="12" sm="6"><v-text-field label="开仓重试次数" v-model.number="settingsStore.settings.open_maker_retries" type="number" variant="outlined" density="compact" /></v-col>
                  <v-col cols="12" sm="6"><v-text-field label="开仓订单超时(s)" v-model.number="settingsStore.settings.open_order_fill_timeout_seconds" type="number" variant="outlined" density="compact" /></v-col>
                  <v-col cols="12" sm="6"><v-text-field label="平仓重试次数" v-model.number="settingsStore.settings.close_maker_retries" type="number" variant="outlined" density="compact" /></v-col>
                  <v-col cols="12" sm="6"><v-text-field label="平仓订单超时(s)" v-model.number="settingsStore.settings.close_order_fill_timeout_seconds" type="number" variant="outlined" density="compact" /></v-col>
                </v-row>
                <v-divider class="my-6"></v-divider>
                <h3 class="settings-subtitle">网络代理</h3>
                <v-row dense>
                  <v-col cols="12"><v-switch label="启用代理" v-model="settingsStore.settings.enable_proxy" color="primary" inset hide-details /></v-col>
                  <v-col cols="12"><v-text-field label="代理 URL" v-model="settingsStore.settings.proxy_url" variant="outlined" density="compact" :disabled="!settingsStore.settings.enable_proxy" hide-details /></v-col>
                </v-row>
              </v-card-text>
            </v-window-item>

            <!-- 币种列表管理标签页 -->
            <v-window-item value="coin_pools">
              <v-card-text>
                <CoinPoolsManager ref="coinPoolsManagerRef" />
              </v-card-text>
            </v-window-item>
          </v-window>

          <v-divider></v-divider>
          <v-card-actions class="pa-4">
            <v-spacer></v-spacer>
            <v-btn color="success" variant="tonal" @click="handleSave">
              <v-icon left>mdi-content-save</v-icon>
              手动保存
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';
import CoinPoolsManager from '@/components/CoinPoolsManager.vue';

const settingsStore = useSettingsStore();
const activeTab = ref('general');
const coinPoolsManagerRef = ref<InstanceType<typeof CoinPoolsManager> | null>(null);

const handleSave = () => {
  if (activeTab.value === 'general') {
    if (settingsStore.settings) {
      settingsStore.saveGeneralSettings(settingsStore.settings);
    }
  } else if (activeTab.value === 'coin_pools') {
    coinPoolsManagerRef.value?.savePools();
  }
};
</script>

<style scoped>
.settings-subtitle {
  font-size: 1rem;
  font-weight: 500;
  color: #a9b3c1;
  margin-bottom: 16px;
}
</style>
