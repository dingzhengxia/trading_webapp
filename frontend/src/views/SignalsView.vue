<!-- frontend/src/views/SignalsView.vue (信号监控) -->
<!--
  按「看 / 配」拆分（规格 §3 A10）：
  页面只保留 KPI 行 + 状态点行 + 信号列表（首屏可见）+ 纸面跟踪折叠区；
  扫描范围 / 推送与开仓 / 出场规则三类参数收进共享的 ConfigDrawer（3 个 Tab），
  与交易页复用同一个抽屉容器。?tab= 深链保留，映射到抽屉 Tab。

  T11 拆分后本视图为薄壳：数据与写路径在 useSignalsConfig（core），
  业务动作在 useSignalsActions，表单状态在 signalsFormState，
  选项常量与归一化函数在 services/signalsData.ts。
-->
<template>
  <div>
    <!-- 指标行：一眼看到「有多少信号 / 有没有出错 / 自动开仓开着没有」 -->
    <v-row dense>
      <v-col cols="6" sm="3">
        <MetricCard
          label="累计信号"
          :value="status.emitted_count"
          :hint="`已扫描 ${status.scanned_symbols} 个币种`"
          icon="mdi-radar"
        />
      </v-col>
      <v-col cols="6" sm="3">
        <MetricCard
          label="错误数"
          :value="status.error_count"
          :hint="status.last_error ? '存在最近错误，见下方提示' : '无错误'"
          icon="mdi-alert-circle-outline"
          :tone="status.error_count > 0 ? 'down' : 'neutral'"
          :warning="status.error_count > 0"
        />
      </v-col>
      <v-col cols="6" sm="3">
        <MetricCard
          label="纸面胜率"
          :value="winRateText"
          :hint="`样本 ${tracking.paper_stats.total} 笔`"
          icon="mdi-flask-outline"
          :tone="winRateTone"
        />
      </v-col>
      <v-col cols="6" sm="3">
        <MetricCard
          label="自动开仓"
          :value="config.signal_auto_trade_enabled ? '已启用' : '已停用'"
          :hint="`最近：${lastAutoOpenText}`"
          icon="mdi-robot"
        />
      </v-col>
    </v-row>

    <!-- 状态条：运行态与时间戳，弱化为一行文字，不再占用 8 个 chip 的面积 -->
    <div class="status-strip d-flex flex-wrap align-center ga-4 mt-3 mb-3">
      <span class="dot-item">
        <i class="dot" :class="status.running ? 'dot--on' : 'dot--off'"></i>
        {{ status.running ? '扫描中' : '空闲' }}
      </span>
      <span class="dot-item">
        <i class="dot" :class="status.enabled ? 'dot--on' : 'dot--off'"></i>
        {{ status.enabled ? '扫描已启用' : '扫描已停用' }}
      </span>
      <span class="dot-item">
        <i class="dot" :class="pushStatus.dingtalk_configured ? 'dot--on' : 'dot--warn'"></i>
        钉钉{{ pushStatus.dingtalk_configured ? '已配置' : '未配置' }}
      </span>
      <span class="dot-item text-medium-emphasis">上次扫描 {{ formatTime(status.last_scan_at) }}</span>
      <span class="dot-item text-medium-emphasis">下次扫描 {{ formatTime(status.next_scan_at) }}</span>
    </div>

    <v-alert
      v-if="status.last_error"
      type="error"
      variant="tonal"
      density="compact"
      class="mb-3 text-caption"
      closable
    >
      最近错误：{{ status.last_error }}
    </v-alert>

    <!-- 信号列表：首屏主体；工具栏右侧的「配置」按钮打开参数抽屉 -->
    <v-card variant="flat" class="signal-shell">
      <SignalListPanel
        v-model:direction="directionFilter"
        :signals="filteredSignals"
        :total="signals.length"
        :forward-bars="tracking.params.forward_bars"
        :volume-threshold="pushStatus.signal_push_volume_multiplier"
        :static-symbols="pushStatus.static_symbols"
        :strategy-labels="strategyLabels"
        :scanning="scanning"
        :clearing="clearing"
        :loading="loading"
        @scan="scanNow"
        @clear="clearSignals"
        @refresh="refresh"
      >
        <template #toolbar-append>
          <v-btn size="small" variant="text" prepend-icon="mdi-cog" @click="configOpen = true">
            配置
          </v-btn>
        </template>
      </SignalListPanel>
    </v-card>

    <!-- 纸面跟踪明细：默认收起，只读数据（参数在抽屉的「出场规则」Tab） -->
    <v-expansion-panels class="mt-3">
      <v-expansion-panel>
        <v-expansion-panel-title>
          <span class="text-subtitle-1 font-weight-medium">纸面跟踪明细</span>
          <span class="text-caption text-medium-emphasis ml-3">
            {{ paperEnabled ? '启用中' : '未启用' }} · 纸面持仓 {{ tracking.open_positions.length }} ·
            已平仓样本 {{ tracking.paper_stats.total }}
          </span>
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <PaperTrackingPanel
            :tracking="tracking"
            :live-exit="liveExit"
            :strategy-labels="strategyLabels"
          />
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>

    <!-- 共享参数抽屉：扫描范围 / 推送与开仓 / 出场规则 -->
    <ConfigDrawer
      v-model="configOpen"
      title="信号配置"
      icon="mdi-tune-variant"
      :tabs="signalConfigTabs"
      default-tab="scope"
    >
      <template #scope>
        <ScanScopePanel
          :enabled="status.enabled"
          :saving-scan="savingScan"
          :static-symbols="scanStaticSymbols"
          :static-items="staticSymbolItems"
          :top-n="scopeTopN"
          :timeframes="scopeTimeframes"
          :timeframe-options="timeframeOptions"
          :valid="scopeValid"
          :saving="savingScope"
          :dirty="scopeDirty"
          @update:static-symbols="setStaticSymbols"
          @update:top-n="onScopeTopNChange"
          @update:timeframes="onScopeTimeframesChange"
          @toggle="onToggleScan"
          @save="saveScanScope"
        />
      </template>

      <template #push>
        <PushAutoPanel
          :push-status="pushStatus"
          :push-volume-input="pushVolumeInput"
          :push-volume-dirty="pushVolumeDirty"
          :saving-dingtalk-push="savingDingtalkPush"
          :saving-push-config="savingPushConfig"
          :auto-enabled="autoTradeEnabled"
          :saving-auto-trade="savingAutoTrade"
          :auto-form="autoForm"
          :auto-valid="autoFormValid"
          :saving-auto="savingAuto"
          :last-auto-open-text="lastAutoOpenText"
          :direction-options="directionOptions"
          :timeframe-options="timeframeOptions"
          :strategy-options="strategyOptions"
          @update:push-volume-input="onPushVolumeChange"
          @toggle-dingtalk="onToggleDingtalkPush"
          @save-volume="savePushVolume"
          @toggle-auto="onToggleAutoTrade"
          @save-auto="saveAutoConfig"
          @dirty="markAutoFormDirty"
        />
      </template>

      <template #exit>
        <ExitParamsPanel
          :exit-mode="exitMode"
          :paper-form="paperForm"
          :paper-enabled="paperEnabled"
          :live-exit="liveExit"
          :atr-timeframes="ATR_TIMEFRAMES"
          :valid="paperFormValid"
          :saving-paper-config="savingPaperConfig"
          :saving-paper-toggle="savingPaperToggle"
          :saving-live-timeout="savingLiveTimeout"
          :saving-sltp-guard="savingSltpGuard"
          @change-mode="onChangeExitMode"
          @toggle-paper="onTogglePaper"
          @save-paper="savePaperConfig"
          @toggle-live-timeout="onToggleLiveTimeout"
          @toggle-sltp-guard="onToggleSltpGuard"
          @dirty="paperDirty = true"
        />
      </template>
    </ConfigDrawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  ATR_TIMEFRAMES,
  directionOptions,
  signalConfigTabs,
  strategyLabels,
  strategyOptions,
  timeframeOptions,
} from '@/services/signalsData'
import { formatIsoTime as formatTime } from '@/utils/format'
import MetricCard from '@/components/MetricCard.vue'
import ConfigDrawer from '@/components/ConfigDrawer.vue'
import SignalListPanel from '@/components/signals/SignalListPanel.vue'
import ScanScopePanel from '@/components/signals/ScanScopePanel.vue'
import PushAutoPanel from '@/components/signals/PushAutoPanel.vue'
import ExitParamsPanel from '@/components/signals/ExitParamsPanel.vue'
import PaperTrackingPanel from '@/components/signals/PaperTrackingPanel.vue'
import {
  autoForm,
  autoFormValid,
  markAutoFormDirty,
  paperDirty,
  paperForm,
  paperFormValid,
  pushVolumeDirty,
  pushVolumeInput,
  savingAuto,
  savingAutoTrade,
  savingDingtalkPush,
  savingLiveTimeout,
  savingPaperConfig,
  savingPaperToggle,
  savingPushConfig,
  savingScan,
  savingScope,
  savingSltpGuard,
  scanStaticSymbols,
  scopeDirty,
  scopeTimeframes,
  scopeTopN,
  scopeValid,
  staticSymbolItems,
} from '@/composables/signalsFormState'
import { useSignalsConfig } from '@/composables/useSignalsConfig'
import { useSignalsActions } from '@/composables/useSignalsActions'

