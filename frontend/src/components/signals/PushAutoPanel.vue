<!-- frontend/src/components/signals/PushAutoPanel.vue -->
<!-- 推送与开仓：钉钉推送门槛 + 信号自动开仓参数。全部是「改」的内容，收进 Tab -->
<template>
  <div>
    <SectionHeader
      icon="mdi-bell-ring-outline"
      title="钉钉推送"
      description="门槛只作用于推送，不影响信号列表与自动开仓"
    >
      <v-chip
        size="x-small"
        variant="tonal"
        :color="pushStatus.dingtalk_configured ? 'success' : 'warning'"
      >
        {{ pushStatus.dingtalk_configured ? 'Webhook 已配置' : '未配置 DINGTALK_WEBHOOK_URL' }}
      </v-chip>
    </SectionHeader>

    <v-row dense align="center" class="mt-2">
      <v-col cols="12" sm="6" md="4">
        <v-switch
          :model-value="pushStatus.signal_dingtalk_enabled"
          :loading="savingDingtalkPush"
          :disabled="!pushStatus.dingtalk_configured || !pushStatus.dingtalk_enabled"
          label="币种信号推送"
          color="primary"
          hide-details
          @update:model-value="emit('toggle-dingtalk', $event)"
        />
      </v-col>
      <v-col cols="8" sm="4" md="3">
        <!-- 说明放小节标题里，这里只留一个不带浮动标签的小输入框，
             避免窄列下 outlined 的缺口放不下长标签 -->
        <v-text-field
          :model-value="pushVolumeInput"
          type="number"
          min="0"
          max="100"
          step="0.5"
          prefix="×"
          aria-label="量能倍数门槛"
          hint="量能倍数"
          persistent-hint
          @update:model-value="emit('update:pushVolumeInput', Number($event))"
        />
      </v-col>
      <v-col cols="4" sm="2" md="2">
        <v-btn
          color="primary"
          variant="tonal"
          prepend-icon="mdi-content-save"
          :loading="savingPushConfig"
          :disabled="!pushVolumeDirty"
          block
          @click="emit('save-volume')"
        >
          保存
        </v-btn>
      </v-col>
      <v-col cols="12" md="3" class="text-caption text-medium-emphasis">
        静态币（{{ pushStatus.static_symbols.join(' / ') || '无' }}）始终推送
      </v-col>
    </v-row>
    <p class="text-caption text-medium-emphasis mt-1 mb-0">
      非静态币需「当前量 ÷ 动态基准 ≥ 量能倍数」才推送；填 0 表示不过滤。
    </p>

    <v-divider class="my-5" />

    <SectionHeader icon="mdi-robot" title="信号自动开仓">
      <span class="text-caption text-medium-emphasis">最近自动开仓：{{ lastAutoOpenText }}</span>
    </SectionHeader>

    <v-alert type="warning" variant="tonal" density="compact" class="mb-4 text-caption">
      <div>· 信号为技术指标信号，不构成收益保证；自动开仓使用限价 post-only 单。</div>
      <div>· 扫描与自动开仓默认关闭，开启后才会请求交易所行情并可能自动开仓。</div>
    </v-alert>

    <v-switch
      :model-value="autoEnabled"
      :loading="savingAutoTrade"
      label="启用自动开仓"
      color="primary"
      hide-details
      class="mb-2"
      @update:model-value="emit('toggle-auto', $event)"
    />

    <v-row dense>
      <v-col cols="12" md="3">
        <SmartSelect
          v-model="autoForm.directions"
          :items="directionOptions"
          item-title="title"
          item-value="value"
          label="允许方向"
          multiple
          @update:model-value="emit('dirty')"
        />
      </v-col>
      <v-col cols="12" md="3">
        <SmartSelect
          v-model="autoForm.timeframes"
          :items="timeframeOptions"
          label="允许周期"
          multiple
          @update:model-value="emit('dirty')"
        />
      </v-col>
      <v-col cols="12" md="6">
        <SmartSelect
          v-model="autoForm.strategies"
          :items="strategyOptions"
          item-title="title"
          item-value="value"
          label="策略白名单"
          multiple
          hint="观望类策略不会自动开仓"
          :hide-details="false"
          @update:model-value="emit('dirty')"
        />
      </v-col>
    </v-row>

    <v-row class="mt-1">
      <v-col v-for="field in numericFields" :key="field.key" cols="6" sm="4" md="4">
        <v-text-field
          v-model.number="autoForm[field.key]"
          :label="field.label"
          type="number"
          :min="field.min"
          hide-details="auto"
          @update:model-value="emit('dirty')"
        />
      </v-col>
    </v-row>

    <div class="d-flex align-center flex-wrap ga-3 mt-4">
      <v-btn
        color="primary"
        variant="tonal"
        prepend-icon="mdi-content-save"
        :loading="savingAuto"
        :disabled="!autoValid || savingAuto"
        @click="emit('save-auto')"
      >
        保存自动开仓配置
      </v-btn>
      <span v-if="!autoValid" class="text-caption text-error">
        方向 / 策略 / 周期至少各选一项，数字参数需大于 0
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import SectionHeader from '@/components/SectionHeader.vue'
import SmartSelect from '@/components/SmartSelect.vue'
import type { SignalPushStatus } from '@/models/types'

