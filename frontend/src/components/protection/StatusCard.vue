<!-- frontend/src/components/protection/StatusCard.vue -->
<!-- 仓位保护状态卡：启用/演练开关、引擎版本与接口健康徽章（T11 自 ProtectionView 拆出） -->
<template>
  <PageCard icon="mdi-shield-check-outline" title="仓位保护（实时风控）" :error="status.last_error">
    <template #badges>
      <v-chip size="small" variant="tonal" :color="status.running ? 'success' : 'grey'">
        {{ status.running ? '守护中' : '未运行' }}
      </v-chip>
      <v-chip size="small" variant="tonal" :color="status.enabled ? 'success' : 'grey'">
        {{ status.enabled ? '已启用' : '已停用' }}
      </v-chip>
      <v-chip size="small" variant="tonal" :color="isV2 ? 'primary' : 'grey'">
        {{ isV2 ? 'v2 引擎' : 'v1 引擎' }}
      </v-chip>
      <v-chip v-if="isV2 && status.v2?.dry_run" size="small" variant="tonal" color="warning">
        演练模式
      </v-chip>
    </template>
    <v-row dense align="center">
      <v-col cols="12" md="3">
        <v-switch
          :model-value="status.enabled"
          :loading="saving"
          label="启用仓位保护"
          color="primary"
          inset
          hide-details
          @update:model-value="onToggleEnabled"
        ></v-switch>
      </v-col>
      <v-col v-if="isV2" cols="12" md="3">
        <v-switch
          :model-value="Boolean(form.dry_run)"
          :loading="saving"
          label="演练模式（只记录不下单）"
          color="warning"
          inset
          hide-details
          @update:model-value="onToggleDryRun"
        ></v-switch>
      </v-col>
      <v-col cols="12" :md="isV2 ? 6 : 9">
        <div class="d-flex flex-wrap ga-2">
          <v-chip size="small" variant="tonal" prepend-icon="mdi-timer-sand">
            周期: {{ status.timeframe ?? '—' }}
          </v-chip>
          <v-chip size="small" variant="tonal" prepend-icon="mdi-account-multiple-check">
            守卫仓位: {{ status.positions.length }}
          </v-chip>
          <v-chip
            size="small"
            variant="tonal"
            prepend-icon="mdi-api"
            :color="status.api.error_count > 0 ? 'warning' : 'default'"
          >
            请求 {{ status.api.request_count }} / 错误 {{ status.api.error_count }}
          </v-chip>
          <v-chip
            size="small"
            variant="tonal"
            prepend-icon="mdi-flash-alert"
            :color="status.api.circuit_open ? 'error' : 'default'"
          >
            {{ status.api.circuit_open ? '接口限流熔断中' : '接口正常' }}
          </v-chip>
        </div>
      </v-col>
    </v-row>
    <v-alert type="info" variant="tonal" density="compact" class="mt-3 text-caption">
      <div>· 依据 EMA 结构 + ATR 确认，在每个持仓方向上独立维护 T1/T2/T3 结构减仓、分批止盈（限价 maker）与保护性 STOP 单。</div>
      <div>· 每次「手动平仓 → 重新开仓」都会建立全新风险周期，不会继承旧的 T1/TP 状态。</div>
      <div>· 风控引擎<strong>只会减仓/挂保护单，永远不会开仓</strong>；紧急止损与限价超时兜底会使用市价<strong>平仓</strong>（非开仓）。</div>
    </v-alert>
  </PageCard>
</template>

<script setup lang="ts">
// 组件直接消费 useProtectionConfig 的模块级单例状态与写入口
import { useProtectionConfig } from '@/composables/useProtectionConfig'
import PageCard from '@/components/PageCard.vue'

const { status, form, saving, isV2, onToggleEnabled, onToggleDryRun } = useProtectionConfig()
</script>
