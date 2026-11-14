<!-- frontend/src/views/TradingView.vue -->
<!-- 首屏职责：盯仓 / 开仓 / 平仓（规格 §1.2）。
     区块顺序：盈亏条 → 多空持仓表（lg 双列 6:6）→ 开仓记录；
     64 个开仓参数控件整体移入共享的 ConfigDrawer。
     dock 只留一个「开仓」入口：点进去即见配置 + 摘要 + 两个动作，
     不再「选币 → 关面板 → 再点开仓」来回跳。 -->
<template>
  <div>
    <!-- 未配置提示：多空币种列表均为空时引导先去抽屉里配置（可关闭，本次会话不再出现） -->
    <v-alert
      v-if="showSetupHint"
      type="info"
      variant="tonal"
      density="compact"
      class="mb-3"
      closable
      @click:close="setupHintDismissed = true"
    >
      <span
        class="setup-hint-link"
        role="button"
        tabindex="0"
        @click="openConfig"
        @keydown.enter.prevent="openConfig"
      >
        还没配置开仓参数，先设置币种与金额 →
      </span>
    </v-alert>

    <!-- 盈亏条 -->
    <PnlSummary />

    <!-- 多空持仓：lg 双列 6:6，<lg 纵向。反手 / 平仓都在每张表的行上操作 -->
    <v-row>
      <v-col cols="12" lg="6">
        <PositionsTable
          title="▲ 多头仓位"
          side="long"
          :positions="positionStore.longPositions"
          :loading="positionStore.loading"
          @refresh="positionStore.fetchPositions()"
        />
      </v-col>
      <v-col cols="12" lg="6">
        <PositionsTable
          title="▼ 空头仓位"
          side="short"
          :positions="positionStore.shortPositions"
          :loading="positionStore.loading"
          @refresh="positionStore.fetchPositions()"
        />
      </v-col>
    </v-row>

    <!-- 开仓记录：选币快照 + 每笔开仓结果（自动/信号/手动/再平衡共用台账） -->
    <v-row>
      <v-col cols="12">
        <OpenHistoryPanel />
      </v-col>
    </v-row>
  </div>

  <!-- 固定操作条：全页只有一个入口。运行中也保持可点 ——
       用户需要能进去看配置，真正该禁用的是抽屉里的动作按钮。 -->
  <AppDockFooter>
    <v-btn
      ref="openConfigBtn"
      variant="flat"
      color="primary"
      prepend-icon="mdi-tune-vertical"
      height="44"
      min-width="168"
      @click="openConfig"
    >
      开仓
    </v-btn>
    <HelpTip :text="HELP.trading.btnOpenDock" />
  </AppDockFooter>

  <!-- 共享参数抽屉（与信号页复用同一个 ConfigDrawer，禁止各写一套） -->
  <ConfigDrawer v-model="configOpen" title="开仓设置" icon="mdi-tune-vertical" :tabs="configTabs">
    <template #general>
      <ControlPanel section="general" />
    </template>
    <template #rebalance>
      <ControlPanel
        section="rebalance"
        :is-generating-plan="isGeneratingPlan"
        @generate-rebalance="onGenerateRebalancePlan"
      />
    </template>

    <!-- 抽屉动作区：常驻在滚动区之外，任何 Tab 下都可见。
         摘要读草稿（刚改的币种/金额立刻反映），动作提交的才是服务端配置。 -->
    <template #actions>
      <div class="d-flex flex-column flex-md-row align-md-center ga-2 w-100">
        <div class="open-summary flex-grow-1">
          <div class="open-summary__line">
            <span class="open-summary__counts">
              <span class="open-summary__count text-long">多 {{ compactCount(longCount) }}</span>
              <span class="open-summary__sep"> · </span>
              <span class="open-summary__count text-short">空 {{ compactCount(shortCount) }}</span>
              <span class="open-summary__sep"> · 总价值 </span>
              <span class="open-summary__count">{{ totalValueText }}</span>
            </span>
            <span class="open-summary__sep"> · </span>
            <!-- 保存状态：变化时播报（读屏用户看不到黄点）。
                 「已保存」三个字只给读屏，视觉上只留时钟 —— 动作区的横向空间
                 被两个按钮吃掉大半，留前缀会把时钟挤成省略号。 -->
            <span class="open-summary__state" aria-live="polite">
              <template v-if="isDirty">
                <span class="open-summary__dot" aria-hidden="true"></span>
                <span class="text-warning">未保存</span>
              </template>
              <template v-else-if="lastSavedAt">
                <span class="d-sr-only">已保存 </span>{{ formatClockTime(lastSavedAt) }}
              </template>
              <template v-else>未保存过</template>
            </span>
          </div>
          <div
            v-if="actionHint"
            id="open-action-hint"
            class="text-caption text-medium-emphasis mt-1"
          >
            {{ actionHint }}
          </div>
        </div>

        <div class="open-actions d-flex ga-2">
          <v-btn
            variant="tonal"
            color="info"
            prepend-icon="mdi-check-circle-outline"
            height="44"
            min-width="112"
            :disabled="calibrateDisabled"
            :aria-label="calibrateAriaLabel"
            aria-describedby="open-action-hint"
            @click="syncSlTp"
          >
            校准 SL/TP
          </v-btn>
          <HelpTip :text="HELP.trading.btnCalibrate" />
          <v-btn
            class="open-pos-btn"
            variant="flat"
            color="success"
            height="44"
            min-width="152"
            :loading="submitting"
            :disabled="openDisabled"
            :aria-label="openAriaLabel"
            aria-describedby="open-action-hint"
            @click="startTrading"
          >
            开始开仓
          </v-btn>
          <HelpTip :text="HELP.trading.btnStart" />
        </div>
      </div>
    </template>
  </ConfigDrawer>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import type { VBtn } from 'vuetify/components'
