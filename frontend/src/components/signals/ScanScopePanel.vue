<!-- frontend/src/components/signals/ScanScopePanel.vue -->
<!-- 扫描范围：静态币 / Top N 补足 / 周期。原先挤在首屏，现在收进 Tab -->
<template>
  <div>
    <SectionHeader
      icon="mdi-radar"
      title="扫描开关"
      description="关闭后不再请求行情，也不会产生新信号"
    >
      <v-switch
        :model-value="enabled"
        :loading="savingScan"
        label="启用信号扫描"
        color="primary"
        hide-details
        @update:model-value="emit('toggle', $event)"
      />
    </SectionHeader>

    <v-divider class="mb-4" />

    <SectionHeader
      icon="mdi-format-list-checks"
      title="扫描范围"
      description="静态币始终扫描并在钉钉实时推送，其余按成交额补足 Top N"
    />

    <v-row dense>
      <v-col cols="12" md="6">
        <SmartSelect
          :model-value="staticSymbols"
          :items="staticItems"
          label="静态币种"
          multiple
          clearable
          searchable
          hint="从备选池中搜索选择，始终扫描并实时推送"
          :hide-details="false"
          @update:model-value="emit('update:staticSymbols', $event)"
        />
      </v-col>
      <v-col cols="6" sm="4" md="2">
        <v-text-field
          :model-value="topN"
          label="Top N 补足"
          type="number"
          min="1"
          max="500"
          hint="按成交额排名补足"
          persistent-hint
          @update:model-value="emit('update:topN', Number($event))"
        />
      </v-col>
      <v-col cols="12" sm="8" md="4">
        <SmartSelect
          :model-value="timeframes"
          :items="timeframeOptions"
          label="扫描周期"
          multiple
          @update:model-value="emit('update:timeframes', $event)"
        />
      </v-col>
    </v-row>

    <div class="d-flex align-center flex-wrap ga-3 mt-4">
      <v-btn
        color="primary"
        variant="tonal"
        prepend-icon="mdi-content-save"
        :loading="saving"
        :disabled="!valid || saving"
        @click="emit('save')"
      >
        保存扫描范围
      </v-btn>
      <span v-if="dirty" class="text-caption text-warning">
        <v-icon size="13" class="mr-1">mdi-circle-edit-outline</v-icon>有未保存的修改
      </span>
      <span v-else class="text-caption text-medium-emphasis">修改后点保存才会生效</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import SectionHeader from '@/components/SectionHeader.vue'
import SmartSelect from '@/components/SmartSelect.vue'

withDefaults(
  defineProps<{
    enabled: boolean
    savingScan?: boolean
    staticSymbols: string[]
    staticItems: string[]
    topN: number
    timeframes: string[]
    timeframeOptions: string[]
    valid: boolean
    saving?: boolean
    dirty?: boolean
  }>(),
  { savingScan: false, saving: false, dirty: false },
)

const emit = defineEmits<{
  (e: 'update:staticSymbols', value: unknown): void
  (e: 'update:topN', value: number): void
  (e: 'update:timeframes', value: unknown): void
  (e: 'toggle', value: unknown): void
  (e: 'save'): void
}>()
</script>
