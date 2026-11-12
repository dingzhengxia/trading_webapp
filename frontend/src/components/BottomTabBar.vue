<!-- frontend/src/components/BottomTabBar.vue -->
<!-- 手机专用底部 Tab 栏（<md 显示）：primaryNav 4 项 + 「更多」。
     所有布局样式统一放 base.css 的 .app-tabbar / .tabbar-item，组件内不写 scoped 布局。 -->
<template>
  <nav class="app-tabbar d-md-none" role="navigation" aria-label="主导航">
    <router-link
      v-for="item in primaryNav"
      :key="item.path"
      :to="item.path"
      class="tabbar-item"
      :class="{ 'tabbar-item--active': isActive(item.path) }"
      :aria-current="isActive(item.path) ? 'page' : undefined"
    >
      <v-icon :size="20">{{ item.icon }}</v-icon>
      <span class="tabbar-label">{{ item.title }}</span>
    </router-link>

    <button type="button" class="tabbar-item" aria-label="更多页面" @click="emit('open-more')">
      <v-icon :size="20">mdi-dots-horizontal</v-icon>
      <span class="tabbar-label">更多</span>
    </button>
  </nav>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import { primaryNav } from '@/config/nav'

const emit = defineEmits<{ (e: 'open-more'): void }>()

const route = useRoute()

// 路由都是精确 path（/ 已重定向到 /trading），直接精确匹配即可
const isActive = (path: string): boolean => route.path === path
</script>