import { useUiStore } from '@/stores/uiStore'
import { usePositionStore } from '@/stores/positionStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { useSnackbarStore } from '@/stores/snackbar'
import { useDraftSettings } from '@/composables/useDraftSettings'
import ControlPanel from '@/components/ControlPanel.vue'
import PositionsTable from '@/components/PositionsTable.vue'
import PnlSummary from '@/components/PnlSummary.vue'
import OpenHistoryPanel from '@/components/OpenHistoryPanel.vue'
import AppDockFooter from '@/components/AppDockFooter.vue'
import ConfigDrawer from '@/components/ConfigDrawer.vue'
import HelpTip from '@/components/HelpTip.vue'
import { HELP } from '@/config/help'
import apiClient from '@/services/api'
import { ENDPOINTS } from '@/services/endpoints'
import type { RebalanceCriteria, UserSettings } from '@/models/types'
import { getErrorMessage } from '@/utils/errors'
import { formatClockTime, formatUsdCompact } from '@/utils/format'

const configTabs = [
  { key: 'general', title: '通用开仓设置', icon: 'mdi-tune-vertical' },
  { key: 'rebalance', title: '智能再平衡', icon: 'mdi-calendar-refresh' },
]

const uiStore = useUiStore()
const positionStore = usePositionStore()
const settingsStore = useSettingsStore()
const snackbarStore = useSnackbarStore()
// 动作区摘要读草稿：刚改的币种/金额立刻反映在摘要里，不用等防抖保存回写 store。
// 注意 commitDraft 与 ControlPanel 是同一份模块级单例，动作与表单不会互相打架。
const { draft, hydrated, isDirty, lastSavedAt, commitDraft } = useDraftSettings()

const configOpen = ref(false)
const isGeneratingPlan = ref(false)
/** 动作进行中（保存草稿 + 提交任务）：两个动作按钮共用，防连点重复提交 */
const submitting = ref(false)
/** dock 上的「开仓」按钮：抽屉关闭后把焦点还回去（键盘用户不丢位置） */
const openConfigBtn = ref<InstanceType<typeof VBtn> | null>(null)

const openConfig = () => {
  configOpen.value = true
}

