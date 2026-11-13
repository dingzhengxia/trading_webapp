<!-- frontend/src/components/protection/ConfigForm.vue -->
<!-- 参数设置：控件收进两组折叠面板（分档参数 / 执行开关），标题行带当前值摘要。
     保存只允许走 useProtectionConfig.saveConfig（配置域唯一写路径）。 -->
<template>
  <PageCard icon="mdi-tune" title="参数设置" spaced>
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

    <v-expansion-panels>
      <!-- 组 1：分档参数（结构 + ATR 四档） -->
      <v-expansion-panel>
        <v-expansion-panel-title>
          <div class="d-flex flex-wrap align-baseline ga-2">
            <span class="text-subtitle-2 font-weight-medium">分档参数</span>
            <span class="text-caption text-medium-emphasis">{{ tierSummary }}</span>
          </div>
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <v-row dense>
            <v-col cols="12" sm="6" md="3">
              <SmartSelect
                v-model="form.v2_timeframe"
                :items="timeframes"
                label="结构判定周期"
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
        </v-expansion-panel-text>
      </v-expansion-panel>

      <!-- 组 2：执行开关（浮盈保护 · 紧急止损 · 灾难止损 · 双轨治理 · 连续追踪） -->
      <v-expansion-panel>
        <v-expansion-panel-title>
          <div class="d-flex flex-wrap align-baseline ga-2">
            <span class="text-subtitle-2 font-weight-medium">执行开关</span>
            <span class="text-caption text-medium-emphasis">{{ switchSummary }}</span>
          </div>
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <v-row dense>
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
          <v-row dense class="mt-1">
            <v-col cols="12" sm="6" md="3">
              <v-switch
                v-model="form.take_over_external_stops"
                label="接管开仓端止盈止损"
                color="primary"
                density="compact"
                inset
                hide-details
              ></v-switch>
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <v-switch
                :model-value="form.trailing_stop_mode === 'continuous'"
                label="连续移动止损"
                color="primary"
                density="compact"
                inset
                hide-details
                @update:model-value="form.trailing_stop_mode = $event ? 'continuous' : 'step'"
              ></v-switch>
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <v-text-field
                v-model.number="form.trailing_trigger_r"
                type="number"
                step="0.1"
                min="0.1"
                max="100"
                label="连续追踪触发 (R)"
                density="compact"
                variant="outlined"
                hide-details
              ></v-text-field>
            </v-col>
          </v-row>
          <v-alert type="info" variant="tonal" density="compact" class="mt-3 text-caption">
            接管开仓端止盈止损：开启后守护引擎会撤销开仓时挂的固定 SL/TP/TS 单（先确认自己的保护 STOP
            已就位才撤，绝不裸仓），止盈止损由守护引擎独家管理。连续移动止损：浮盈达到触发 R
            倍数后，止损线按 价格 ± ATR×倍数 平滑追踪（只在盈利方向推进）。
          </v-alert>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>
  </PageCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useProtectionConfig } from '@/composables/useProtectionConfig'
import SmartSelect from '@/components/SmartSelect.vue'
import PageCard from '@/components/PageCard.vue'

const { form, saving, saveConfig } = useProtectionConfig()

const timeframes = ['15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d']

// ---- 折叠面板标题行的当前值摘要（收起状态也能读到关键值） ----
const onOff = (value: boolean): string => (value ? '开' : '关')
const tierSummary = computed(
  () =>
    `风险 ${form.risk_min_pct}–${form.risk_max_pct} / 追踪 ${form.trailing_atr_mult} ATR / 巡检 ${form.v2_poll_interval_sec}s`,
)
const switchSummary = computed(
  () =>
    `浮盈保护 ${onOff(form.profit_protection_enabled)} / 紧急止损 ${onOff(form.emergency_enabled)} / ` +
    `灾难止损 ${onOff(form.exchange_hard_stop_enabled)} / 接管外部止盈止损 ${onOff(form.take_over_external_stops)} / ` +
    `连续移动止损 ${form.trailing_stop_mode === 'continuous' ? '开' : '关'}`,
)
</script>
