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
                    >
                      <template #append-inner>
                        <HelpTip :text="HELP.settings.apiKey" />
                      </template>
                    </v-text-field></v-col
                  >
                  <v-col cols="12"
                    ><v-text-field
                      label="API Secret"
                      v-model="settingsStore.settings.api_secret"
                      type="password"
                      hide-details
                    >
                      <template #append-inner>
                        <HelpTip :text="HELP.settings.apiSecret" />
                      </template>
                    </v-text-field></v-col
                  >
                  <v-col cols="12"
                    ><v-switch
                      v-model="settingsStore.settings.use_testnet"
                      color="primary"
                      hide-details
                    >
                      <template #label>
                        使用测试网<HelpTip :text="HELP.settings.useTestnet" />
                      </template>
                    </v-switch></v-col
                  >
                  <v-col cols="12"
                    ><v-switch
                      v-model="settingsStore.settings.enable_proxy"
                      color="primary"
                      hide-details
                    >
                      <template #label>
                        使用代理<HelpTip :text="HELP.settings.enableProxy" />
                      </template>
                    </v-switch></v-col
                  >
                  <v-col cols="12"
                    ><v-text-field
                      label="代理地址"
                      v-model="settingsStore.settings.proxy_url"
                      :disabled="!settingsStore.settings.enable_proxy"
                      hide-details
                    >
                      <template #append-inner>
                        <HelpTip :text="HELP.settings.proxyUrl" />
                      </template>
                    </v-text-field></v-col
                  >
                </v-row>

                <SectionHeader icon="mdi-shield-alert" title="风控与执行兜底" spaced />
                <v-row dense>
                  <v-col cols="12" sm="6">
                    <v-select
                      label="裸仓处置（SL/TP 失败时）"
                      v-model="settingsStore.settings.unprotected_position_action"
                      :items="[
                        { title: '自动回收仓位（推荐）', value: 'auto_close' },
                        { title: '仅告警不触碰仓位', value: 'keep_alert' },
                      ]"
                      item-title="title"
                      item-value="value"
                      hide-details
                    >
                      <template #append-inner>
                        <HelpTip :text="HELP.settings.unprotectedAction" />
                      </template>
                    </v-select>
                  </v-col>
                  <v-col cols="12" sm="6">
                    <v-text-field
                      label="平仓让价 tick 数（0=关闭）"
                      v-model.number="settingsStore.settings.close_price_chase_ticks"
                      type="number"
                      min="0"
                      max="10"
                      hint="reduceOnly 平仓单连续 2 轮 0 成交后按 tick 让价重挂"
                      persistent-hint
                    >
                      <template #append-inner>
                        <HelpTip :text="HELP.settings.closeChaseTicks" />
                      </template>
                    </v-text-field>
                  </v-col>
                </v-row>

                <SectionHeader icon="mdi-speedometer" title="API 限流（热更新）" spaced />
                <v-row dense>
                  <v-col cols="6" sm="3">
                    <v-text-field
                      label="最大并发"
                      v-model.number="settingsStore.settings.api_max_concurrency"
                      type="number"
                      min="1"
                      max="20"
                      hide-details
                    >
                      <template #append-inner>
                        <HelpTip :text="HELP.settings.apiMaxConcurrency" />
                      </template>
                    </v-text-field>
                  </v-col>
                  <v-col cols="6" sm="3">
                    <v-text-field
                      label="最小间隔(秒)"
                      v-model.number="settingsStore.settings.api_min_interval_sec"
                      type="number"
                      min="0"
                      max="5"
                      step="0.01"
                      hide-details
                    >
                      <template #append-inner>
                        <HelpTip :text="HELP.settings.apiMinInterval" />
                      </template>
                    </v-text-field>
                  </v-col>
                  <v-col cols="6" sm="3">
                    <v-text-field
                      label="最大重试"
                      v-model.number="settingsStore.settings.api_max_retries"
                      type="number"
                      min="1"
                      max="10"
                      hide-details
                    >
                      <template #append-inner>
                        <HelpTip :text="HELP.settings.apiMaxRetries" />
                      </template>
                    </v-text-field>
                  </v-col>
                  <v-col cols="6" sm="3">
                    <v-text-field
                      label="熔断失败阈值"
                      v-model.number="settingsStore.settings.api_failure_threshold"
                      type="number"
                      min="1"
                      max="50"
                      hide-details
                    >
                      <template #append-inner>
                        <HelpTip :text="HELP.settings.apiFailureThreshold" />
                      </template>
                    </v-text-field>
                  </v-col>
                  <v-col cols="6" sm="3">
                    <v-text-field
                      label="熔断冷却(秒)"
                      v-model.number="settingsStore.settings.api_circuit_breaker_cooldown_sec"
                      type="number"
                      min="1"
                      max="3600"
                      hide-details
                    >
                      <template #append-inner>
                        <HelpTip :text="HELP.settings.apiCooldown" />
                      </template>
                    </v-text-field>
                  </v-col>
                  <v-col cols="6" sm="3">
                    <v-text-field
                      label="418 冷却(秒)"
                      v-model.number="settingsStore.settings.api_418_cooldown_sec"
                      type="number"
                      min="1"
                      max="3600"
                      hide-details
                    >
                      <template #append-inner>
                        <HelpTip :text="HELP.settings.api418Cooldown" />
                      </template>
                    </v-text-field>
                  </v-col>
                  <v-col cols="6" sm="3">
                    <v-text-field
                      label="429 退避基数(秒)"
                      v-model.number="settingsStore.settings.api_429_base_backoff_sec"
                      type="number"
                      min="0.2"
                      max="60"
                      step="0.1"
                      hide-details
                    >
                      <template #append-inner>
                        <HelpTip :text="HELP.settings.api429Base" />
                      </template>
                    </v-text-field>
                  </v-col>
                  <v-col cols="6" sm="3">
                    <v-text-field
                      label="429 退避上限(秒)"
                      v-model.number="settingsStore.settings.api_429_max_backoff_sec"
                      type="number"
                      min="0.2"
                      max="600"
                      step="0.1"
                      hide-details
                    >
                      <template #append-inner>
                        <HelpTip :text="HELP.settings.api429Max" />
                      </template>
                    </v-text-field>
                  </v-col>
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
    <HelpTip :text="HELP.settings.saveBtn" />
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
import HelpTip from '@/components/HelpTip.vue'
import { HELP } from '@/config/help'

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
