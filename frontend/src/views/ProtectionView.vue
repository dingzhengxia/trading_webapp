<!-- frontend/src/views/ProtectionView.vue（仓位保护：monitor 实时风控并入） -->
<template>
  <div>
    <!-- 状态卡 -->
    <v-row>
      <v-col cols="12">
        <v-card>
          <v-card-title class="text-h6 d-flex align-center flex-wrap ga-2">
            <v-icon start>mdi-shield-check-outline</v-icon>
            <span>仓位保护（实时风控）</span>
            <v-spacer></v-spacer>
            <v-chip size="small" variant="tonal" :color="status.running ? 'success' : 'grey'">
              {{ status.running ? '守护中' : '未运行' }}
            </v-chip>
            <v-chip size="small" variant="tonal" :color="status.enabled ? 'success' : 'grey'">
              {{ status.enabled ? '已启用' : '已停用' }}
            </v-chip>
          </v-card-title>
          <v-divider></v-divider>
          <v-card-text>
            <v-row dense align="center">
              <v-col cols="12" md="4">
                <v-switch
                  :model-value="status.enabled"
                  :loading="saving"
                  label="启用仓位保护"
                  color="primary"
                  inset
                  hide-details
                  @update:model-value="onToggleEnabled"
                ></v-switch>
              </v-col>
              <v-col cols="12" md="8">
                <div class="d-flex flex-wrap ga-2">
                  <v-chip size="small" variant="tonal" prepend-icon="mdi-timer-sand">
                    周期: {{ status.timeframe ?? '—' }}
                  </v-chip>
                  <v-chip size="small" variant="tonal" prepend-icon="mdi-account-multiple-check">
                    守卫仓位: {{ status.positions.length }}
                  </v-chip>
                  <v-chip
                    size="small"
                    variant="tonal"
                    prepend-icon="mdi-api"
                    :color="status.api.error_count > 0 ? 'warning' : 'default'"
                  >
                    请求 {{ status.api.request_count }} / 错误 {{ status.api.error_count }}
                  </v-chip>
                  <v-chip
                    size="small"
                    variant="tonal"
                    prepend-icon="mdi-flash-alert"
                    :color="status.api.circuit_open ? 'error' : 'default'"
                  >
                    {{ status.api.circuit_open ? '接口限流熔断中' : '接口正常' }}
                  </v-chip>
                </div>
              </v-col>
            </v-row>
            <v-alert
              v-if="status.last_error"
              type="error"
              variant="tonal"
              density="compact"
              class="mt-3 text-caption"
            >
              最近错误：{{ status.last_error }}
            </v-alert>
            <v-alert type="info" variant="tonal" density="compact" class="mt-3 text-caption">
              <div>· 依据 EMA 结构 + ATR 确认，在每个持仓方向上独立维护 T1/T2/T3 结构减仓、分批止盈（限价 maker）与保护性 STOP 单。</div>
              <div>· 每次「手动平仓 → 重新开仓」都会建立全新风险周期，不会继承旧的 T1/TP 状态。</div>
              <div>· 风控引擎<strong>只会减仓/挂保护单，永远不会开仓</strong>；紧急止损与限价超时兜底会使用市价<strong>平仓</strong>（非开仓）。</div>
            </v-alert>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- 参数卡 -->
    <v-row>
      <v-col cols="12">
        <v-card>
          <v-card-title class="text-subtitle-1 d-flex align-center">
            <v-icon start size="small">mdi-tune</v-icon>
            <span>核心参数</span>
            <v-spacer></v-spacer>
            <v-btn
              size="small"
              color="primary"
              variant="tonal"
              prepend-icon="mdi-content-save"
              :loading="saving"
              @click="saveConfig"
            >
              保存参数
            </v-btn>
          </v-card-title>
          <v-divider></v-divider>
          <v-card-text>
            <v-row dense>
              <v-col cols="12" sm="6" md="3">
                <SmartSelect
                  v-model="form.timeframe"
                  :items="timeframes"
                  label="结构判定周期"
                ></SmartSelect>
              </v-col>
              <v-col cols="12" sm="6" md="3">
                <v-text-field
                  v-model.number="form.tp1_r_multiple"
                  type="number"
                  step="0.1"
                  min="0.1"
                  label="TP1 (R 倍数)"
                  density="compact"
                  variant="outlined"
                  hide-details
                ></v-text-field>
              </v-col>
              <v-col cols="12" sm="6" md="3">
                <v-text-field
                  v-model.number="form.tp2_r_multiple"
                  type="number"
                  step="0.1"
                  min="0.1"
                  label="TP2 (R 倍数)"
                  density="compact"
                  variant="outlined"
                  hide-details
                ></v-text-field>
              </v-col>
              <v-col cols="12" sm="6" md="3">
                <v-text-field
                  v-model.number="form.tp3_r_multiple"
                  type="number"
                  step="0.1"
                  min="0.1"
                  label="躺平 (R 倍数)"
                  density="compact"
                  variant="outlined"
                  hide-details
                ></v-text-field>
              </v-col>
              <v-col cols="12" sm="6" md="3">
                <v-text-field
                  v-model.number="form.t1_structure_lookback"
                  type="number"
                  min="2"
                  label="T1 结构回看(根)"
                  density="compact"
                  variant="outlined"
                  hide-details
                ></v-text-field>
              </v-col>
              <v-col cols="12" sm="6" md="3">
                <v-text-field
                  v-model.number="form.t2_structure_lookback"
                  type="number"
                  min="2"
                  label="T2 结构回看(根)"
                  density="compact"
                  variant="outlined"
                  hide-details
                ></v-text-field>
              </v-col>
              <v-col cols="12" sm="6" md="3">
                <v-text-field
                  v-model.number="form.t3_structure_lookback"
                  type="number"
                  min="2"
                  label="T3 结构回看(根)"
                  density="compact"
                  variant="outlined"
                  hide-details
                ></v-text-field>
              </v-col>
              <v-col cols="12" sm="6" md="3">
                <v-text-field
                  v-model.number="form.structure_buffer_atr"
                  type="number"
                  step="0.1"
                  min="0"
                  label="结构缓冲 (ATR)"
                  density="compact"
                  variant="outlined"
                  hide-details
                ></v-text-field>
              </v-col>
            </v-row>

            <v-row dense class="mt-2">
              <v-col cols="12" sm="6" md="3">
                <v-switch
                  v-model="form.profit_protection_enabled"
                  label="浮盈保护（上移止损）"
                  color="primary"
                  density="compact"
                  inset
                  hide-details
                ></v-switch>
              </v-col>
              <v-col cols="12" sm="6" md="3">
                <v-switch
                  v-model="form.emergency_enabled"
                  label="紧急结构止损"
                  color="primary"
                  density="compact"
                  inset
                  hide-details
                ></v-switch>
              </v-col>
              <v-col cols="12" sm="6" md="3">
                <v-switch
                  v-model="form.exchange_hard_stop_enabled"
                  label="交易所灾难止损单"
                  color="primary"
                  density="compact"
                  inset
                  hide-details
                ></v-switch>
              </v-col>
              <v-col cols="12" sm="6" md="3">
                <v-text-field
                  v-model.number="form.hard_stop_min_distance_pct"
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  label="灾难止损最小距离 (比例)"
                  density="compact"
                  variant="outlined"
                  hide-details
                ></v-text-field>
              </v-col>
            </v-row>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- 守卫中的仓位 -->
    <v-row>
      <v-col cols="12">
        <v-card>
          <v-card-title class="text-subtitle-1 d-flex align-center">
            <v-icon start size="small">mdi-shield-account</v-icon>
            <span>守卫中的仓位（{{ status.positions.length }}）</span>
            <v-spacer></v-spacer>
            <v-btn size="small" variant="text" prepend-icon="mdi-refresh" @click="fetchStatus">
              刷新
            </v-btn>
          </v-card-title>
          <v-divider></v-divider>
          <v-card-text>
            <v-alert
              v-if="!status.enabled"
              type="warning"
              variant="tonal"
              density="compact"
              class="text-caption"
            >
              仓位保护当前未启用：打开上方开关后，引擎才会开始轮询持仓并挂保护单。
            </v-alert>
            <v-table v-else-if="status.positions.length > 0" density="compact">
              <thead>
                <tr>
                  <th class="text-left">币种</th>
                  <th class="text-left">方向</th>
                  <th class="text-right">数量</th>
                  <th class="text-right">开仓价</th>
                  <th class="text-right">标记价</th>
                  <th class="text-right">保护止损</th>
                  <th class="text-right">TP1 / TP2 / 躺平</th>
                  <th class="text-left">已触发</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in status.positions" :key="`${row.symbol}-${row.side}`">
                  <td class="font-weight-medium">{{ row.symbol }}</td>
                  <td>
                    <v-chip
                      size="x-small"
                      variant="tonal"
                      :color="row.side === 'long' ? 'success' : 'error'"
                    >
                      {{ row.side === 'long' ? '多' : '空' }}
                    </v-chip>
                  </td>
                  <td class="text-right">{{ formatNumber(row.contracts, 4) }}</td>
                  <td class="text-right">{{ formatNumber(row.entry_price) }}</td>
                  <td class="text-right">{{ formatNumber(row.mark_price) }}</td>
                  <td class="text-right">
                    <span v-if="row.protected_stop">{{ formatNumber(row.protected_stop) }}</span>
                    <span v-else-if="row.stop_price">{{ formatNumber(row.stop_price) }}</span>
                    <span v-else class="text-grey">—</span>
                  </td>
                  <td class="text-right text-caption">
                    {{ formatNumber(row.tp1_price) }} / {{ formatNumber(row.tp2_price) }} /
                    {{ formatNumber(row.tp3_price) }}
                  </td>
                  <td>
                    <div class="d-flex flex-wrap ga-1">
                      <v-chip v-if="row.tp1_done" size="x-small" variant="tonal" color="info">TP1</v-chip>
                      <v-chip v-if="row.tp2_done" size="x-small" variant="tonal" color="info">TP2</v-chip>
                      <v-chip v-if="row.tp3_done" size="x-small" variant="tonal" color="info">躺平</v-chip>
                      <v-chip v-if="row.t1_done" size="x-small" variant="tonal" color="warning">T1</v-chip>
                      <v-chip v-if="row.t2_done" size="x-small" variant="tonal" color="warning">T2</v-chip>
                      <v-chip v-if="row.t3_done" size="x-small" variant="tonal" color="warning">T3</v-chip>
                      <span
                        v-if="!hasTriggered(row)"
                        class="text-caption text-grey"
                      >等待触发</span>
                    </div>
                  </td>
                </tr>
              </tbody>
            </v-table>
            <div v-else class="text-caption text-grey">
              当前没有持仓，引擎处于待机巡检状态。
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import api from '@/services/api'
import { useSnackbarStore } from '@/stores/snackbar'
import { getErrorMessage } from '@/utils/errors'
import { formatNumberOrDash as formatNumber } from '@/utils/format'
import SmartSelect from '@/components/SmartSelect.vue'
import type { ProtectionConfig, ProtectionPositionRow, ProtectionStatus } from '@/models/types'

