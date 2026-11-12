<!-- frontend/src/components/SectionHeader.vue -->
<!-- 卡内小节标题：图标 + 标题 + 说明 + 右侧动作。原先在 SignalsView 里手写了 3 份 -->
<template>
  <div class="section-header d-flex align-center flex-wrap ga-2" :class="{ 'mt-4': spaced }">
    <v-icon v-if="icon" size="16" color="primary">{{ icon }}</v-icon>
    <span class="text-subtitle-2 font-weight-medium">{{ title }}</span>
    <slot name="badges"></slot>
    <span v-if="description" class="text-caption text-medium-emphasis flex-grow-1">{{
      description
    }}</span>
    <v-spacer v-else></v-spacer>
    <slot></slot>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string
    icon?: string
    description?: string
    spaced?: boolean
  }>(),
  { icon: '', description: '', spaced: false },
)
</script>

<style scoped>
.section-header {
  min-height: 28px;
  margin-bottom: 10px;
}
</style>
