<!-- frontend/src/components/AppDockFooter.vue -->
<!-- 固定悬浮底栏：右侧操作按钮插槽，自动避让侧边栏（桌面）。
     内容区对齐 .page-shell 的 max-width:1600px；bottom 定位交给 base.css
     （默认贴底，<md 抬高到 Tab 栏上方），这里不再内联写死。 -->
<template>
  <v-footer class="pa-0 app-dock" :style="footerStyle">
    <div class="dock-inner d-flex align-center ga-2 px-4 w-100">
      <v-spacer></v-spacer>
      <slot></slot>
    </div>
  </v-footer>
</template>

<script setup lang="ts">
import { computed, type CSSProperties } from 'vue'
import { useDisplay, useLayout } from 'vuetify'

// useDisplay() 上没有 application，侧边栏宽度需从 useLayout().mainRect 获取
const vuetifyDisplay = useDisplay()
const vuetifyLayout = useLayout()

// bottom 不在这里内联：base.css 统一管理（手机断点要给底部 Tab 栏让位）
const footerStyle = computed<CSSProperties>(() => ({
  position: 'fixed',
  right: '0',
  zIndex: 1000,
  left: vuetifyDisplay.mdAndUp.value ? `${vuetifyLayout.mainRect.value.left}px` : '0px',
}))
</script>

<style scoped>
.dock-inner {
  max-width: 1600px;
  margin: 0 auto;
  height: var(--dock-h);
}
</style>