const snackbarStore = useSnackbarStore()

const timeframes = ['15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d']

const emptyStatus = (): ProtectionStatus => ({
  enabled: false,
  running: false,
  started_at: null,
  last_error: null,
  timeframe: null,
  positions: [],
  api: {
    request_count: 0,
    error_count: 0,
    failures: 0,
    circuit_open: false,
    circuit_open_until: 0,
    cooldown_until: 0,
  },
  config: {} as ProtectionConfig,
})

const status = ref<ProtectionStatus>(emptyStatus())
const saving = ref(false)
const form = reactive({
  timeframe: '2h',
  tp1_r_multiple: 1,
  tp2_r_multiple: 2,
  tp3_r_multiple: 3,
  t1_structure_lookback: 7,
  t2_structure_lookback: 26,
  t3_structure_lookback: 83,
  structure_buffer_atr: 0.5,
  profit_protection_enabled: true,
  emergency_enabled: true,
  exchange_hard_stop_enabled: true,
  hard_stop_min_distance_pct: 0.05,
})

let pollTimer: number | undefined

const hasTriggered = (row: ProtectionPositionRow): boolean =>
  row.tp1_done || row.tp2_done || row.tp3_done || row.t1_done || row.t2_done || row.t3_done

const applyConfig = (config: Partial<ProtectionConfig>): void => {
  if (typeof config.timeframe === 'string') form.timeframe = config.timeframe
  for (const key of [
    'tp1_r_multiple',
    'tp2_r_multiple',
    'tp3_r_multiple',
    't1_structure_lookback',
    't2_structure_lookback',
    't3_structure_lookback',
    'structure_buffer_atr',
    'hard_stop_min_distance_pct',
  ] as const) {
    const value = Number(config[key])
    if (Number.isFinite(value)) form[key] = value
  }
  for (const key of [
    'profit_protection_enabled',
    'emergency_enabled',
    'exchange_hard_stop_enabled',
  ] as const) {
    if (typeof config[key] === 'boolean') form[key] = config[key] as boolean
  }
}

