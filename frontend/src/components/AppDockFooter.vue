<!-- frontend/src/components/AppDockFooter.vue -->
<!-- 固定悬浮底栏：右侧操作按钮插槽，自动避让侧边栏（桌面）与底部导航（移动） -->
<template>
  <v-footer
    style="
      position: fixed;
      bottom: 0;
      right: 0;
      z-index: 1000;
      border-top: 1px solid rgba(255, 255, 255, 0.12);
    "
    class="pa-0"
    :style="footerStyle"
  >
    <v-card flat tile class="d-flex align-center px-4 w-100" height="64px">
      <v-spacer></v-spacer>
      <slot></slot>
    </v-card>
  </v-footer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useDisplay, useLayout } from 'vuetify'

// useDisplay() 上没有 application，侧边栏宽度需从 useLayout().mainRect 获取
const vuetifyDisplay = useDisplay()
const vuetifyLayout = useLayout()

const footerStyle = computed(() => {
  const styles: { bottom: string; left: string } = {
    bottom: vuetifyDisplay.smAndDown.value ? '56px' : '0px',
    left: '0px',
  }
  if (vuetifyDisplay.mdAndUp.value) {
    styles.left = `${vuetifyLayout.mainRect.value.left}px`
  }
  return styles
})
</script>