// ---- core：共享状态 + 数据拉取 + 扫描/清空/轮询 ----
const {
  status,
  signals,
  config,
  pushStatus,
  tracking,
  liveExit,
  loading,
  scanning,
  clearing,
  directionFilter,
  autoTradeEnabled,
  paperEnabled,
  exitMode,
  winRateText,
  winRateTone,
  filteredSignals,
  lastAutoOpenText,
  refresh,
  scanNow,
  clearSignals,
  startPolling,
  stopPolling,
  onVisibilityChange,
} = useSignalsConfig()

// ---- actions：开关 / 保存表单 ----
const {
  onToggleScan,
  saveScanScope,
  setStaticSymbols,
  onScopeTopNChange,
  onScopeTimeframesChange,
  onPushVolumeChange,
  savePushVolume,
  onToggleDingtalkPush,
  onTogglePaper,
  onToggleLiveTimeout,
  onToggleSltpGuard,
  onChangeExitMode,
  savePaperConfig,
  onToggleAutoTrade,
  saveAutoConfig,
} = useSignalsActions()

// 支持 ?tab=scope|push|exit 深链：带着参数进来时直接展开配置抽屉并落到对应 Tab
const route = useRoute()
const configOpen = ref(['scope', 'push', 'exit'].includes(String(route.query.tab)))

onMounted(() => {
  void useSignalsConfig().fetchSignals(true)
  startPolling()
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onUnmounted(() => {
  stopPolling()
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<style scoped>
.status-strip {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.72);
}
.dot-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: 0 0 auto;
}
.dot--on {
  background: rgb(var(--v-theme-long));
  box-shadow: 0 0 0 3px rgba(var(--v-theme-long), 0.16);
}
.dot--off {
  background: rgba(var(--v-theme-on-surface), 0.34);
}
.dot--warn {
  background: rgb(var(--v-theme-warning));
  box-shadow: 0 0 0 3px rgba(var(--v-theme-warning), 0.16);
}
.signal-shell {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 12px;
}
</style>
