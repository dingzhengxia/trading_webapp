<!-- frontend/src/views/ReportsView.vue（周期报告：monitor periodic_reporter 并入） -->
<!--
  重设计（redesign-spec 2026-11-13 · B3）：
  旧版首屏是一排配置卡 + 8 行 .env 说明，真正的报告内容沉底。
  新版顺序：最近报告内容置顶 → 报告配置卡×N（lg 6:6 双列）→ 钉钉推送配置
  （.env 长文默认折叠成一行「推送配置说明 ▸」）。
-->
<template>
  <div>
    <!-- 最近报告内容（置顶：本页职责是「看报告」） -->
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-medium d-flex align-center flex-wrap ga-2">
        <v-icon start>mdi-text-box-outline</v-icon>
        <span>最近报告</span>
        <v-spacer></v-spacer>
        <SmartSelect
          v-model="selectedReport"
          :items="latestNames"
          class="reports-picker"
        ></SmartSelect>
      </v-card-title>
      <v-divider></v-divider>
      <v-card-text>
        <template v-if="currentLatest">
          <div class="text-caption text-medium-emphasis mb-2">
            {{ currentLatest.title }} · 生成于 {{ formatTime(currentLatest.generated_at) }}
          </div>
          <pre class="report-body">{{ currentLatest.markdown }}</pre>
        </template>
        <v-alert v-else type="info" variant="tonal" density="compact">
          还没有报告。启用周期报告后到点自动生成，或点某份报告的「立即生成」。
        </v-alert>
      </v-card-text>
    </v-card>

    <!-- 报告配置卡（lg 6:6 双列） -->
    <v-row class="mt-4">
      <v-col v-for="report in reports" :key="report.report_name" cols="12" lg="6">
        <v-card height="100%">
          <v-card-title class="text-subtitle-1 font-weight-medium d-flex align-center flex-wrap ga-2">
            <span>{{ report.report_name }}</span>
            <v-chip v-if="report.running" size="x-small" color="info" variant="flat">生成中</v-chip>
            <v-spacer></v-spacer>
            <v-switch
              v-model="report.enabled"
              color="primary"
              inset
              hide-details
              density="compact"
              :disabled="saving"
            ></v-switch>
          </v-card-title>
          <v-divider></v-divider>
          <v-card-text>
            <v-row dense>
              <v-col cols="12" sm="6">
                <SmartSelect
                  v-model="report.run_interval"
                  :items="intervalOptions"
                  label="统计周期"
                  :disabled="saving"
                ></SmartSelect>
              </v-col>
              <v-col cols="12" sm="6">
                <v-text-field
                  v-model.number="report.top_n_by_volume"
                  label="取样合约数（按成交额 TopN）"
                  type="number"
                  min="5"
                  max="500"
                  density="compact"
                  variant="outlined"
                  hide-details
                  :disabled="saving"
                ></v-text-field>
              </v-col>
              <v-col cols="12" sm="6">
                <v-text-field
                  v-model.number="report.top_n_gainers"
                  label="涨幅榜条数"
                  type="number"
                  min="1"
                  max="50"
                  density="compact"
                  variant="outlined"
                  hide-details
                  :disabled="saving"
                ></v-text-field>
              </v-col>
              <v-col cols="12" sm="6">
                <v-text-field
                  v-model.number="report.top_n_volume_ratio"
                  label="放量榜条数"
                  type="number"
                  min="1"
                  max="50"
                  density="compact"
                  variant="outlined"
                  hide-details
                  :disabled="saving"
                ></v-text-field>
              </v-col>
            </v-row>

            <div class="d-flex flex-wrap ga-2 mt-3 text-caption text-medium-emphasis">
              <span>上次：{{ formatTime(report.last_run) }}</span>
              <span>·</span>
              <span>下次：{{ report.enabled ? formatTime(report.next_run) : '未启用' }}</span>
              <span v-if="report.scanned != null">· 样本 {{ report.scanned }} 个</span>
            </div>

            <v-alert
              v-if="report.last_error"
              type="error"
              variant="tonal"
              density="compact"
              class="mt-3"
            >
              {{ report.last_error }}
            </v-alert>
          </v-card-text>
          <v-divider></v-divider>
          <v-card-actions>
            <v-btn
              color="primary"
              variant="text"
              prepend-icon="mdi-play-circle-outline"
              :loading="report.running"
              :disabled="status.running"
              @click="runNow(report.report_name)"
            >
              立即生成
            </v-btn>
            <v-spacer></v-spacer>
            <v-btn
              variant="text"
              prepend-icon="mdi-eye-outline"
              :disabled="!status.latest[report.report_name]"
              @click="selectedReport = report.report_name"
            >
              查看最近报告
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>

    <!-- 全局状态 + 钉钉推送配置（.env 说明折叠） -->
    <v-card class="mt-4">
      <v-card-title class="text-subtitle-1 font-weight-medium d-flex align-center flex-wrap ga-2">
        <v-icon start>mdi-newspaper-variant-outline</v-icon>
        <span>周期报告</span>
        <v-spacer></v-spacer>
        <v-chip size="small" variant="tonal" :color="enabledCount > 0 ? 'success' : 'grey'">
          已启用 {{ enabledCount }} / {{ reports.length }}
        </v-chip>
        <v-chip size="small" variant="tonal" :color="status.running ? 'info' : 'grey'">
          {{ status.running ? '正在生成' : '空闲' }}
        </v-chip>
        <v-chip
          size="small"
          variant="tonal"
          :color="status.dingtalk_configured ? 'success' : 'warning'"
          prepend-icon="mdi-bell-ring-outline"
        >
          钉钉{{ status.dingtalk_configured ? '已配置' : '未配置' }}
        </v-chip>
      </v-card-title>
      <v-divider></v-divider>
      <v-card-text>
        <div class="d-flex flex-wrap align-center ga-4">
          <v-switch
            v-model="dingtalkEnabled"
            label="钉钉推送（报告 + 仓位保护告警）"
            color="primary"
            inset
            hide-details
            density="compact"
            :disabled="!status.dingtalk_configured || saving"
          ></v-switch>
          <v-spacer></v-spacer>
          <v-btn
            color="primary"
            variant="tonal"
            prepend-icon="mdi-content-save"
            :loading="saving"
            @click="saveConfig"
          >
            保存配置
          </v-btn>
        </div>

        <!-- .env 说明：默认折叠成一行，需要时再展开看 -->
        <v-expansion-panels class="mt-3">
          <v-expansion-panel title="推送配置说明">
            <v-expansion-panel-text>
              <div class="text-caption">
                报告按周期统计热门合约的涨幅榜、放量榜、连涨榜与 RSI 超买超卖，结果同时写入网页日志。
                钉钉推送需要在服务器上 <strong>项目根目录的 <code>.env</code></strong>（与 <code>deploy.sh</code> 同级）中配置
                <code>DINGTALK_WEBHOOK_URL</code> 与（可选）<code>DINGTALK_SECRET</code>，
                改完需重建容器或重启后端；密钥不会写入数据库或日志。
              </div>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import api from '@/services/api'
