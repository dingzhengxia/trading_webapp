<!-- frontend/src/components/PageCard.vue -->
<!-- 统一页面卡片骨架：图标 + 标题 + 右侧徽章插槽 + 正文插槽 + 错误提示条，全站页面复用 -->
<template>
  <v-row :class="{ 'mt-2': spaced }">
    <v-col cols="12">
      <v-card>
        <v-card-title class="text-subtitle-1 font-weight-medium d-flex align-center flex-wrap ga-2">
          <v-icon v-if="icon" start>{{ icon }}</v-icon>
          <span>{{ title }}</span>
          <v-spacer></v-spacer>
          <slot name="badges"></slot>
        </v-card-title>
        <v-divider></v-divider>
        <v-card-text>
          <slot></slot>
          <v-alert
            v-if="error"
            type="error"
            variant="tonal"
            density="compact"
            class="mt-3 text-caption"
          >
            最近错误：{{ error }}
          </v-alert>
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    icon?: string
    title: string
    /** 错误提示（非空时在正文底部显示红色警示条） */
    error?: string | null
    /** 非首个卡片时与上一张卡留出间距 */
    spaced?: boolean
  }>(),
  { error: null, spaced: false },
)
</script>