// ---- 抽屉动作区：摘要 ----
const longCount = computed(() =>
  draft.value?.enable_long_trades ? (draft.value.long_coin_list?.length ?? 0) : 0,
)
const shortCount = computed(() =>
  draft.value?.enable_short_trades ? (draft.value.short_coin_list?.length ?? 0) : 0,
)
const coinCount = computed(() => longCount.value + shortCount.value)

/** 摘要条只有一行：>99 个币压成 99+，别把「未保存」挤出可视区 */
const compactCount = (count: number) => (count > 99 ? '99+' : String(count))

/**
 * 启用方向的总价值。任一启用方向的值是空串/NaN（输入框被清空）时返回 null，
 * 界面显示「—」，但**不禁用**开仓：diffKeys 会跳过这些非法键，服务端保留旧值。
 */
const totalValue = computed<number | null>(() => {
  const current = draft.value
  if (!current) return null
  const values: number[] = []
  if (current.enable_long_trades) values.push(Number(current.total_long_position_value))
  if (current.enable_short_trades) values.push(Number(current.total_short_position_value))
  if (values.length === 0) return null
  if (values.some((value) => !Number.isFinite(value))) return null
  return values.reduce((sum, value) => sum + value, 0)
})

const totalValueText = computed(() =>
  totalValue.value === null ? '—' : formatUsdCompact(totalValue.value),
)

/**
 * 动作不可用的原因，按「用户能不能自己解决」排序：
 * 运行中 > 保存中 > 加载中 > 没选币 > 没持仓（后者只影响校准）。
 * 两个按钮都 aria-describedby 到这里，禁用原因不只有视觉这一条通道。
 */
const actionHint = computed(() => {
  if (uiStore.isRunning) return '有任务正在运行，完成后可再开仓'
  if (submitting.value) return '正在保存配置…'
  if (!hydrated.value) return '正在加载配置…'
  if (coinCount.value === 0) return '未选择币种：先开启多头/空头并选币'
  if (positionStore.positions.length === 0) return '暂无持仓，校准只作用于已有仓位'
  return ''
})

const busy = computed(() => uiStore.isRunning || submitting.value)
const openDisabled = computed(() => busy.value || !hydrated.value || coinCount.value === 0)
const calibrateDisabled = computed(
  () => busy.value || !hydrated.value || positionStore.positions.length === 0,
)

const openAriaLabel = computed(() => {
  const total = totalValue.value === null ? '未知' : `${formatUsdCompact(totalValue.value)} 美元`
  return `开始开仓，多头 ${longCount.value} 个币、空头 ${shortCount.value} 个币、总价值 ${total}`
})
const calibrateAriaLabel = computed(
  () => `校准 SL/TP，作用于 ${positionStore.positions.length} 个持仓`,
)

// ---- 动作 ----
/**
 * 提交草稿。刻意**不**先 flushDraftSave()：debounce.flush() 会同步触发内部的
 * void commitDraft() 把 commitInFlight 置位，紧随的 await commitDraft() 会因
 * in-flight 直接返回 false（假失败）。diff 基于 draft vs baseline，防抖窗口内的
 * 编辑本来就在 draft 里，一次提交全覆盖。
 *
 * commitDraft 返回 false 有两种成因：① 真·提交失败（服务端拒绝/网络，commitDraft
 * 已弹过 snackbar）；② 另一路（防抖自动保存）的提交正在飞，被 commitInFlight 挡掉。
 * 用 isDirty 区分：已经无差异说明状态已落库（或本来就没差异），算成功；仍有差异
 * 则是被 in-flight 挡掉，等一拍再试一次 —— **只重试一次，不递归**，避免把等待放大。
 */
const ensureSaved = async (): Promise<boolean> => {
  if (await commitDraft()) return true
  if (!isDirty.value) return true
  await new Promise((resolve) => setTimeout(resolve, 150))
  return (await commitDraft()) || !isDirty.value
}

/**
 * 两个动作共用的外壳：同步置位 submitting → 提交草稿 → 二次守卫 → 执行 → 复位。
 * submitting 必须在第一个 await 之前置位，否则连点两下会各自提交一次。
 * 保存失败不在这里弹提示：commitDraft 已经弹过服务端原因的 snackbar，这里只复位，
 * 抽屉保持打开、草稿保留，用户改完可以再点。
 */
