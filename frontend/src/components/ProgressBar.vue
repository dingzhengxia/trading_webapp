<!-- frontend/src/components/ProgressBar.vue -->
<!--
  全局任务进度条（悬浮 HUD）。
  刻意固定为深色：它浮在任意主题的内容之上，需要跨主题保持同样的可读性，
  因此不使用主题色当底色（浅色主题下会变成白底白字）。
-->
<template>
  <v-footer v-if="uiStore.progress.show" app class="pa-0 progress-dock" style="z-index: 1008">
    <div class="progress-card d-flex align-center px-2 px-sm-4 w-100">
      <!-- 左侧任务名 -->
      <span class="hud-title flex-shrink-0 mr-4 d-none d-md-flex">
        {{ uiStore.progress.task_name }}
      </span>

      <v-progress-linear
        :model-value="progressPercentage"
        :color="progressColor"
        :indeterminate="uiStore.isStopping"
        height="25"
        rounded
        :striped="!uiStore.isStopping"
        bg-color="rgba(255,255,255,0.10)"
        class="flex-grow-1"
      >
        <template #default>
          <div class="d-flex justify-space-between align-center w-100 px-2 hud-readout">
            <span class="d-md-none">{{ uiStore.progress.task_name }}</span>
            <v-spacer class="d-md-none"></v-spacer>

            <span v-if="!uiStore.isStopping" class="mx-2 num">
              {{ Math.ceil(progressPercentage) }}%
            </span>
            <span v-else class="mx-2">正在停止…</span>

            <v-spacer></v-spacer>
            <div class="d-flex align-center ga-1">
              <v-icon size="small" color="success">mdi-check-circle</v-icon>
              <span class="num">{{ uiStore.progress.success_count }}</span>
              <span class="mx-1">/</span>
              <v-icon
                size="small"
                :color="uiStore.progress.failed_count > 0 ? 'error' : 'grey'"
                >mdi-close-circle</v-icon
              >
              <span class="num">{{ uiStore.progress.failed_count }}</span>
              <span class="mx-1">/</span>
              <v-icon size="small" color="grey">mdi-gauge-full</v-icon>
              <span class="num">{{ uiStore.progress.total }}</span>
            </div>
          </div>
        </template>
      </v-progress-linear>

      <v-btn
        color="white"
        variant="text"
        size="small"
        @click="stopTrading"
        :disabled="!uiStore.isRunning || uiStore.isStopping"
        :loading="uiStore.isStopping"
        class="flex-shrink-0 ml-2"
        icon="mdi-stop-circle-outline"
        aria-label="停止当前任务"
      />
    </div>
  </v-footer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useUiStore } from '@/stores/uiStore'
import api from '@/services/api'

const uiStore = useUiStore()

const progressPercentage = computed(() => {
  const total = uiStore.progress.total
  if (total === 0) return 0
  const processed = uiStore.progress.success_count + uiStore.progress.failed_count
  return (processed / total) * 100
})

const stopTrading = () => {
  uiStore.initiateStop()
  api.post('/api/trading/stop').catch((e) => {
    uiStore.logStore.addLog({
      message: `发送停止指令失败: ${e.message}`,
      level: 'error',
      timestamp: new Date().toLocaleTimeString(),
    })
    uiStore.setStatus('停止失败', false)
  })
}

// 状态只体现在进度条填充色上，底色保持固定的深色 HUD
const progressColor = computed(() => {
  if (uiStore.isStopping) return 'warning'
  if (uiStore.progress.failed_count > 0) return 'error'
  if (uiStore.progress.is_final) return 'success'
  return 'primary'
})
</script>

<style scoped>
.progress-card {
  height: 48px;
  background: #161a20;
  color: #e8ecf2;
}
.hud-title {
  font-size: 12px;
  font-weight: 500;
  color: #e8ecf2;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.hud-readout {
  font-size: 12px;
  color: #ffffff;
}
</style>