import { useSnackbarStore } from '@/stores/snackbar'
import { getErrorMessage } from '@/utils/errors'
import { formatUnixSeconds as formatTime } from '@/utils/format'
import SmartSelect from '@/components/SmartSelect.vue'
import type { PeriodicReportConfig, ReportResult, ReportRow, ReportsStatus } from '@/models/types'

const snackbarStore = useSnackbarStore()

const intervalOptions = [
  { title: '每小时', value: '1h' },
  { title: '每 2 小时', value: '2h' },
  { title: '每 4 小时', value: '4h' },
  { title: '每 6 小时', value: '6h' },
  { title: '每 12 小时', value: '12h' },
  { title: '每天', value: '1d' },
]

const status = ref<ReportsStatus>({
  reports: [],
  dingtalk_configured: false,
  dingtalk_enabled: false,
  running: false,
  latest: {},
})
const reports = ref<ReportRow[]>([])
const dingtalkEnabled = ref(false)
const saving = ref(false)
const selectedReport = ref<string>('')
let pollTimer: number | undefined
let initialised = false

const enabledCount = computed(() => reports.value.filter((item) => item.enabled).length)
const latestNames = computed(() => Object.keys(status.value.latest))
const currentLatest = computed<ReportResult | undefined>(() => {
  if (!selectedReport.value) return undefined
  return status.value.latest[selectedReport.value]
})

