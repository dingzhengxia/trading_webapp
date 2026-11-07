<!-- frontend/src/components/SmartSelect.vue -->
<!--
  移动端友好的选择器：
  - 桌面（≥ md）：行为完全等同 v-select，保留下拉菜单；
  - 手机（< md）：把选项平铺成可换行的胶囊按钮，点一下就选中，没有弹出层，
    避免 Vuetify 下拉在窄屏上“菜单太小 / 被卡片裁切 / 需要精准点按”的问题。
-->
<template>
  <div class="smart-select">
    <template v-if="isMobile">
      <div v-if="label" class="smart-select__label">{{ label }}</div>
      <div class="smart-select__chips" :class="{ 'smart-select__chips--dense': dense }">
        <button
          v-for="opt in normalizedItems"
          :key="String(opt.value)"
          type="button"
          class="smart-chip"
          :class="{ 'smart-chip--on': isSelected(opt.value) }"
          :disabled="disabled"
          :aria-pressed="isSelected(opt.value)"
          @click="toggle(opt.value)"
        >
          {{ opt.title }}
        </button>

        <button
          v-if="clearable && hasValue && !multiple"
          type="button"
          class="smart-chip smart-chip--clear"
          :disabled="disabled"
          @click="clear"
        >
          清除
        </button>

        <span v-if="!normalizedItems.length" class="text-caption text-medium-emphasis">
          暂无可选项
        </span>
      </div>
      <div v-if="hint" class="text-caption text-medium-emphasis mt-1">{{ hint }}</div>
    </template>

    <v-select
      v-else
      :model-value="modelValue"
      :items="items"
      :item-title="itemTitle"
      :item-value="itemValue"
      :label="label"
      :multiple="multiple"
      :disabled="disabled"
      :clearable="clearable"
      :density="density"
      :variant="variant"
      :hide-details="hideDetails"
      :hint="hint"
      @update:model-value="onSelect"
    ></v-select>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useDisplay } from 'vuetify'

type Primitive = string | number
// v-model 取值：单选为标量，多选为数组；父组件的 ref 类型各不相同，这里统一用联合类型收敛
type SelectValue = Primitive | Primitive[] | null | undefined
type RawItem = Primitive | Record<string, unknown>

const props = withDefaults(
  defineProps<{
    modelValue?: SelectValue
    items?: RawItem[]
    itemTitle?: string
    itemValue?: string
    label?: string
    multiple?: boolean
    disabled?: boolean
    clearable?: boolean
    density?: 'default' | 'comfortable' | 'compact'
    variant?: 'filled' | 'outlined' | 'plain' | 'underlined' | 'solo' | 'solo-inverted' | 'solo-filled'
    hideDetails?: boolean | 'auto'
    hint?: string
    /** 表格单元格等窄容器里用更小的胶囊 */
    dense?: boolean
  }>(),
  {
    items: () => [],
    itemTitle: 'title',
    itemValue: 'value',
    multiple: false,
    disabled: false,
    clearable: false,
    density: 'compact',
    variant: 'outlined',
    hideDetails: true,
    dense: false,
  },
)

const emit = defineEmits<{ (e: 'update:modelValue', value: SelectValue): void }>()

const { smAndDown } = useDisplay()
const isMobile = computed(() => smAndDown.value)

const normalizedItems = computed(() =>
  props.items.map((raw) => {
    if (raw !== null && typeof raw === 'object') {
      const record = raw as Record<string, unknown>
      return {
        title: String(record[props.itemTitle] ?? ''),
        value: record[props.itemValue] as Primitive,
      }
    }
    return { title: String(raw), value: raw as Primitive }
  }),
)

const selectedValues = computed<Primitive[]>(() => {
  const value = props.modelValue
  if (Array.isArray(value)) return value as Primitive[]
  if (value === null || value === undefined || value === '') return []
  return [value as Primitive]
})

const hasValue = computed(() => selectedValues.value.length > 0)

function isSelected(value: Primitive): boolean {
  return selectedValues.value.includes(value)
}

function onSelect(value: unknown): void {
  emit('update:modelValue', value as SelectValue)
}

function toggle(value: Primitive): void {
  if (props.disabled) return
  if (props.multiple) {
    const next = isSelected(value)
      ? selectedValues.value.filter((item) => item !== value)
      : [...selectedValues.value, value]
    emit('update:modelValue', next)
    return
  }
  // 单选：再次点击已选项时，若允许清除就取消选择，否则保持
  emit('update:modelValue', isSelected(value) && props.clearable ? null : value)
}

function clear(): void {
  emit('update:modelValue', props.multiple ? [] : null)
}
</script>

<style scoped>
.smart-select {
  min-width: 0;
}
.smart-select__label {
  font-size: 0.75rem;
  line-height: 1.2;
  opacity: 0.7;
  margin-bottom: 6px;
}
.smart-select__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  max-height: 40vh;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}
.smart-chip {
  appearance: none;
  -webkit-appearance: none;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: transparent;
  color: rgb(var(--v-theme-on-surface));
  border-radius: 999px;
  min-height: 40px;
  padding: 0 16px;
  font-size: 0.9375rem;
  line-height: 1.1;
  font-family: inherit;
  cursor: pointer;
  transition:
    background-color 0.15s ease,
    border-color 0.15s ease,
    transform 0.08s ease;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}
.smart-chip:active {
  transform: scale(0.97);
}
.smart-chip--on {
  background: rgb(var(--v-theme-primary));
  border-color: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
  font-weight: 600;
}
.smart-chip:disabled {
  opacity: 0.45;
  cursor: default;
}
.smart-chip--clear {
  border-style: dashed;
  opacity: 0.75;
  padding: 0 12px;
  font-size: 0.875rem;
}
.smart-select__chips--dense .smart-chip {
  min-height: 32px;
  padding: 0 10px;
  font-size: 0.8125rem;
}
/* 表格单元格里不做内部滚动，避免和表格自身的横向滚动打架 */
.smart-select__chips--dense {
  max-height: none;
  gap: 6px;
}
</style>
