<!-- frontend/src/views/SettingsView.vue (最终版) -->
<template>
  <div>
    <v-row justify="center">
      <v-col cols="12" md="10" lg="8" xl="7">
        <PageSkeleton v-if="settingsStore.loading || !draft" />

        <v-card v-else variant="flat" class="settings-card">
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
                      v-model="draft.api_key"
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
                      v-model="draft.api_secret"
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
                      v-model="draft.use_testnet"
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
                      v-model="draft.enable_proxy"
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
                      v-model="draft.proxy_url"
                      :disabled="!draft.enable_proxy"
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
                      v-model="draft.unprotected_position_action"
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
                  <NumberField
                    v-model="draft.close_price_chase_ticks"
                    label="平仓让价 tick 数（0=关闭）"
                    min="0"
                    max="10"
                    hint="reduceOnly 平仓单连续 2 轮 0 成交后按 tick 让价重挂"
                    persistent-hint
                    :help="HELP.settings.closeChaseTicks"
                    sm="6"
                  />
                </v-row>

                <!-- 开仓冷静期：打开即拒绝所有开仓，连亏自动触发（trade_cooldown.py） -->
                <SectionHeader icon="mdi-timer-pause" title="开仓冷静期" spaced />
                <v-row dense>
                  <v-col cols="12"
                    ><v-switch
                      v-model="draft.trade_cooldown_enabled"
                      color="warning"
                      hide-details
                      @update:modelValue="persistQuietly"
                    >
                      <template #label>
                        冷静期内拒绝开仓
                        <HelpTip :text="HELP.settings.tradeCooldown" />
                      </template>
                    </v-switch></v-col
                  >
                  <v-col v-if="cooldownRemaining" cols="12">
                    <v-alert
                      type="warning"
                      variant="tonal"
                      density="compact"
                      class="text-caption"
                    >
                      🧊 冷静中，剩余约 {{ cooldownRemaining }} 分钟（{{
                        draft.trade_cooldown_triggered_by === 'auto'
                          ? '连亏自动触发'
                          : '手动打开'
                      }}）
                      <HelpTip :text="HELP.settings.cooldownState" />
                    </v-alert>
                  </v-col>
                  <NumberField
                    v-model="draft.trade_cooldown_minutes"
                    label="冷静时长（分钟）"
                    min="1"
                    max="1440"
                    :help="HELP.settings.tradeCooldownMinutes"
                    cols="6"
                    sm="6"
                  />
                  <NumberField
                    v-model="draft.trade_cooldown_loss_streak"
                    label="连亏次数阈值"
                    min="1"
                    max="10"
                    hint="当日连续 N 次操作亏损自动进入冷静期"
                    persistent-hint
                    :help="HELP.settings.tradeCooldownStreak"
                    cols="6"
                    sm="6"
                  />
                </v-row>

                <SectionHeader icon="mdi-speedometer" title="API 限流（热更新）" spaced />
                <v-row dense>
                  <NumberField
                    v-model="draft.api_max_concurrency"
                    label="最大并发"
                    min="1"
                    max="20"
                    :help="HELP.settings.apiMaxConcurrency"
                    cols="6"
                    sm="3"
                  />
                  <NumberField
                    v-model="draft.api_min_interval_sec"
                    label="最小间隔(秒)"
                    min="0"
                    max="5"
                    step="0.01"
                    :help="HELP.settings.apiMinInterval"
                    cols="6"
                    sm="3"
                  />
                  <NumberField
                    v-model="draft.api_max_retries"
                    label="最大重试"
                    min="1"
                    max="10"
                    :help="HELP.settings.apiMaxRetries"
                    cols="6"
                    sm="3"
                  />
                  <NumberField
                    v-model="draft.api_failure_threshold"
                    label="熔断失败阈值"
                    min="1"
                    max="50"
                    :help="HELP.settings.apiFailureThreshold"
                    cols="6"
                    sm="3"
                  />
                  <NumberField
                    v-model="draft.api_circuit_breaker_cooldown_sec"
                    label="熔断冷却(秒)"
                    min="1"
                    max="3600"
                    :help="HELP.settings.apiCooldown"
                    cols="6"
                    sm="3"
                  />
                  <NumberField
                    v-model="draft.api_418_cooldown_sec"
                    label="418 冷却(秒)"
                    min="1"
                    max="3600"
                    :help="HELP.settings.api418Cooldown"
                    cols="6"
                    sm="3"
                  />
                  <NumberField
                    v-model="draft.api_429_base_backoff_sec"
                    label="429 退避基数(秒)"
                    min="0.2"
                    max="60"
                    step="0.1"
                    :help="HELP.settings.api429Base"
                    cols="6"
                    sm="3"
                  />
                  <NumberField
                    v-model="draft.api_429_max_backoff_sec"
                    label="429 退避上限(秒)"
                    min="0.2"
                    max="600"
                    step="0.1"
                    :help="HELP.settings.api429Max"
                    cols="6"
                    sm="3"
                  />
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

  <!-- 固定悬浮底栏（共享组件）：改动自动保存，这里保留「立即保存」 -->
  <AppDockFooter>
    <span v-if="lastSavedAt" class="text-caption text-medium-emphasis mr-2">
      已自动保存 {{ formatClockTime(lastSavedAt) }}
    </span>
    <v-btn color="success" variant="tonal" :loading="saving" @click="persistNow">
      <v-icon left>mdi-content-save</v-icon>
      立即保存
    </v-btn>
    <HelpTip :text="HELP.settings.saveBtn" />
  </AppDockFooter>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, onUnmounted } from 'vue'
