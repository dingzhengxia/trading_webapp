<!-- frontend/src/components/NumberField.vue -->
<!-- 数字输入字段的共享骨架：v-col 栅格 + 数字框 + 「?」说明。
     消除参数表单里 20+ 处逐字段复制的同构模板。
     沿用 v-model.number 语义：清空得到 ''，否则得到 number（与直接写 v-text-field 一致）。 -->
<template>
  <v-col :cols="cols" :sm="sm" :md="md">
    <v-text-field
      v-model.number="localValue"
      type="number"
      :label="label"
      :step="step"
      :min="min"
      :max="max"
      :hint="hint"
      :persistent-hint="persistentHint"
      :disabled="disabled"
      :density="density"
      :variant="variant"
      :hide-details="hideDetails"
    >
      <template v-if="help" #append-inner>
        <HelpTip :text="help" />
      </template>
    </v-text-field>
  </v-col>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import HelpTip from '@/components/HelpTip.vue'

const props = withDefaults(
  defineProps<{
    modelValue: number | string | null
    label: string
    /** HELP.xxx 说明文案；省略则不渲染「?」 */
    help?: string
    step?: string | number
    min?: string | number
    max?: string | number
    cols?: string | number
    sm?: string | number
    md?: string | number
    density?: 'default' | 'comfortable' | 'compact'
    variant?: 'filled' | 'outlined' | 'plain' | 'underlined' | 'solo' | 'solo-inverted' | 'solo-filled'
    hideDetails?: boolean
    hint?: string
    persistentHint?: boolean
    disabled?: boolean
  }>(),
  { cols: 12, hideDetails: true, persistentHint: false, disabled: false },
)

const emit = defineEmits<{ 'update:modelValue': [value: number | string] }>()

// 桥接 v-model：组件内部用 v-model.number 完成字符串→数字转换（与原写法行为一致）
const localValue = computed({
  get: () => props.modelValue,
  set: (value: number | string) => emit('update:modelValue', value),
})
</script>
