<!-- frontend/src/components/SmartSelect.vue -->
<!--
  统一的选择器：
  - 桌面（≥ md）：v-select（searchable 时用 v-autocomplete，可输入搜索），保留下拉菜单；
  - 手机（< md）：只读输入框 + 全屏选择页（顶部搜索、平铺大行、点选即勾选），
    彻底避开 Vuetify 下拉在窄屏上只有一条缝、完全没法点的问题。
-->
<template>
  <div class="smart-select">
    <template v-if="isMobile">
      <v-text-field
        :model-value="summary"
        :label="label"
        readonly
        :variant="variant"
        :density="density"
        :hide-details="hideDetails"
        :disabled="disabled"
        :hint="hint"
        :persistent-hint="!!hint"
        :placeholder="placeholderText"
        @click="openDialog"
      >
        <template #append-inner>
          <v-icon icon="mdi-chevron-down" size="20" />
        </template>
      </v-text-field>

      <v-dialog v-model="dialog" fullscreen transition="dialog-bottom-transition">
        <v-card>
          <v-toolbar density="compact">
            <v-toolbar-title>{{ label || '请选择' }}</v-toolbar-title>
            <v-spacer></v-spacer>
            <v-btn icon="mdi-close" @click="dialog = false"></v-btn>
          </v-toolbar>
          <v-divider></v-divider>

          <div class="pa-3">
            <v-text-field
              v-model="search"
              label="搜索"
              prepend-inner-icon="mdi-magnify"
              variant="outlined"
              density="compact"
              hide-details
              clearable
            ></v-text-field>
          </div>
          <v-divider></v-divider>

          <div class="ss-list">
            <div
              v-for="opt in filteredItems"
              :key="String(opt.value)"
              class="ss-row"
              :class="{ 'ss-row--on': isSelected(opt.value) }"
              @click="pick(opt.value)"
            >
              <span class="ss-row__title">{{ opt.title }}</span>
              <v-icon
                size="22"
                :color="isSelected(opt.value) ? 'primary' : 'grey'"
                :icon="isSelected(opt.value) ? 'mdi-check-circle' : 'mdi-circle-outline'"
              ></v-icon>
            </div>
            <div v-if="filteredItems.length === 0" class="pa-6 text-center text-caption text-medium-emphasis">
              没有匹配的选项
            </div>
          </div>

          <v-divider></v-divider>
          <div class="pa-3 d-flex align-center ga-2">
            <v-btn
              v-if="clearable"
              variant="text"
              class="flex-grow-1"
              :disabled="!hasValue"
              @click="clearAndClose"
            >
              清空
            </v-btn>
            <v-btn color="primary" variant="tonal" class="flex-grow-1" @click="dialog = false">
              完成{{ multiple ? `（已选 ${selectedValues.length}）` : '' }}
            </v-btn>
          </div>
        </v-card>
      </v-dialog>
    </template>

    <!-- v-select 与 v-autocomplete 的 props 完全同构，用动态组件收敛为一份 -->
    <component
      :is="searchable ? VAutocomplete : VSelect"
      v-else
      :model-value="modelValue"
      :items="items"
      :item-title="itemTitle"
      :item-value="itemValue"
      :label="label"
      :multiple="multiple"
      :chips="multiple"
      :closable-chips="multiple"
      :disabled="disabled"
      :clearable="clearable"
      :density="density"
      :variant="variant"
      :hide-details="hideDetails"
      :hint="hint"
      :persistent-hint="!!hint"
      @update:model-value="onSelect"
    ></component>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDisplay } from 'vuetify'
// 按需引入（T12）：下面两个组件经 <component :is> 动态渲染且 vite-plugin-vuetify
// 无法静态分析字符串派发，必须显式 import 并直接传组件对象
import { VAutocomplete, VSelect } from 'vuetify/components'

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
    /** 桌面端允许输入搜索（选项很多时用） */
    searchable?: boolean
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
    searchable: false,
  },
)

const emit = defineEmits<{ (e: 'update:modelValue', value: SelectValue): void }>()

const { smAndDown } = useDisplay()
const isMobile = computed(() => smAndDown.value)

// ---- 手机端全屏选择页 ----
const dialog = ref(false)
const search = ref('')

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

const filteredItems = computed(() => {
  const keyword = search.value.trim().toUpperCase()
  if (!keyword) return normalizedItems.value
  return normalizedItems.value.filter((opt) => opt.title.toUpperCase().includes(keyword))
})

const summary = computed(() => {
  const list = selectedValues.value
  if (list.length === 0) return ''
  const titles = list.map(
    (value) => normalizedItems.value.find((opt) => opt.value === value)?.title ?? String(value),
  )
  if (!props.multiple) return titles[0] ?? String(list[0])
  if (titles.length <= 2) return titles.join('、')
  return `${titles.slice(0, 2).join('、')} 等 ${titles.length} 项`
})

const placeholderText = computed(() => (selectedValues.value.length === 0 ? '点击选择' : ''))

function isSelected(value: Primitive): boolean {
  return selectedValues.value.includes(value)
}

function onSelect(value: unknown): void {
  emit('update:modelValue', value as SelectValue)
}

function clear(): void {
  emit('update:modelValue', props.multiple ? [] : null)
}

function clearAndClose(): void {
  clear()
  dialog.value = false
}

function openDialog(): void {
  if (props.disabled) return
  search.value = ''
  dialog.value = true
}

function pick(value: Primitive): void {
  if (props.disabled) return
  if (props.multiple) {
    const next = isSelected(value)
      ? selectedValues.value.filter((item) => item !== value)
      : [...selectedValues.value, value]
    emit('update:modelValue', next)
    return
  }
  // 单选：点选后关闭（再次点已选项且允许清除则取消）
  emit('update:modelValue', isSelected(value) && props.clearable ? null : value)
  dialog.value = false
}
</script>

<style scoped>
.smart-select {
  min-width: 0;
}
.ss-list {
  flex: 1 1 auto;
  height: calc(100vh - 260px);
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}
.ss-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 52px;
  padding: 0 16px;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  cursor: pointer;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}
.ss-row:active {
  background: rgba(var(--v-theme-primary), 0.08);
}
.ss-row--on .ss-row__title {
  font-weight: 600;
}
.ss-row__title {
  font-size: 1rem;
}
</style>
