<!-- frontend/src/views/ProtectionView.vue（仓位保护：monitor 实时风控并入） -->
<template>
  <div>
    <!-- 状态卡 -->
    <PageCard icon="mdi-shield-check-outline" title="仓位保护（实时风控）" :error="status.last_error">
      <template #badges>
        <v-chip size="small" variant="tonal" :color="status.running ? 'success' : 'grey'">
          {{ status.running ? '守护中' : '未运行' }}
        </v-chip>
        <v-chip size="small" variant="tonal" :color="status.enabled ? 'success' : 'grey'">
          {{ status.enabled ? '已启用' : '已停用' }}
        </v-chip>
        <v-chip size="small" variant="tonal" :color="isV2 ? 'primary' : 'grey'">
          {{ isV2 ? 'v2 引擎' : 'v1 引擎' }}
        </v-chip>
        <v-chip v-if="isV2 && status.v2?.dry_run" size="small" variant="tonal" color="warning">
          演练模式
        </v-chip>
      </template>
      <v-row dense align="center">
        <v-col cols="12" md="3">
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
        <v-col v-if="isV2" cols="12" md="3">
          <v-switch
            :model-value="Boolean(form.dry_run)"
            :loading="saving"
            label="演练模式（只记录不下单）"
            color="warning"
            inset
            hide-details
            @update:model-value="onToggleDryRun"
          ></v-switch>
        </v-col>
        <v-col cols="12" :md="isV2 ? 6 : 9">
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
      <v-alert type="info" variant="tonal" density="compact" class="mt-3 text-caption">
        <div>· 依据 EMA 结构 + ATR 确认，在每个持仓方向上独立维护 T1/T2/T3 结构减仓、分批止盈（限价 maker）与保护性 STOP 单。</div>
        <div>· 每次「手动平仓 → 重新开仓」都会建立全新风险周期，不会继承旧的 T1/TP 状态。</div>
        <div>· 风控引擎<strong>只会减仓/挂保护单，永远不会开仓</strong>；紧急止损与限价超时兜底会使用市价<strong>平仓</strong>（非开仓）。</div>
      </v-alert>
    </PageCard>

    <!-- 参数卡 -->
    <!-- 参数卡 -->
    <PageCard icon="mdi-tune" title="核心参数" spaced>
      <template #badges>
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
      </template>
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
    </PageCard>

    <!-- v2 分档参数（结构 + ATR 四档） -->
    <PageCard icon="mdi-layers-triple-outline" title="v2 分档参数（结构 + ATR）" spaced>
      <template #badges>
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
      </template>
      <v-row dense>
        <v-col cols="12" sm="6" md="3">
          <SmartSelect
            v-model="form.engine_version"
            :items="engineVersions"
            label="风控引擎版本"
          ></SmartSelect>
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <SmartSelect
            v-model="form.v2_timeframe"
            :items="timeframes"
            label="v2 结构判定周期"
          ></SmartSelect>
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <v-text-field
            v-model.number="form.risk_min_pct"
            type="number"
            step="0.005"
            min="0.001"
            max="0.5"
            label="最小单笔风险（占价格比例）"
            density="compact"
            variant="outlined"
            hide-details
          ></v-text-field>
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <v-text-field
            v-model.number="form.risk_max_pct"
            type="number"
            step="0.01"
            min="0.001"
            max="0.5"
            label="最大单笔风险（占价格比例）"
            density="compact"
            variant="outlined"
            hide-details
          ></v-text-field>
        </v-col>
      </v-row>
      <v-row dense class="mt-1">
        <v-col v-for="(_, i) in 4" :key="`tier-${i}`" cols="6" sm="3" md="3">
          <v-text-field
            v-model.number="form.tier_ratios[i]"
            type="number"
            step="0.05"
            min="0"
            max="1"
            :label="`T${i + 1} 减仓比例${i === 3 ? '（全平档）' : ''}`"
            density="compact"
            variant="outlined"
            hide-details
          ></v-text-field>
        </v-col>
      </v-row>
      <v-row dense class="mt-1">
        <v-col v-for="(_, i) in 4" :key="`confirm-${i}`" cols="6" sm="3" md="3">
          <v-text-field
            v-model.number="form.tier_confirm_sec[i]"
            type="number"
            step="5"
            min="0"
            max="600"
            :label="`T${i + 1} 持续确认（秒）`"
            density="compact"
            variant="outlined"
            hide-details
          ></v-text-field>
        </v-col>
      </v-row>
      <v-row dense class="mt-1">
        <v-col cols="12" sm="6" md="3">
          <v-text-field
            v-model.number="form.breakeven_trigger_r"
            type="number"
            step="0.1"
            min="0.1"
            max="100"
            label="保本触发（R）"
            density="compact"
            variant="outlined"
            hide-details
          ></v-text-field>
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <v-text-field
            v-model.number="form.trailing_atr_mult"
            type="number"
            step="0.5"
            min="0.5"
            max="20"
            label="追踪止损（ATR 倍数）"
            density="compact"
            variant="outlined"
            hide-details
          ></v-text-field>
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <v-text-field
            v-model.number="form.v2_poll_interval_sec"
            type="number"
            step="1"
            min="1"
            max="60"
            label="巡检间隔（秒）"
            density="compact"
            variant="outlined"
            hide-details
          ></v-text-field>
        </v-col>
      </v-row>
      <v-alert type="info" variant="tonal" density="compact" class="mt-3 text-caption">
        四档合计应等于 100%：越破越重，T4 为全平档。交易所 STOP 只做兜底（灾难线再往外 1.5 ATR），
        正常情况由这四档先动作；减一档，止损就推进到下一档。
      </v-alert>
    </PageCard>

    <!-- 守卫中的仓位 -->
    <!-- 守卫中的仓位 -->
    <PageCard icon="mdi-shield-account" title="守卫中的仓位" spaced>
      <template #badges>
        <v-chip size="small" variant="tonal">{{ status.positions.length }} 个</v-chip>
        <v-btn size="small" variant="text" prepend-icon="mdi-refresh" @click="fetchStatus">
          刷新
        </v-btn>
      </template>
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
              <th v-if="isV2" class="text-right">四档减仓线</th>
              <th v-if="isV2" class="text-right">灾难线</th>
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
              <td v-if="isV2" class="text-right text-caption">
                <span v-if="row.tier_levels?.length">
                  {{ row.tier_levels.map((v) => formatNumber(v)).join(' / ') }}
                </span>
                <span v-else class="text-grey">—</span>
              </td>
              <td v-if="isV2" class="text-right text-caption">
                <span v-if="row.disaster_stop">{{ formatNumber(row.disaster_stop) }}</span>
                <span v-else class="text-grey">—</span>
              </td>
              <td>
                <div class="d-flex flex-wrap ga-1">
                  <v-chip v-if="row.tp1_done" size="x-small" variant="tonal" color="info">TP1</v-chip>
                  <v-chip v-if="row.tp2_done" size="x-small" variant="tonal" color="info">TP2</v-chip>
                  <v-chip v-if="row.tp3_done" size="x-small" variant="tonal" color="info">躺平</v-chip>
                  <v-chip v-if="row.t1_done" size="x-small" variant="tonal" color="warning">T1</v-chip>
                  <v-chip v-if="row.t2_done" size="x-small" variant="tonal" color="warning">T2</v-chip>
                  <v-chip v-if="row.t3_done" size="x-small" variant="tonal" color="warning">T3</v-chip>
                  <v-chip v-if="row.t4_done" size="x-small" variant="tonal" color="error">T4</v-chip>
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
    </PageCard>

    <!-- v2 动作轨迹：什么时候、因为哪条线、减了多少 -->
    <PageCard v-if="isV2" icon="mdi-history" title="最近保护动作" spaced>
      <template #badges>
        <v-chip size="small" variant="tonal">
          第 {{ status.v2?.cycle_count ?? 0 }} 轮
        </v-chip>
      </template>
      <div v-if="(status.v2?.recent_actions?.length ?? 0) === 0" class="text-caption text-grey">
        最近没有触发减仓/止盈，引擎只在上移止损时保持安静。
      </div>
      <v-list v-else density="compact" lines="one">
        <v-list-item
          v-for="(item, idx) in status.v2?.recent_actions ?? []"
          :key="`${item.ts}-${idx}`"
        >
          <template #prepend>
            <v-icon
              size="16"
              :color="item.level === 'error' ? 'error' : item.level === 'warning' ? 'warning' : 'success'"
            >
              mdi-shield-alert-outline
            </v-icon>
          </template>
          <v-list-item-title class="text-caption">
            {{ new Date(item.ts * 1000).toLocaleTimeString() }} · {{ item.symbol }} · {{ item.text }}
          </v-list-item-title>
        </v-list-item>
      </v-list>
    </PageCard>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import api from '@/services/api'
