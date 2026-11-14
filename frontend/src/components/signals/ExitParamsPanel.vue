<!-- frontend/src/components/signals/ExitParamsPanel.vue -->
<!-- 出场规则（参数类，规格 A10 拆分）：出场模式、纸面/实盘共用的出场参数、
     实盘超时平仓与止损巡检开关。放在 ConfigDrawer 的 exit Tab；查看类数据见 PaperTrackingPanel -->
<template>
  <div>
    <SectionHeader
      icon="mdi-chart-timeline-variant"
      title="出场层"
      description="实盘条件单与纸面模拟共用同一份价格计算"
    >
      <v-chip size="x-small" variant="tonal" :color="paperEnabled ? 'success' : 'grey'">
        {{ paperEnabled ? '纸面跟踪中' : '纸面未启用' }}
      </v-chip>
      <v-chip size="x-small" variant="tonal" :color="liveExit.enabled ? 'warning' : 'grey'">
        {{ liveExit.enabled ? '实盘超时平仓' : '实盘不超时' }}
      </v-chip>
    </SectionHeader>

    <v-alert type="info" variant="tonal" density="compact" class="mb-4 text-caption">
      止盈止损价格由 <code>core/exit_rules.py</code> 统一计算：实盘条件单和纸面模拟读同一份实现，
      改一个参数两边同时改。ATR 口径会真实改变实盘挂单（拿不到 ATR 时自动回退百分比）。
    </v-alert>

    <v-btn-toggle
      :model-value="exitMode"
      mandatory
      divided
      density="compact"
      variant="outlined"
      class="mb-2"
      @update:model-value="emit('change-mode', $event)"
    >
      <v-btn value="percent" size="small">百分比（现设）</v-btn>
      <v-btn value="atr" size="small">ATR 止损</v-btn>
    </v-btn-toggle>
    <HelpTip :text="HELP.signals.exitMode" />
    <p class="text-caption text-medium-emphasis mb-4">
      {{
        exitMode === 'percent'
          ? '价格距离 = 设置页的保证金百分比 ÷ 杠杆；实盘条件单与纸面模拟用的是同一套价格。'
          : '止损 = N × ATR，止盈 = R × 止损距离；实盘条件单也按这个挂，拿不到 ATR 时回退百分比。'
      }}
    </p>

    <v-row dense align="center">
      <v-col cols="12" sm="6" md="3">
        <v-switch
          :model-value="paperEnabled"
          :loading="savingPaperToggle"
          color="primary"
          hide-details
          @update:model-value="emit('toggle-paper', $event)"
        >
          <template #label>
            启用纸面跟踪<HelpTip :text="HELP.signals.paperSwitch" />
          </template>
        </v-switch>
      </v-col>
      <v-col cols="6" sm="3" md="2">
        <v-text-field
          v-model.number="paperForm.slAtr"
          label="止损 (ATR 倍数)"
          type="number"
          min="0.2"
          max="10"
          step="0.1"
          :disabled="exitMode !== 'atr'"
          @update:model-value="emit('dirty')"
        >
          <template #append-inner>
            <HelpTip :text="HELP.signals.slAtr" />
          </template>
        </v-text-field>
      </v-col>
      <v-col cols="6" sm="3" md="2">
        <v-text-field
          v-model.number="paperForm.tpR"
          label="止盈 (R 倍数)"
          type="number"
          min="0.5"
          max="10"
          step="0.5"
          :disabled="exitMode !== 'atr'"
          @update:model-value="emit('dirty')"
        >
          <template #append-inner>
            <HelpTip :text="HELP.signals.tpR" />
          </template>
        </v-text-field>
      </v-col>
      <v-col cols="6" sm="3" md="2">
        <v-text-field
          v-model.number="paperForm.maxBars"
          label="最大持有 (根)"
          type="number"
          min="1"
          max="100"
          @update:model-value="emit('dirty')"
        >
          <template #append-inner>
            <HelpTip :text="HELP.signals.maxBars" />
          </template>
        </v-text-field>
      </v-col>
      <v-col cols="6" sm="3" md="3">
        <v-btn
          color="primary"
          variant="tonal"
          prepend-icon="mdi-content-save"
          :loading="savingPaperConfig"
          :disabled="!valid || savingPaperConfig"
          block
          @click="emit('save-paper')"
        >
          保存参数
        </v-btn>
        <HelpTip :text="HELP.signals.savePaperBtn" />
      </v-col>
    </v-row>

    <v-divider class="my-4" />

    <v-row dense align="center">
      <v-col cols="12" sm="6" md="3">
        <v-select
          v-model="paperForm.atrTimeframe"
          :items="atrTimeframes"
          label="实盘 ATR 周期"
          :disabled="exitMode !== 'atr'"
          hide-details
          @update:model-value="emit('dirty')"
        >
          <template #append-inner>
            <HelpTip :text="HELP.signals.atrTimeframe" />
          </template>
        </v-select>
      </v-col>
      <v-col cols="12" sm="6" md="4">
        <v-switch
          :model-value="liveExit.enabled"
          :loading="savingLiveTimeout"
          color="warning"
          hide-details
          @update:model-value="emit('toggle-live-timeout', $event)"
        >
          <template #label>
            实盘超时平仓<HelpTip :text="HELP.signals.liveTimeoutSwitch" />
          </template>
        </v-switch>
      </v-col>
      <v-col cols="12" md="5" class="text-caption text-medium-emphasis">
        持有满「最大持有」根就市价平掉信号自动开的仓；手动仓不动。
      </v-col>

      <v-col cols="12" sm="6" md="4" class="mt-2">
        <v-switch
          :model-value="liveExit.guard_enabled"
          :loading="savingSltpGuard"
          color="success"
          hide-details
          @update:model-value="emit('toggle-sltp-guard', $event)"
        >
          <template #label>
            止损巡检（缺单自动补挂）<HelpTip :text="HELP.signals.sltpGuardSwitch" />
          </template>
        </v-switch>
      </v-col>
      <v-col cols="12" md="8" class="text-caption text-medium-emphasis mt-2">
        每 5 分钟核对所有持仓（手动与自动都算）：没有止损单就按当前口径补挂；只补挂、不平仓。
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import SectionHeader from '@/components/SectionHeader.vue'
import HelpTip from '@/components/HelpTip.vue'
import { HELP } from '@/config/help'
import type { LiveExitStatus } from '@/models/types'

export interface PaperForm {
  slAtr: number
  tpR: number
  maxBars: number
  atrTimeframe: string
}

const props = withDefaults(
  defineProps<{
    exitMode: string
    paperForm: PaperForm
    /** 纸面跟踪开关状态（数据归 SignalsView 管，这里只读） */
    paperEnabled: boolean
    liveExit: LiveExitStatus
    atrTimeframes: string[]
    valid: boolean
    savingPaperConfig?: boolean
    savingPaperToggle?: boolean
    savingLiveTimeout?: boolean
    savingSltpGuard?: boolean
  }>(),
  {
    savingPaperConfig: false,
    savingPaperToggle: false,
    savingLiveTimeout: false,
    savingSltpGuard: false,
  },
)

const paperForm = props.paperForm

const emit = defineEmits<{
  (e: 'change-mode', value: unknown): void
  (e: 'toggle-paper', value: unknown): void
  (e: 'save-paper'): void
  (e: 'toggle-live-timeout', value: unknown): void
  (e: 'toggle-sltp-guard', value: unknown): void
  (e: 'dirty'): void
}>()
</script>