const fetchStatus = async (): Promise<void> => {
  try {
    const response = await api.get<ProtectionStatus>('/api/protection')
    status.value = response.data
    applyConfig(response.data.config ?? {})
  } catch (error: unknown) {
    console.warn('获取仓位保护状态失败:', getErrorMessage(error))
  }
}

const saveConfig = async (): Promise<void> => {
  saving.value = true
  try {
    await api.post('/api/protection/config', { ...form })
    snackbarStore.show({ message: '仓位保护参数已保存并生效。', color: 'success' })
    await fetchStatus()
  } catch (error: unknown) {
    snackbarStore.show({ message: getErrorMessage(error), color: 'error' })
  } finally {
    saving.value = false
  }
}

const onToggleEnabled = async (value: boolean | null): Promise<void> => {
  saving.value = true
  try {
    await api.post('/api/protection/config', { enabled: value === true })
    snackbarStore.show({
      message: value ? '仓位保护已启用，引擎将在数秒内启动。' : '仓位保护已停用。',
      color: 'success',
    })
    await fetchStatus()
  } catch (error: unknown) {
    snackbarStore.show({ message: getErrorMessage(error), color: 'error' })
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await fetchStatus()
  pollTimer = window.setInterval(() => {
    void fetchStatus()
  }, 10000)
})

onUnmounted(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = undefined
  }
})
</script>