import { useSnackbarStore } from '@/stores/snackbar'
import { getErrorMessage } from '@/utils/errors'
import { formatNumberOrDash as formatNumber } from '@/utils/format'
import SmartSelect from '@/components/SmartSelect.vue'
import PageCard from '@/components/PageCard.vue'
import type { ProtectionConfig, ProtectionPositionRow, ProtectionStatus } from '@/models/types'

const snackbarStore = useSnackbarStore()

const timeframes = ['15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d']

const engineVersions = [
  { title: 'v2（四档结构 + 一仓一行账本）', value: 'v2' },
  { title: 'v1（旧引擎，仅回滚用）', value: 'v1' },
]

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
  engine_version: 'v2',
  dry_run: false,
  v2_timeframe: '2h',
  v2_poll_interval_sec: 3,
  tier_ratios: [0.15, 0.2, 0.25, 0.4] as number[],
  tier_confirm_sec: [30, 45, 60, 0] as number[],
  risk_min_pct: 0.015,
  risk_max_pct: 0.08,
  breakeven_trigger_r: 0.5,
  trailing_atr_mult: 2.5,
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

const isV2 = computed(() =>
  (status.value.engine_version ?? form.engine_version ?? 'v2') === 'v2',
)

let pollTimer: number | undefined

const hasTriggered = (row: ProtectionPositionRow): boolean =>
  row.tp1_done || row.tp2_done || row.tp3_done ||
  row.t1_done || row.t2_done || row.t3_done || Boolean(row.t4_done)

