<!-- frontend/src/components/HelpTip.vue -->
<!-- 控件说明角标：一个淡色「?」，点击弹出说明卡片。
     用法：
       字段  <template #append-inner><HelpTip :text="HELP.xxx" /></template>
       按钮  <v-btn …>开仓</v-btn><HelpTip :text="HELP.btnOpen" />
     设计约束：默认几乎不可见（opacity .4），悬停/聚焦才醒目，避免满屏问号；
     只做「点击打开」不做 hover 打开 —— hover 与 click 同时开启时，鼠标移上去已展开、
     再点一下会被判成关闭，观感像「点了没用」。
     点击一律 .stop，防止误触父级卡片/表格行的点击逻辑。 -->
<template>
  <span class="help-tip" @click.stop @keydown.stop>
    <v-menu
      location="top"
      :offset="8"
      :close-on-content-click="false"
      max-width="320"
      content-class="help-tip__menu"
    >
      <template #activator="{ props: activatorProps }">
        <button
          v-bind="activatorProps"
          type="button"
          class="help-tip__btn"
          :aria-label="ariaLabel"
          :title="title || undefined"
        >
          <v-icon size="15">mdi-help-circle-outline</v-icon>
        </button>
      </template>
      <v-card variant="flat" class="help-tip__card pa-3">
        <div v-if="title" class="text-subtitle-2 mb-1">{{ title }}</div>
        <div class="text-body-2 help-tip__body">{{ text }}</div>
      </v-card>
    </v-menu>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  /** 说明正文（换行用 \n，会原样保留） */
  text: string
  /** 可选小标题 */
  title?: string
}>()

const ariaLabel = computed(() => `说明：${props.title ?? props.text.slice(0, 24)}`)
</script>

<style scoped>
.help-tip {
  display: inline-flex;
  align-items: center;
  /* 输入框的 append-inner 是 align-items:flex-start 的 flex，
     不自适应会在字段顶部贴边，这里让它自己垂直居中 */
  align-self: center;
  vertical-align: middle;
  line-height: 1;
}

.help-tip__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  color: rgb(var(--v-theme-on-surface));
  opacity: 0.4;
  cursor: pointer;
  transition:
    opacity 0.15s ease,
    color 0.15s ease,
    background-color 0.15s ease;
}

.help-tip__btn:hover,
.help-tip__btn:focus-visible {
  opacity: 1;
  color: rgb(var(--v-theme-primary));
  background-color: rgba(var(--v-theme-primary), 0.1);
  outline: none;
}

/* 触屏设备没有 hover，直接提到可读对比度 */
@media (hover: none) {
  .help-tip__btn {
    opacity: 0.65;
  }
}

.help-tip__body {
  white-space: pre-line;
  line-height: 1.55;
}
</style>

<style>
/* 菜单挂在 body 上，scoped 选不中，单独给一张不透明的卡 */
.help-tip__menu .help-tip__card {
  background-color: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.18);
}
</style>
