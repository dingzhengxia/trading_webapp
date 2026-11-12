<!-- frontend/src/components/PageSkeleton.vue -->
<!-- 统一加载骨架：有骨架屏就不会出现「先空白后撑开」的布局跳动 -->
<template>
  <v-skeleton-loader type="article, actions" class="page-skeleton" />
</template>

<style scoped>
.page-skeleton {
  background: transparent;
}
</style>