const runAction = async (options: { canRun: () => boolean; run: () => void }): Promise<void> => {
  if (submitting.value) return
  submitting.value = true
  const saved = await ensureSaved()
  if (!saved) {
    submitting.value = false
    return
  }
  // 保存期间可能别的入口把任务跑起来了：二次确认，避免白提交一个被后端拒绝的请求
  if (!uiStore.isRunning && options.canRun()) options.run()
  submitting.value = false
}

/** 校准 payload：只取止损/止盈/移动止盈/杠杆相关键（与 /trading/sync-sltp 契约一致） */
const buildSltpPayload = (plan: UserSettings) => {
  const {
    enable_long_sl_tp,
    long_stop_loss_percentage,
    long_take_profit_percentage,
    enable_short_sl_tp,
    short_stop_loss_percentage,
    short_take_profit_percentage,
    // --- 移动止盈参数 ---
    enable_long_trailing_stop,
    long_trailing_stop_callback_rate,
    enable_short_trailing_stop,
    short_trailing_stop_callback_rate,
    // -------------------
    leverage,
  } = plan

  return {
    enable_long_sl_tp,
    long_stop_loss_percentage,
    long_take_profit_percentage,
    enable_short_sl_tp,
    short_stop_loss_percentage,
    short_take_profit_percentage,
    enable_long_trailing_stop,
    long_trailing_stop_callback_rate,
    enable_short_trailing_stop,
    short_trailing_stop_callback_rate,
    leverage,
  }
}

const startTrading = () => {
  void runAction({
    canRun: () => coinCount.value > 0,
    run: () => {
      const plan = settingsStore.settings
      if (!plan) return
      // payload 必须是服务端 settings：草稿里可能有 ''/NaN（diffKeys 会跳过、服务端保留
      // 旧值），直接发草稿等于把非法值原样带出去。
      uiStore.launchTask(ENDPOINTS.tradingStart, plan, '自动开仓', coinCount.value)
      // launchTask 是 fire-and-forget（不能 await）：立刻收起抽屉，把视线还给持仓表
      configOpen.value = false
      void nextTick(() => openConfigBtn.value?.$el?.focus())
    },
  })
}

const syncSlTp = () => {
  void runAction({
    canRun: () => positionStore.positions.length > 0,
    run: () => {
      const plan = settingsStore.settings
      if (!plan) return
      uiStore.launchTask(
        ENDPOINTS.tradingSyncSltp,
        buildSltpPayload(plan),
        '同步SL/TP/移动止盈',
        positionStore.positions.length,
      )
      // 校准只把参数推给已有仓位，抽屉保持打开让用户继续核对配置
      snackbarStore.show({ message: '已提交校准，结果见进度条', color: 'info', timeout: 3000 })
    },
  })
}

// 首次进入且多空币种列表都为空时提示去配置；关闭后本次会话不再打扰
const setupHintDismissed = ref(false)
const showSetupHint = computed(
  () =>
    !setupHintDismissed.value &&
    !!settingsStore.settings &&
    settingsStore.settings.long_coin_list.length === 0 &&
    settingsStore.settings.short_coin_list.length === 0,
)

const onGenerateRebalancePlan = () => {
  if (settingsStore.settings) {
    const criteria: RebalanceCriteria = {
      method: settingsStore.settings.rebalance_method,
      top_n: settingsStore.settings.rebalance_top_n,
      min_volume_usd: settingsStore.settings.rebalance_min_volume_usd,
      abs_momentum_days: settingsStore.settings.rebalance_abs_momentum_days,
      rel_strength_days: settingsStore.settings.rebalance_rel_strength_days,
      rebalance_volume_ma_days: settingsStore.settings.rebalance_volume_ma_days,
      rebalance_volume_spike_ratio: settingsStore.settings.rebalance_volume_spike_ratio,
      rebalance_benchmark_coin: settingsStore.settings.rebalance_benchmark_coin,
      enable_rebalance_filters: settingsStore.settings.enable_rebalance_filters,
      rebalance_rsi_period: settingsStore.settings.rebalance_rsi_period,
      rebalance_rsi_threshold: settingsStore.settings.rebalance_rsi_threshold,
      rebalance_short_term_momentum_days: settingsStore.settings.rebalance_short_term_momentum_days,
      rebalance_short_term_momentum_threshold: settingsStore.settings.rebalance_short_term_momentum_threshold,
      rebalance_bollinger_period: settingsStore.settings.rebalance_bollinger_period,
      rebalance_bollinger_std_dev: settingsStore.settings.rebalance_bollinger_std_dev,
      rebalance_bollinger_width_spike_ratio: settingsStore.settings.rebalance_bollinger_width_spike_ratio,
    }
    handleGenerateRebalancePlan(criteria)
  }
}

