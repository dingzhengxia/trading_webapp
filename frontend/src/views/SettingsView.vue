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

  <!-- REFACTOR: 新增悬浮在底部的 v-footer -->
  <v-footer
    style="
      position: fixed;
      bottom: 0;
      right: 0;
      z-index: 1000;
      border-top: 1px solid rgba(255, 255, 255, 0.12);
    "
    class="pa-0"
    :style="footerStyle"
  >
    <v-card flat tile class="d-flex align-center px-4 w-100" height="64px">
      <v-spacer></v-spacer>
      <!-- REFACTOR: 将保存按钮移动到这里 -->
      <v-btn color="success" variant="tonal" @click="handleSave">
        <v-icon left>mdi-content-save</v-icon>
        手动保存
      </v-btn>
    </v-card>
  </v-footer>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useDisplay } from 'vuetify' // REFACTOR: 导入 useDisplay
import { useSettingsStore } from '@/stores/settingsStore'
import CoinPoolsManager from '@/components/CoinPoolsManager.vue'

const settingsStore = useSettingsStore()
const activeTab = ref('general')
const coinPoolsManagerRef = ref<InstanceType<typeof CoinPoolsManager> | null>(null)

// REFACTOR: 增加用于动态计算 footer 位置的逻辑
const vuetifyDisplay = useDisplay()
const footerStyle = computed(() => {
  const styles: { bottom: string; left: string } = {
    bottom: vuetifyDisplay.smAndDown.value ? '56px' : '0px',
    left: '0px',
  }
  if (vuetifyDisplay.mdAndUp.value && vuetifyDisplay.application) {
    styles.left = `${vuetifyDisplay.application.left}px`
  }
  return styles
})

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
