<!-- frontend/src/views/SettingsView.vue (最终版) -->
<template>
  <!-- REFACTOR: 增加底部内边距，防止内容被悬浮的 footer 遮挡 -->
  <div :style="{ paddingBottom: $vuetify.display.smAndDown ? '128px' : '80px' }">
    <v-container>
      <v-row justify="center">
        <v-col cols="12" md="10" lg="8" xl="6">
          <v-skeleton-loader
            v-if="settingsStore.loading"
            type="card, article, actions"
          ></v-skeleton-loader>

          <v-card v-else-if="settingsStore.settings">
            <v-tabs v-model="activeTab" bg-color="primary" grow>
              <v-tab value="general">通用配置</v-tab>
              <v-tab value="coin_pools">币种列表管理</v-tab>
            </v-tabs>

            <v-window v-model="activeTab">
              <v-window-item value="general">
                <v-card-text>
                  <h3 class="text-subtitle-1 font-weight-medium my-4">API 配置</h3>
                  <v-row dense>
                    <v-col cols="12"
                      ><v-text-field
                        label="API Key"
                        v-model="settingsStore.settings.api_key"
                        variant="outlined"
                        density="compact"
                        hide-details
                    /></v-col>
                    <v-col cols="12"
                      ><v-text-field
                        label="API Secret"
                        v-model="settingsStore.settings.api_secret"
                        type="password"
                        variant="outlined"
                        density="compact"
                        hide-details
                    /></v-col>
                    <v-col cols="12"
                      ><v-switch
                        label="使用测试网"
                        v-model="settingsStore.settings.use_testnet"
                        color="primary"
                        inset
                        hide-details
                    /></v-col>
                    <v-col cols="12"
                      ><v-switch
                        label="使用代理"
                        v-model="settingsStore.settings.enable_proxy"
                        color="primary"
                        inset
                        hide-details
                    /></v-col>
                    <v-col cols="12"
                      ><v-text-field
                        label="代理地址"
                        v-model="settingsStore.settings.proxy_url"
                        variant="outlined"
                        density="compact"
                        :disabled="!settingsStore.settings.enable_proxy"
                        hide-details
                    /></v-col>
                  </v-row>
                </v-card-text>
              </v-window-item>

              <v-window-item value="coin_pools">
                <v-card-text>
                  <CoinPoolsManager ref="coinPoolsManagerRef" />
                </v-card-text>
              </v-window-item>
            </v-window>

            <!-- REFACTOR: 移除了这里的 v-divider 和 v-card-actions -->
          </v-card>
        </v-col>
      </v-row>
    </v-container>
  </div>

  <!-- 固定悬浮底栏（共享组件）：保存按钮 -->
  <AppDockFooter>
    <v-btn color="success" variant="tonal" @click="handleSave">
      <v-icon left>mdi-content-save</v-icon>
      手动保存
    </v-btn>
  </AppDockFooter>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useSettingsStore } from '@/stores/settingsStore'
import CoinPoolsManager from '@/components/CoinPoolsManager.vue'
import AppDockFooter from '@/components/AppDockFooter.vue'

const settingsStore = useSettingsStore()
const activeTab = ref('general')
const coinPoolsManagerRef = ref<InstanceType<typeof CoinPoolsManager> | null>(null)

// handleSave 函数本身是正确的，无需修改
const handleSave = () => {
  if (activeTab.value === 'general') {
    if (settingsStore.settings) {
      settingsStore.saveGeneralSettings(settingsStore.settings)
    }
  } else if (activeTab.value === 'coin_pools') {
    if (coinPoolsManagerRef.value) {
      coinPoolsManagerRef.value.savePools()
    }
  }
}

onMounted(() => {
  // 确保在进入页面时获取设置
  if (!settingsStore.settings) {
    settingsStore.fetchSettings()
  }
})
</script>
