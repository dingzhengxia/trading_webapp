<!-- frontend/src/views/ProtectionView.vue（仓位保护：monitor 实时风控并入） -->
<!--
  重设计（redesign-spec 2026-11-13 · B2）：
    状态卡 → 守卫中的仓位表 → 最近保护动作 → 参数设置（三组折叠面板）。
  T11 拆分：本页只剩编排（轮询 + 组件拼装），状态与写入口统一收敛在
  composables/useProtectionConfig.ts（配置域唯一写路径），
  展示与表单拆到 components/protection/{StatusCard,RiskSettingsPanel,ConfigForm}.vue。
-->
<template>
  <div>
    <!-- 状态卡 -->
    <ProtectionStatusCard />

    <!-- 守卫中的仓位 + 最近保护动作 -->
    <RiskSettingsPanel />

    <!-- 参数设置 -->
    <ConfigForm />
  </div>
</template>

<script setup lang="ts">
import { useProtectionConfig } from '@/composables/useProtectionConfig'
import { usePolling } from '@/composables/usePolling'
import ProtectionStatusCard from '@/components/protection/StatusCard.vue'
import RiskSettingsPanel from '@/components/protection/RiskSettingsPanel.vue'
import ConfigForm from '@/components/protection/ConfigForm.vue'

const { fetchStatus } = useProtectionConfig()

usePolling(fetchStatus, 10000, { immediate: true })
</script>
