<template>
  <v-container>
    <v-row justify="center">
      <v-col cols="12" md="10" lg="8" xl="6">
        <v-skeleton-loader v-if="settingsStore.loading" type="card, list-item-two-line@4"></v-skeleton-loader>

        <v-card v-else-if="settingsStore.settings">
          <v-card-title class="text-h5">应用设置</v-card-title>
          <v-list lines="two" subheader>

            <!-- API 设置 -->
            <v-list-subheader>API 配置</v-list-subheader>
            <v-list-item>
              <v-text-field
                label="API Key"
                v-model="settingsStore.settings.api_key"
                variant="outlined"
                density="compact"
                class="mb-3"
                hide-details
              ></v-text-field>
            </v-list-item>
            <v-list-item>
               <v-text-field
                label="API Secret"
                v-model="settingsStore.settings.api_secret"
                type="password"
                variant="outlined"
                density="compact"
                class="mb-3"
                hide-details
              ></v-text-field>
            </v-list-item>
            <v-list-item>
              <v-switch
                label="使用测试网"
                v-model="settingsStore.settings.use_testnet"
                color="primary"
                inset
                hide-details
              ></v-switch>
            </v-list-item>

            <!-- 交易高级参数 -->
            <v-list-subheader>通用交易参数</v-list-subheader>
            <v-list-item>
              <v-row dense>
                <v-col cols="12" sm="6"><v-text-field label="开仓重试次数" v-model.number="settingsStore.settings.open_maker_retries" type="number" variant="outlined" density="compact" /></v-col>
                <v-col cols="12" sm="6"><v-text-field label="开仓订单超时(s)" v-model.number="settingsStore.settings.open_order_fill_timeout_seconds" type="number" variant="outlined" density="compact" /></v-col>
                <v-col cols="12" sm="6"><v-text-field label="平仓重试次数" v-model.number="settingsStore.settings.close_maker_retries" type="number" variant="outlined" density="compact" /></v-col>
                <v-col cols="12" sm="6"><v-text-field label="平仓订单超时(s)" v-model.number="settingsStore.settings.close_order_fill_timeout_seconds" type="number" variant="outlined" density="compact" /></v-col>
              </v-row>
            </v-list-item>

            <!-- 代理设置 -->
            <v-list-subheader>网络代理</v-list-subheader>
            <v-list-item>
                <v-switch
                    label="启用代理"
                    v-model="settingsStore.settings.enable_proxy"
                    color="primary"
                    inset
                    class="mb-2"
                    hide-details
                ></v-switch>
                <v-text-field
                    label="代理 URL (e.g., http://127.0.0.1:7890)"
                    v-model="settingsStore.settings.proxy_url"
                    variant="outlined"
                    density="compact"
                    :disabled="!settingsStore.settings.enable_proxy"
                    hide-details
                ></v-text-field>
            </v-list-item>

          </v-list>
           <v-card-actions>
              <v-spacer></v-spacer>
              <v-btn color="success" variant="tonal" @click="settingsStore.saveSettings()">
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
import { useSettingsStore } from '@/stores/settingsStore';
const settingsStore = useSettingsStore();
</script>
