<script setup lang="ts">
import type { ProtectionPositionRow } from '@/models/types'

/**
 * 仓位保护进度标签：TP1/TP2/躺平、四档减仓线、待回落档。
 *
 * 守卫卡片（展开视图）和持仓表格共用这一组标签，抽出来只写一份；
 * 有差异的标签（待突破、加仓重算、「等待触发」提示）由调用方按原顺序追加。
 */
defineProps<{ row: ProtectionPositionRow }>()
</script>

<template>
  <v-chip size="x-small" :variant="row.tp1_done ? 'tonal' : 'outlined'" color="info">TP1</v-chip>
  <v-chip size="x-small" :variant="row.tp2_done ? 'tonal' : 'outlined'" color="info">TP2</v-chip>
  <v-chip size="x-small" :variant="row.tp3_done ? 'tonal' : 'outlined'" color="info">躺平</v-chip>
  <v-chip v-if="row.t1_done" size="x-small" variant="tonal" color="warning">T1</v-chip>
  <v-chip v-if="row.t2_done" size="x-small" variant="tonal" color="warning">T2</v-chip>
  <v-chip v-if="row.t3_done" size="x-small" variant="tonal" color="warning">T3</v-chip>
  <v-chip v-if="row.t4_done" size="x-small" variant="tonal" color="error">T4</v-chip>
  <v-chip
    v-if="row.tp_armed_level"
    size="x-small"
    variant="tonal"
    color="success"
    title="已突破止盈价，等价格回到该档就分批止盈（引擎每 3 秒判断）"
  >
    TP{{ row.tp_armed_level }} 待回落
  </v-chip>
</template>
