<!-- frontend/src/components/protection/ConfigForm.vue -->
<!-- 参数设置：控件收进两组折叠面板（分档参数 / 执行开关），标题行带当前值摘要。
     保存只允许走 useProtectionConfig.saveConfig（配置域唯一写路径）。 -->
<template>
  <PageCard icon="mdi-tune" title="参数设置" spaced>
    <template #badges>
      <v-btn v-if="isDirty" size="small" variant="text" :disabled="saving" @click="revertChanges">
        撤销
      </v-btn>
      <HelpTip v-if="isDirty" :text="HELP.protection.revertBtn" />
      <v-btn
        size="small"
        :color="isDirty ? 'warning' : 'primary'"
        variant="tonal"
        prepend-icon="mdi-content-save"
        :loading="saving"
        @click="saveConfig"
      >
        {{ isDirty ? `保存参数（${dirtyKeys.length} 项未保存）` : '保存参数' }}
      </v-btn>
      <HelpTip :text="HELP.protection.saveBtn" />
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
                :help="HELP.protection.v2Timeframe"
              ></SmartSelect>
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <SmartSelect
                v-model="form.emergency_timeframe"
                :items="timeframes"
                label="黑天鹅判定周期"
                :help="HELP.protection.emergencyTimeframe"
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
              >
                <template #append-inner>
                  <HelpTip :text="HELP.protection.riskMinPct" />
                </template>
              </v-text-field>
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <v-text-field
                v-model.number="form.risk_max_pct"
                type="number"
                step="0.01"
                min="0.001"
                max="0.5"
                label="单笔最大亏损（灾难线）"
                density="compact"
                variant="outlined"
                hide-details
              >
                <template #append-inner>
                  <HelpTip :text="HELP.protection.riskMaxPct" />
                </template>
              </v-text-field>
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <v-text-field
                v-model.number="form.t1_max_pct"
                type="number"
                step="0.005"
                min="0.005"
                max="0.5"
                label="T1 最远距离（结构位封顶）"
                density="compact"
                variant="outlined"
                hide-details
              >
                <template #append-inner>
                  <HelpTip :text="HELP.protection.t1MaxPct" />
                </template>
              </v-text-field>
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
              >
                <template #append-inner>
                  <HelpTip :text="HELP.protection.tierRatios" />
                </template>
              </v-text-field>
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
              >
                <template #append-inner>
                  <HelpTip :text="HELP.protection.tierConfirmSec" />
                </template>
              </v-text-field>
            </v-col>
          </v-row>
          <v-row dense class="mt-1">
            <v-col cols="12" sm="6" md="3">
              <v-text-field
                v-model.number="form.breakeven_trigger_atr"
                type="number"
                step="0.5"
                min="0.2"
                max="20"
                label="保本触发（ATR 倍数）"
                density="compact"
                variant="outlined"
                hide-details
              >
                <template #append-inner>
                  <HelpTip :text="HELP.protection.breakevenTriggerAtr" />
                </template>
              </v-text-field>
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <v-text-field
                v-model.number="form.breakeven_atr_ratio"
                type="number"
                step="0.1"
                min="0"
                max="5"
                label="保本位缓冲（ATR 倍数）"
                density="compact"
                variant="outlined"
                hide-details
              >
                <template #append-inner>
                  <HelpTip :text="HELP.protection.breakevenAtrRatio" />
                </template>
              </v-text-field>
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <v-text-field
                v-model.number="form.trailing_start_atr"
                type="number"
                step="0.5"
                min="0.2"
                max="20"
                label="追踪起点（ATR 倍数）"
                density="compact"
                variant="outlined"
                hide-details
              >
                <template #append-inner>
                  <HelpTip :text="HELP.protection.trailingStartAtr" />
                </template>
              </v-text-field>
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <v-text-field
                v-model.number="form.trailing_atr_mult"
                type="number"
                step="0.5"
                min="0.5"
                max="20"
                label="追踪宽度（ATR 倍数）"
                density="compact"
                variant="outlined"
                hide-details
              >
                <template #append-inner>
                  <HelpTip :text="HELP.protection.trailingAtrMult" />
                </template>
              </v-text-field>
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
              >
                <template #append-inner>
                  <HelpTip :text="HELP.protection.pollInterval" />
                </template>
              </v-text-field>
            </v-col>
          </v-row>
          <v-alert type="info" variant="tonal" density="compact" class="mt-3 text-caption">
            <strong>四档怎么算：</strong>T1 = 最近的结构低点再往外 0.5×ATR（夹在「最小风险」与「T1
            最远距离」之间），T2/T3/T4 = T1 到灾难线之间的 25/50/75% 等距。
            灾难线就是「单笔最大亏损」，不再由 T4 再外推——旧口径会把兜底线推到 −11%。
            T4 允许清仓（结构彻底失效），T1~T3 至少留 10% 给后面的档。
            交易所 STOP 只做兜底；减一档，止损就推进到下一档。
          </v-alert>
        </v-expansion-panel-text>
      </v-expansion-panel>

      <!-- 组 2：止盈阶梯（R 倍数 + 减仓比例 + 保留仓位） -->
      <v-expansion-panel>
        <v-expansion-panel-title>
          <div class="d-flex flex-wrap align-baseline ga-2">
            <span class="text-subtitle-2 font-weight-medium">止盈阶梯</span>
            <HelpTip :text="HELP.protection.switchTpPassive" />
            <span class="text-caption text-medium-emphasis">{{ tpSummary }}</span>
          </div>
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <v-row dense>
            <v-col v-for="(_, i) in 3" :key="`tp-r-${i}`" cols="6" sm="3" md="3">
              <v-text-field
                v-model.number="form.tp_r_multiples[i]"
                type="number"
                step="0.1"
                min="0.1"
                max="50"
                :label="`TP${i + 1} 触发（R）`"
                density="compact"
                variant="outlined"
                hide-details
              >
                <template #append-inner>
                  <HelpTip :text="HELP.protection.tpRMultiple" />
                </template>
              </v-text-field>
            </v-col>
          </v-row>
          <v-row dense class="mt-1">
            <v-col v-for="(_, i) in 3" :key="`tp-ratio-${i}`" cols="6" sm="3" md="3">
              <v-text-field
                v-model.number="form.tp_ratios[i]"
                type="number"
                step="0.05"
                min="0"
                max="1"
                :label="`TP${i + 1} 减仓比例`"
                density="compact"
                variant="outlined"
                hide-details
              >
                <template #append-inner>
                  <HelpTip :text="HELP.protection.tpRatio" />
                </template>
              </v-text-field>
            </v-col>
            <v-col cols="6" sm="3" md="3">
              <v-text-field
                v-model.number="form.tp_keep_ratio"
                type="number"
                step="0.05"
                min="0"
                max="0.9"
                label="保留仓位（追踪）"
                density="compact"
                variant="outlined"
                hide-details
              >
                <template #append-inner>
                  <HelpTip :text="HELP.protection.tpKeepRatio" />
                </template>
              </v-text-field>
            </v-col>
            <v-col cols="6" sm="3" md="3">
              <v-text-field
                v-model.number="form.tp_breakout_confirm_pct"
                type="number"
                step="0.001"
                min="0"
                max="0.02"
                label="突破确认（0.001=0.1%）"
                density="compact"
                variant="outlined"
                hide-details
              >
                <template #append-inner>
                  <HelpTip :text="HELP.protection.tpBreakoutConfirm" />
                </template>
              </v-text-field>
            </v-col>
          </v-row>
          <v-alert type="info" variant="tonal" density="compact" class="mt-3 text-caption">
            <strong>止盈由引擎判断：先突破，再回落才卖。</strong>
            引擎每 3 秒核对一次价格：只有真正越过目标价（含「突破确认」缓冲）才算突破，
            之后价格回到目标价才分批卖出——插针碰到目标价不会成交，也不会把单子挂在交易所等撮合。
            一次只卖当前一档，后面的档位要自己重新突破。执行复用保护性减仓通道（reduceOnly）。
          </v-alert>
        </v-expansion-panel-text>
      </v-expansion-panel>

      <!-- 组 3：执行开关（浮盈保护 · 紧急止损 · 灾难止损 · 双轨治理 · 连续追踪） -->
      <v-expansion-panel>
        <v-expansion-panel-title>
          <div class="d-flex flex-wrap align-baseline ga-2">
            <span class="text-subtitle-2 font-weight-medium">执行开关</span>
            <span class="text-caption text-medium-emphasis">{{ switchSummary }}</span>
          </div>
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <!-- 四个二值开关：改动即写入（不等「保存参数」），否则下次 10s 轮询会把值刷回旧状态 -->
          <v-row dense>
            <v-col v-for="sw in booleanSwitches" :key="sw.key" cols="12" sm="6" md="3">
              <v-switch
                :model-value="form[sw.key]"
                color="primary"
                density="compact"
                inset
                hide-details
                @update:model-value="onBooleanSwitch(sw.key, $event)"
              >
                <template #label> {{ sw.label }}<HelpTip :text="sw.help" /> </template>
              </v-switch>
            </v-col>
          </v-row>
          <v-row dense class="mt-1">
            <v-col cols="12" sm="6" md="3">
              <v-text-field
                v-model.number="form.emergency_cooldown_sec"
                type="number"
                step="60"
                min="0"
                max="86400"
                label="黑天鹅后冷却（秒）"
                density="compact"
                variant="outlined"
                hide-details
              >
                <template #append-inner>
                  <HelpTip :text="HELP.protection.emergencyCooldown" />
                </template>
              </v-text-field>
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
              >
                <template #append-inner>
                  <HelpTip :text="HELP.protection.hardStopMinDistance" />
                </template>
              </v-text-field>
            </v-col>
          </v-row>
          <v-alert type="info" variant="tonal" density="compact" class="mt-3 text-caption">
            开关改动立即生效；数值参数改动后需点右上角「保存参数」。
            接管开仓端止盈止损：开启后守护引擎会撤销开仓时挂的固定 SL/TP/TS 单（先确认自己的保护
            STOP 已就位才撤，绝不裸仓），止盈止损由守护引擎独家管理。
            止损阶梯全部按 ATR 计：浮盈 2 ATR 推到成本价、2.5 ATR 起按「峰值 − 1.5 ATR」跟随。
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
import HelpTip from '@/components/HelpTip.vue'
import { HELP } from '@/config/help'