const handleGenerateRebalancePlan = async (criteria: RebalanceCriteria) => {
  if (uiStore.isRunning || isGeneratingPlan.value) return
  isGeneratingPlan.value = true
  uiStore.logStore.addLog({
    message: '[前端] 正在生成再平衡计划...',
    level: 'info',
    timestamp: new Date().toLocaleTimeString(),
  })
  try {
    const response = await apiClient.post(ENDPOINTS.rebalancePlan, criteria)
    const planData = response.data
    if (planData.error) {
      uiStore.logStore.addLog({
        message: `计划生成逻辑错误: ${planData.error}`,
        level: 'error',
        timestamp: new Date().toLocaleTimeString(),
      })
    } else {
      uiStore.rebalancePlan = planData
      uiStore.showRebalanceDialog = true
    }
  } catch (error: unknown) {
    const errorMsg = getErrorMessage(error)
    uiStore.logStore.addLog({
      message: `[后端] ❌ 生成计划请求失败: ${errorMsg}`,
      level: 'error',
      timestamp: new Date().toLocaleTimeString(),
    })
  } finally {
    isGeneratingPlan.value = false
  }
}

onMounted(() => {
  if (positionStore.positions.length === 0) {
    positionStore.fetchPositions()
  }
})
</script>

<style scoped>
.setup-hint-link {
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
}

/* ---------------- 抽屉动作区 ---------------- */

/* 摘要条只占一行：min-width:0 是 flex 子项能被压缩（从而出省略号）的前提 */
.open-summary {
  min-width: 0;
}

.open-summary__line {
  display: flex;
  align-items: baseline;
  min-width: 0;
  font-size: 14px;
  line-height: 1.5;
}

/* 币数 / 总价值这段参与压缩：宽度不够时出省略号（抽屉里只有 ~200px 可用） */
.open-summary__counts {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

/* 保存状态这段不压缩：时钟被切成「14:0…」比末尾省略号更难读，
   空间紧张时优先牺牲前面那段摘要 */
.open-summary__state {
  flex: 0 0 auto;
  white-space: nowrap;
}

.open-summary__count {
  font-weight: 600;
}

.open-summary__sep {
  color: rgba(var(--v-theme-on-surface), 0.6);
}

/* 未保存：黄点 + 文字。只用颜色区分对色弱不友好，所以点后面跟着「未保存」三个字 */
.open-summary__dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 4px;
  border-radius: 50%;
  vertical-align: middle;
  background: rgb(var(--v-theme-warning));
}

/* 主按钮：Vuetify flat + color=success 的底色压不住白字（浅色主题只有 3.4:1），
   改用主题里专为实心按钮准备的低亮度 success-strong（check-contrast 会守住它）。
   !important 用于压过 Vuetify 内联的 flat 背景色。 */
.open-pos-btn {
  background: rgb(var(--v-theme-success-strong)) !important;
  color: rgb(var(--v-theme-on-success-strong)) !important;
}

/* 手机断点（与 base.css 的 960px 对齐）：两个动作换行后各占一半宽度，
   高度抬到 48 保证拇指命中率；desktop 保持 44 */
@media (max-width: 959px) {
  .open-actions > .v-btn {
    flex: 1 1 0;
    height: 48px !important;
  }
}
</style>
