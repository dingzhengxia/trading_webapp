<!-- frontend/src/components/EmptyState.vue -->
<!-- 统一空状态：必须给一个「下一步」动作，而不是只丢一句「暂无数据」 -->
<template>
  <div class="empty-state text-center">
    <v-icon size="28" class="mb-2" color="medium-emphasis">{{ icon }}</v-icon>
    <div class="empty-title">{{ title }}</div>
    <div v-if="description" class="empty-desc text-medium-emphasis">{{ description }}</div>
    <v-btn
      v-if="actionText"
      class="mt-4"
      size="small"
      color="primary"
      variant="tonal"
      :prepend-icon="actionIcon || undefined"
      :loading="actionLoading"
      @click="emit('action')"
    >
      {{ actionText }}
    </v-btn>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string
    description?: string
    icon?: string
    actionText?: string
    actionIcon?: string
    actionLoading?: boolean
  }>(),
  {
    description: '',
    icon: 'mdi-inbox-outline',
    actionText: '',
    actionIcon: '',
    actionLoading: false,
  },
)

const emit = defineEmits<{ (e: 'action'): void }>()
</script>

<style scoped>
.empty-state {
  padding: 32px 20px;
  border: 1px dashed rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
}
.empty-title {
  font-size: 13px;
  font-weight: 500;
}
.empty-desc {
  font-size: 12px;
  margin-top: 4px;
  max-width: 46ch;
  margin-left: auto;
  margin-right: auto;
  line-height: 1.6;
}
</style>
