<!-- frontend/src/components/AppDockFooter.vue -->
<!-- 固定悬浮底栏：右侧操作按钮插槽，自动避让侧边栏（桌面）与底部导航（移动） -->
<template>
  <v-footer class="pa-0 app-dock" :style="footerStyle">
    <v-card flat tile class="d-flex align-center px-4 w-100" height="64px">
      <v-spacer></v-spacer>
      <slot></slot>
    </v-card>
  </v-footer>
</template>

<script setup lang="ts">
import { computed, type CSSProperties } from 'vue'
import { useDisplay, useLayout } from 'vuetify'

// useDisplay() 上没有 application，侧边栏宽度需从 useLayout().mainRect 获取
const vuetifyDisplay = useDisplay()
const vuetifyLayout = useLayout()

const footerStyle = computed<CSSProperties>(() => ({
  position: 'fixed',
  right: '0',
  zIndex: 1000,
  // 底部导航已下线（导航改成顶部抽屉），手机端不再需要为它让出 56px
  bottom: '0px',
  left: vuetifyDisplay.mdAndUp.value ? `${vuetifyLayout.mainRect.value.left}px` : '0px',
}))
</script>
