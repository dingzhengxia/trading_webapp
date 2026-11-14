<!-- frontend/src/components/HelpTip.vue -->
<!-- 控件说明角标：一个淡色「?」，点击弹出说明卡片。
     用法：
       字段  <template #append-inner><HelpTip :text="HELP.xxx" /></template>
       按钮  <v-btn …>开仓</v-btn><HelpTip :text="HELP.btnOpen" />
     设计约束：
     1) 默认几乎不可见（opacity .4），悬停/聚焦才醒目，避免满屏问号；
     2) 只做「点击打开」不做 hover 打开 —— hover 与 click 同时开启时，鼠标移上去已展开、
        再点一下会被判成关闭，观感像「点了没用」；
     3) 点击一律 .stop，防止误触父级卡片/表格行的点击逻辑；
     4) **桌面用 v-menu 锚定气泡，手机/平板用 v-dialog 居中弹窗**：小屏上把 320px 的
        气泡锚在一个靠边的「?」上，必然有半张卡片被推出可视区（正文被裁、无法滚动），
        这是移动端「说明看不全」的根因。弹窗宽度受 max-width 约束、正文可滚动，
        无论文案多长都能读完。 -->
<template>
  <span class="help-tip" @click.stop @keydown.stop>
    <!-- 同一套 slot / 卡片内容，仅外层容器按屏幕切换（不用写两遍按钮） -->
    <component
      :is="isDesktop ? VMenu : VDialog"
      v-model="open"
      v-bind="overlayProps"
      content-class="help-tip__overlay"
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
        <div class="help-tip__head">
          <div v-if="title" class="text-subtitle-2">{{ title }}</div>
          <v-spacer v-else></v-spacer>
          <!-- 弹窗必须给一个显式关闭入口（小屏上点空白关闭不直观） -->
          <button
            v-if="!isDesktop"
            type="button"
            class="help-tip__close"
            aria-label="关闭说明"
            @click="open = false"
          >
            <v-icon size="18">mdi-close</v-icon>
          </button>
        </div>
        <div class="text-body-2 help-tip__body">{{ text }}</div>
      </v-card>
    </component>
  </span>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDisplay } from 'vuetify'
// 经 <component :is> 动态渲染，vite-plugin-vuetify 无法静态分析，必须显式引入组件对象
import { VDialog, VMenu } from 'vuetify/components'

const props = defineProps<{
  /** 说明正文（换行用 \n，会原样保留） */
  text: string
  /** 可选小标题 */
  title?: string
}>()

const { mdAndUp } = useDisplay()
const isDesktop = computed(() => mdAndUp.value)
const open = ref(false)

// 桌面：贴着「?」往上方弹；移动端：居中弹窗，宽度吃满但留 12px 边
const overlayProps = computed(() =>
  isDesktop.value
    ? { location: 'top' as const, offset: 8, maxWidth: 340, closeOnContentClick: false }
    : { maxWidth: 440 },
)

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
  position: relative;
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

/* 视觉只有 20px，但手指要 40px 才好点（与持仓表勾选框同一口径） */
.help-tip__btn::after {
  content: '';
  position: absolute;
  inset: -10px;
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

.help-tip__head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 24px;
  margin-bottom: 4px;
}

.help-tip__close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  margin: -4px -4px -4px 0;
  border-radius: 50%;
  color: rgb(var(--v-theme-on-surface));
  opacity: 0.6;
  margin-left: auto;
}

.help-tip__close:hover {
  opacity: 1;
  background-color: rgba(var(--v-theme-on-surface), 0.08);
}

.help-tip__body {
  white-space: pre-line;
  line-height: 1.55;
  /* 文案里有 PM_WS_SL_ 这类长下划线串，不强制断行会把卡片顶宽 */
  overflow-wrap: anywhere;
}
</style>

<style>
/* 气泡/弹窗挂在 body 上，scoped 选不中，单独给一张不透明的卡；
   限高 + 内部滚动：再长的文案也不会溢出屏幕 */
.help-tip__overlay .help-tip__card {
  max-height: min(60vh, 480px);
  overflow-y: auto;
  background-color: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.18);
}

.help-tip__overlay {
  max-width: calc(100vw - 24px);
}

/* 手机上正文略大一号，长段落更好读 */
@media (max-width: 959px) {
  .help-tip__overlay .help-tip__body {
    font-size: 0.9375rem;
  }
}
</style>