const applyConfig = (config: Partial<ProtectionConfig>): void => {
  if (typeof config.timeframe === 'string') form.timeframe = config.timeframe
  if (typeof config.engine_version === 'string') {
    form.engine_version = config.engine_version === 'v1' ? 'v1' : 'v2'
  }
  if (typeof config.dry_run === 'boolean') form.dry_run = config.dry_run
  if (typeof config.v2_timeframe === 'string') form.v2_timeframe = config.v2_timeframe
  if (Array.isArray(config.tier_ratios) && config.tier_ratios.length === 4) {
    form.tier_ratios = config.tier_ratios.map((x) => Number(x))
  }
  if (Array.isArray(config.tier_confirm_sec) && config.tier_confirm_sec.length === 4) {
    form.tier_confirm_sec = config.tier_confirm_sec.map((x) => Number(x))
  }
  for (const key of [
    'v2_poll_interval_sec',
    'risk_min_pct',
    'risk_max_pct',
    'breakeven_trigger_r',
    'trailing_atr_mult',
  ] as const) {
    const value = Number(config[key])
    if (Number.isFinite(value)) form[key] = value
  }
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

const onToggleDryRun = async (value: boolean | null): Promise<void> => {
  saving.value = true
  try {
    form.dry_run = value === true
    await api.post('/api/protection/config', { dry_run: value === true })
    snackbarStore.show({
      message: value
        ? '演练模式已开启：引擎照常判断并记录动作，但不会真实下单。'
        : '演练模式已关闭：风控动作将真实执行。',
      color: value ? 'warning' : 'success',
    })
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