export interface AutoTradeForm {
  directions: string[]
  strategies: string[]
  timeframes: string[]
  confirmations: number
  confirmationWindowSeconds: number
  cooldownSeconds: number
  valueUsd: number
  maxPositions: number
}

interface OptionItem {
  title: string
  value: string
  // 允许附加字段：SmartSelect 的 items 需要 Record<string, unknown> 形状
  [key: string]: unknown
}

const props = withDefaults(
  defineProps<{
    pushStatus: SignalPushStatus
    pushVolumeInput: number
    pushVolumeDirty?: boolean
    savingDingtalkPush?: boolean
    savingPushConfig?: boolean
    autoEnabled: boolean
    savingAutoTrade?: boolean
    autoForm: AutoTradeForm
    autoValid: boolean
    savingAuto?: boolean
    lastAutoOpenText: string
    directionOptions: OptionItem[]
    timeframeOptions: string[]
    strategyOptions: OptionItem[]
  }>(),
  { pushVolumeDirty: false, savingDingtalkPush: false, savingPushConfig: false, savingAutoTrade: false, savingAuto: false },
)

// 表单对象由父组件持有，这里直接改其字段并通知「已修改」，
// 避免 v-model 在 props 上反复往返导致抖动。
const autoForm = props.autoForm

type NumericKey =
  | 'confirmations'
  | 'confirmationWindowSeconds'
  | 'cooldownSeconds'
  | 'valueUsd'
  | 'maxPositions'

// 五个数字参数用数据驱动渲染：加字段不用再复制一段模板
// 说明统一写在 label 里（确认窗口/冷却时间已带单位），不再用 persistent-hint，
// 否则各行提示文字行数不同会互相挤压、导致输入框错位
const numericFields: Array<{ key: NumericKey; label: string; min: number }> = [
  { key: 'confirmations', label: '确认数', min: 1 },
  { key: 'confirmationWindowSeconds', label: '确认窗口 (秒)', min: 1 },
  { key: 'cooldownSeconds', label: '冷却时间 (秒)', min: 0 },
  { key: 'valueUsd', label: '单笔金额 (USD)', min: 1 },
  { key: 'maxPositions', label: '最大持仓数', min: 1 },
]

const emit = defineEmits<{
  (e: 'update:pushVolumeInput', value: number): void
  (e: 'toggle-dingtalk', value: unknown): void
  (e: 'save-volume'): void
  (e: 'toggle-auto', value: unknown): void
  (e: 'save-auto'): void
  (e: 'dirty'): void
}>()
</script>