const toConfig = (row: ReportRow): PeriodicReportConfig => ({
  report_name: row.report_name,
  enabled: row.enabled,
  run_interval: row.run_interval,
  top_n_by_volume: Number(row.top_n_by_volume),
  top_n_gainers: Number(row.top_n_gainers),
  top_n_volume_ratio: Number(row.top_n_volume_ratio),
  min_consecutive_candles: Number(row.min_consecutive_candles),
  volume_ma_period: Number(row.volume_ma_period),
  market_sentiment: {
    enabled: row.market_sentiment?.enabled !== false,
    rsi_period: row.market_sentiment?.rsi_period ?? 14,
    rsi_overbought: row.market_sentiment?.rsi_overbought ?? 70,
    rsi_oversold: row.market_sentiment?.rsi_oversold ?? 30,
  },
})

const applyStatus = (data: ReportsStatus, overwriteForm = false): void => {
  status.value = data
  dingtalkEnabled.value = data.dingtalk_enabled
  if (overwriteForm || !initialised) {
    reports.value = data.reports.map((row) => ({ ...row, market_sentiment: { ...row.market_sentiment } }))
    initialised = true
  } else {
    // 轮询只同步运行态字段，避免覆盖用户正在编辑但未保存的值
    reports.value = reports.value.map((row) => {
      const fresh = data.reports.find((item) => item.report_name === row.report_name)
      return fresh
        ? { ...row, last_run: fresh.last_run, next_run: fresh.next_run, running: fresh.running, last_error: fresh.last_error, scanned: fresh.scanned, title: fresh.title }
        : row
    })
  }
  if (!selectedReport.value && data.reports.length > 0) {
    selectedReport.value = data.reports[0].report_name
  }
}

const fetchStatus = async (overwriteForm = false): Promise<void> => {
  try {
    const response = await api.get<ReportsStatus>('/api/reports')
    applyStatus(response.data, overwriteForm)
  } catch (error: unknown) {
    console.warn('获取周期报告状态失败:', getErrorMessage(error))
  }
}

const saveConfig = async (): Promise<void> => {
  saving.value = true
  try {
    const response = await api.post<ReportsStatus>('/api/reports/config', {
      reports: reports.value.map(toConfig),
      dingtalk_enabled: dingtalkEnabled.value,
    })
    // 保存成功后仍以后端返回为准，保证下次运行时间等信息同步
    initialised = false
    applyStatus(response.data, true)
    snackbarStore.show({ message: '周期报告配置已保存。', color: 'success' })
  } catch (error: unknown) {
    snackbarStore.show({ message: getErrorMessage(error), color: 'error' })
  } finally {
    saving.value = false
  }
}

const runNow = async (reportName: string): Promise<void> => {
  try {
    await api.post('/api/reports/run', { report_name: reportName })
    snackbarStore.show({ message: `已开始生成「${reportName}」，稍候刷新查看。`, color: 'info' })
    await fetchStatus()
  } catch (error: unknown) {
    snackbarStore.show({ message: getErrorMessage(error), color: 'error' })
  }
}

onMounted(async () => {
  await fetchStatus(true)
  pollTimer = window.setInterval(() => {
    void fetchStatus()
  }, 15000)
})

onUnmounted(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = undefined
  }
})
</script>

<style scoped>
/* 手机上让报告切换占满一行，桌面恢复成标题右侧的窄下拉 */
.reports-picker {
  width: 100%;
}
@media (min-width: 960px) {
  .reports-picker {
    width: 260px;
    margin-left: auto;
  }
}
.report-body {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 0.85rem;
  line-height: 1.6;
  margin: 0;
  max-height: 60vh;
  overflow-y: auto;
}
</style>