import { useSettingsStore } from '@/stores/settingsStore'
import { useSnackbarStore } from '@/stores/snackbar'
import { useDraftSettings } from '@/composables/useDraftSettings'
import { formatClockTime } from '@/utils/format'
import CoinPoolsManager from '@/components/CoinPoolsManager.vue'
import AppDockFooter from '@/components/AppDockFooter.vue'
import PageSkeleton from '@/components/PageSkeleton.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import NumberField from '@/components/NumberField.vue'
import HelpTip from '@/components/HelpTip.vue'
import { HELP } from '@/config/help'

const settingsStore = useSettingsStore()
const activeTab = ref('general')
const coinPoolsManagerRef = ref<InstanceType<typeof CoinPoolsManager> | null>(null)

// 草稿模式：表单只绑 draft，改动经 useDraftSettings 防抖 diff 自动落库，
// 不再依赖用户手动点保存（历史问题：改完不点按钮 → 刷新全丢）。
const { draft, commitDraft, flushDraftSave, lastSavedAt } = useDraftSettings()
const saving = ref(false)

/** 安全开关（冷静期）改动立即落库，不等 1.5s 防抖：开关必须即刻生效。 */
const persistQuietly = async () => {
  if (!draft.value) return
  await commitDraft()
}

/** 通用配置立即保存；币种池 tab 交给自己的保存逻辑。 */
const persistNow = async () => {
  if (activeTab.value === 'coin_pools') {
    coinPoolsManagerRef.value?.savePools()
    return
  }
  if (!draft.value || saving.value) return
  saving.value = true
  const ok = await commitDraft(true)
  saving.value = false
  useSnackbarStore().show({
    message: ok ? '配置已保存' : '保存失败，详见下方提示',
    color: ok ? 'success' : 'error',
    timeout: ok ? 2500 : 6000,
  })
}

// 冷静期剩余分钟：本地 30s 刷新一次（服务端 until 为准，前端只做展示）
const nowTick = ref(Date.now())
let cooldownTimer: number | undefined
const cooldownRemaining = computed<string | null>(() => {
  const s = settingsStore.settings
  const tick = nowTick.value // 显式引用，保证随定时器重算
  if (!s?.trade_cooldown_enabled || !s.trade_cooldown_until) return null
  const leftMin = Math.ceil((new Date(s.trade_cooldown_until).getTime() - tick) / 60000)
  return leftMin > 0 ? String(leftMin) : null
})

onMounted(() => {
  // 每次进入都拉一次服务端最新值：冷静期可能已被“连亏自动触发”打开，
  // 草稿没有未保存改动时 useDraftSettings 会自动重灌成最新值。
  void settingsStore.fetchSettings()
  cooldownTimer = window.setInterval(() => {
    nowTick.value = Date.now()
  }, 30000)
})

onBeforeUnmount(() => {
  // 防抖窗口内（1.5s）的修改立刻提交，避免“改完就切页/刷新”丢失
  flushDraftSave()
})

onUnmounted(() => {
  if (cooldownTimer !== undefined) window.clearInterval(cooldownTimer)
})
</script>

<style scoped>
.settings-card {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
}
</style>