const { form, saving, isDirty, dirtyKeys, saveConfig, applySwitch, revertChanges } =
  useProtectionConfig()

const timeframes = ['15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d']

/** 五个布尔型执行开关：绑定同名配置字段，改动即 patch 落库 */
const booleanSwitches = [
  {
    key: 'profit_protection_enabled',
    label: '浮盈保护（上移止损）',
    help: HELP.protection.switchProfitProtection,
  },
  {
    key: 'emergency_enabled',
    label: '紧急结构止损',
    help: HELP.protection.switchEmergency,
  },
  {
    key: 'exchange_hard_stop_enabled',
    label: '交易所灾难止损单',
    help: HELP.protection.switchExchangeHardStop,
  },
  {
    key: 'take_over_external_stops',
    label: '接管开仓端止盈止损',
    help: HELP.protection.switchTakeOver,
  },
  {
    key: 'emergency_block_new_entries',
    label: '黑天鹅期间禁止开仓',
    help: HELP.protection.switchBlockEntries,
  },
] as const

type BooleanSwitchKey = (typeof booleanSwitches)[number]['key']

const onBooleanSwitch = (key: BooleanSwitchKey, value: boolean | null): void => {
  void applySwitch(key, value === true)
}

// ---- 折叠面板标题行的当前值摘要（收起状态也能读到关键值） ----
const onOff = (value: boolean): string => (value ? '开' : '关')
const pct = (value: number): string => `${Math.round(value * 100)}%`
const tierSummary = computed(
  () =>
    `T1 风险 ${pct(form.risk_min_pct)}–${pct(form.t1_max_pct)} / 亏损上限 ${pct(form.risk_max_pct)} / ` +
    `保本 ${form.breakeven_trigger_atr} ATR / 追踪 ${form.trailing_atr_mult} ATR / ` +
    `黑天鹅 ${form.emergency_timeframe} / 巡检 ${form.v2_poll_interval_sec}s`,
)
const switchSummary = computed(
  () =>
    `浮盈保护 ${onOff(form.profit_protection_enabled)} / 紧急止损 ${onOff(form.emergency_enabled)} / ` +
    `灾难止损 ${onOff(form.exchange_hard_stop_enabled)} / 接管外部止盈止损 ${onOff(form.take_over_external_stops)} / ` +
    `黑天鹅禁开仓 ${onOff(form.emergency_block_new_entries)}`,
)
const tpSummary = computed(() => {
  const r = form.tp_r_multiples.map((x) => `${x}R`).join(' / ')
  return `${r} 减 ${form.tp_ratios.map(pct).join(' / ')}，保留 ${pct(form.tp_keep_ratio)} 追踪`
})
</script>
