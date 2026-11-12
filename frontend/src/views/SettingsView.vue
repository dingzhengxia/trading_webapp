<!-- frontend/src/views/SettingsView.vue (最终版) -->
<template>
  <div>
    <v-row justify="center">
      <v-col cols="12" md="10" lg="8" xl="7">
        <PageSkeleton v-if="settingsStore.loading" />

        <v-card v-else-if="settingsStore.settings" variant="flat" class="settings-card">
          <v-tabs v-model="activeTab" class="tabs-quiet" grow>
            <v-tab value="general">通用配置</v-tab>
            <v-tab value="coin_pools">币种列表管理</v-tab>
          </v-tabs>

          <v-window v-model="activeTab">
            <v-window-item value="general">
              <v-card-text>
                <SectionHeader icon="mdi-key-variant" title="API 配置" spaced /> 
                <v-row dense>
                  <v-col cols="12"
                    ><v-text-field
                      label="API Key"
                      v-model="settingsStore.settings.api_key"
                      hide-details
                  /></v-col>
                  <v-col cols="12"
                    ><v-text-field
                      label="API Secret"
                      v-model="settingsStore.settings.api_secret"
                      type="password"
                      hide-details
                  /></v-col>
                  <v-col cols="12"
                    ><v-switch
                      label="使用测试网"
                      v-model="settingsStore.settings.use_testnet"
                      color="primary"
                      hide-details
                  /></v-col>
                  <v-col cols="12"
                    ><v-switch
                      label="使用代理"
                      v-model="settingsStore.settings.enable_proxy"
                      color="primary"
                      hide-details
                  /></v-col>
                  <v-col cols="12"
                    ><v-text-field
                      label="代理地址"
                      v-model="settingsStore.settings.proxy_url"
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
        </v-card>
      </v-col>
    </v-row>
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
import { useSnackbarStore } from '@/stores/snackbar'
import CoinPoolsManager from '@/components/CoinPoolsManager.vue'
import AppDockFooter from '@/components/AppDockFooter.vue'
import PageSkeleton from '@/components/PageSkeleton.vue'
import SectionHeader from '@/components/SectionHeader.vue'

const settingsStore = useSettingsStore()
const activeTab = ref('general')
const coinPoolsManagerRef = ref<InstanceType<typeof CoinPoolsManager> | null>(null)

// handleSave 函数本身是正确的，无需修改
const handleSave = async () => {
  if (activeTab.value === 'general') {
    if (settingsStore.settings) {
      const result = await settingsStore.saveGeneralSettings(settingsStore.settings)
      useSnackbarStore().show({
        message: result.ok ? '配置已保存' : `保存失败：${result.detail}`,
        color: result.ok ? 'success' : 'error',
        timeout: result.ok ? 3000 : 8000,
      })
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

<style scoped>
.settings-card {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
}
</style>
