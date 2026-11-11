<!-- frontend/src/views/ManualTradeView.vue (手动做多/做空/反手) -->
<template>
  <div>
    <v-row>
      <v-col cols="12">
        <v-card>
          <v-card-title class="text-h6 d-flex align-center">
            <v-icon start>mdi-hand-coin-outline</v-icon>
            <span>手动交易（做多 / 做空 / 反手）</span>
          </v-card-title>
          <v-divider></v-divider>
          <v-card-text>
            <v-alert type="info" variant="tonal" density="compact" class="mb-4 text-caption">
              <div>· 所有开仓均为<strong>限价 post-only 单</strong>，不会使用市价单。</div>
              <div>· 反手 = 先按当前持仓方向<strong>全平</strong>（确认无残留）后再反向限价开仓。</div>
              <div>· 反手时若无持仓会跳过并记录 warning 日志；同一币种多空持仓并存时同样跳过。</div>
              <div>· 每行「价值」为目标名义价值（USD）；反手行的价值即反向开仓后的目标价值。</div>
              <div>· 币种列表 = 你的币种池 + 币安全部 USDT/USDC 永续，支持输入搜索，池外币种也可直接开仓。</div>
              <div>· 执行期间不可修改/提交，任务结束后会自动刷新下方持仓。</div>
            </v-alert>

            <v-row>
              <v-col cols="12" md="8">
                <v-autocomplete
                  v-model="selectedCoins"
                  :items="availableCoins"
                  label="选择币种（可多选，输入即搜索）"
                  multiple
                  chips
                  closable-chips
                  clearable
                  density="compact"
                  variant="outlined"
                  hide-details
                  :disabled="uiStore.isRunning"
                  :menu-props="coinMenuProps"
                >
                  <template v-slot:no-data>
                    <v-list-item title="没有匹配的币种" />
                  </template>
                </v-autocomplete>
              </v-col>
              <v-col cols="12" md="4">
                <v-text-field
                  v-model.number="defaultValue"
                  label="默认每币种价值 (USD)"
                  type="number"
                  min="0"
                  step="10"
                  density="compact"
                  variant="outlined"
                  hide-details
                  prefix="$"
                  :disabled="uiStore.isRunning"
                  :error="!isDefaultValueValid"
                  :messages="isDefaultValueValid ? '新增币种时自动填充该价值' : '默认价值必须大于 0'"
                ></v-text-field>
              </v-col>
            </v-row>

            <div class="d-flex flex-wrap align-center ga-2 my-3">
              <v-btn
                color="success"
                variant="tonal"
                size="small"
                prepend-icon="mdi-arrow-up-bold"
                :disabled="rows.length === 0 || uiStore.isRunning"
                @click="applyActionToAll('long')"
              >
                全部做多
              </v-btn>
              <v-btn
                color="error"
                variant="tonal"
                size="small"
                prepend-icon="mdi-arrow-down-bold"
                :disabled="rows.length === 0 || uiStore.isRunning"
                @click="applyActionToAll('short')"
              >
                全部做空
              </v-btn>
              <v-btn
                color="warning"
                variant="tonal"
                size="small"
                prepend-icon="mdi-swap-vertical-bold"
                :disabled="rows.length === 0 || uiStore.isRunning"
                @click="applyActionToAll('reverse')"
              >
                全部反手
              </v-btn>
              <v-spacer></v-spacer>
              <v-btn
                variant="text"
                size="small"
                prepend-icon="mdi-close-circle-outline"
                :disabled="rows.length === 0 || uiStore.isRunning"
                @click="clearSelection"
              >
                清空选择
              </v-btn>
            </div>

            <!-- 手机端：卡片式布局，避免 6 列表格横向溢出、动作按钮竖排 -->
            <div v-if="isMobile && rows.length > 0">
              <v-card
                v-for="row in rows"
                :key="`m-${row.symbol}`"
                variant="outlined"
                class="mb-2"
              >
                <v-card-text class="pa-3">
                  <div class="d-flex align-center flex-wrap ga-1 mb-2">
                    <span class="font-weight-medium text-body-1">{{ row.symbol }}</span>
                    <v-chip
                      v-if="resolvedSymbols[row.symbol]"
                      size="x-small"
                      variant="tonal"
                      :color="quoteColor(resolvedSymbols[row.symbol])"
                    >
                      {{ quoteLabel(resolvedSymbols[row.symbol]) }}
                    </v-chip>
                    <span v-else class="text-caption text-grey">解析中...</span>
                    <template v-if="positionsOf(row.symbol).length > 0">
                      <v-chip
                        v-for="position in positionsOf(row.symbol)"
                        :key="position.full_symbol"
                        size="x-small"
                        variant="tonal"
                        :color="position.side === 'long' ? 'success' : 'error'"
                      >
                        {{ position.side === 'long' ? '多' : '空' }}
                        ${{ formatNumber(position.notional) }}
                      </v-chip>
                    </template>
                    <span v-else class="text-caption text-grey">未持仓</span>
                    <v-spacer></v-spacer>
                    <v-btn
                      icon="mdi-close"
                      size="x-small"
                      variant="text"
                      :disabled="uiStore.isRunning"
                      @click="removeRow(row.symbol)"
                    ></v-btn>
                  </div>
                  <div class="d-flex align-center flex-wrap ga-2">
                    <div class="flex-grow-1" style="flex-basis: 100%">
                      <SmartSelect
                        v-model="row.action"
                        :items="actionOptions"
                        item-title="title"
                        item-value="value"
                        :disabled="uiStore.isRunning"
                      ></SmartSelect>
                    </div>
                    <v-text-field
                      v-model.number="row.value"
                      type="number"
                      min="0"
                      step="10"
                      density="compact"
                      variant="outlined"
                      hide-details
                      prefix="$"
                      label="价值 (USD)"
                      class="flex-grow-1"
                      style="flex-basis: 130px"
                      :error="!isRowValueValid(row)"
                      :disabled="uiStore.isRunning"
                    ></v-text-field>
                  </div>
                </v-card-text>
              </v-card>
            </div>

            <v-table
              v-else-if="rows.length > 0"
              density="compact"
              class="manual-table"
            >
              <thead>
                <tr>
                  <th class="text-left">币种</th>
                  <th class="text-left">当前持仓</th>
                  <th class="text-left" style="width: 150px">动作</th>
                  <th class="text-left" style="width: 180px">价值 (USD)</th>
                  <th class="text-left" style="width: 120px">报价</th>
                  <th class="text-right" style="width: 60px">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in rows" :key="row.symbol">
                  <td class="font-weight-medium">{{ row.symbol }}</td>
                  <td>
                    <template v-if="positionsOf(row.symbol).length === 0">
                      <span class="text-caption text-grey">未持仓</span>
                    </template>
                    <template v-else>
                      <v-chip
                        v-for="position in positionsOf(row.symbol)"
                        :key="position.full_symbol"
                        size="small"
                        variant="tonal"
                        :color="position.side === 'long' ? 'success' : 'error'"
                        class="mr-1 my-1"
                      >
                        {{ position.side === 'long' ? '多' : '空' }}
                        ${{ formatNumber(position.notional) }}
                      </v-chip>
                    </template>
                  </td>
                  <td>
                    <SmartSelect
                      v-model="row.action"
                      :items="actionOptions"
                      item-title="title"
                      item-value="value"
                      dense
                      :disabled="uiStore.isRunning"
                    ></SmartSelect>
                  </td>
                  <td>
                    <v-text-field
                      v-model.number="row.value"
                      type="number"
                      min="0"
                      step="10"
                      density="compact"
                      variant="outlined"
                      hide-details
                      prefix="$"
                      :error="!isRowValueValid(row)"
                      :disabled="uiStore.isRunning"
                    ></v-text-field>
                  </td>
                  <td>
                    <v-chip
                      v-if="resolvedSymbols[row.symbol]"
                      size="small"
                      variant="tonal"
                      :color="quoteColor(resolvedSymbols[row.symbol])"
                    >
                      {{ quoteLabel(resolvedSymbols[row.symbol]) }}
                    </v-chip>
                    <span v-else class="text-caption text-grey">解析中...</span>
                  </td>
                  <td class="text-right">
                    <v-btn
                      icon="mdi-close"
                      size="x-small"
                      variant="text"
                      :disabled="uiStore.isRunning"
                      @click="removeRow(row.symbol)"
                    ></v-btn>
                  </td>
                </tr>
              </tbody>
            </v-table>
            <v-alert v-else type="info" variant="text" density="compact" class="text-caption">
              请先选择一个或多个币种，再配置每个币种的动作与价值。
            </v-alert>

            <v-divider class="my-4"></v-divider>

            <div class="d-flex align-center flex-wrap ga-2">
            <div class="text-caption text-grey">
              共 {{ rows.length }} 个币种，预计总价值 ${{ formatNumber(totalValue) }}
              <span v-if="hasInvalidValue" class="text-error ml-2">存在非法价值，无法执行</span>
              <span v-if="hasUnavailable" class="text-error ml-2">存在不可用交易对，请先移除</span>
            </div>
            <v-spacer></v-spacer>
            <v-btn
              color="primary"
              variant="tonal"
              prepend-icon="mdi-play"
              :loading="uiStore.isRunning"
              :disabled="!canExecute"
              @click="requestExecute"
            >
              执行手动交易
            </v-btn>
          </div>
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>

  <!-- 执行前确认：反手/批量下单风险较高，强制二次确认 -->
  <v-dialog v-model="showConfirm" max-width="560">
    <v-card>
      <v-card-title class="text-h6">确认执行手动交易</v-card-title>
      <v-divider></v-divider>
      <v-card-text>
        <v-alert v-if="reverseCount > 0" type="warning" variant="tonal" density="compact" class="mb-3 text-caption">
          包含 {{ reverseCount }} 个「反手」操作：将先按当前持仓方向全平，确认无残留后再反向限价开仓。
        </v-alert>
        <div class="text-caption text-grey mb-2">
          合计 {{ rows.length }} 个币种，总名义价值 ${{ formatNumber(totalValue) }}；全部为限价 post-only 单。
        </div>
        <v-table density="compact">
          <thead>
            <tr>
              <th class="text-left">币种</th>
              <th class="text-left">动作</th>
              <th class="text-right">价值 (USD)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="`confirm-${row.symbol}`">
              <td>{{ row.symbol }}</td>
              <td>{{ actionTitle(row.action) }}</td>
              <td class="text-right">${{ formatNumber(Number(row.value)) }}</td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="showConfirm = false">取消</v-btn>
        <v-btn color="primary" variant="tonal" @click="executeManualTrade">确认执行</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

    <v-row class="mt-2">
      <v-col cols="12">
        <PnlSummary />
      </v-col>
    </v-row>

    <v-row>
      <v-col cols="12">
        <PositionsTable
          title="▲ 多头仓位"
          side="long"
          :positions="positionStore.longPositions"
          :loading="positionStore.loading"
          @refresh="positionStore.fetchPositions()"
        />
      </v-col>
    </v-row>

    <v-row>
      <v-col cols="12">
        <PositionsTable
          title="▼ 空头仓位"
          side="short"
          :positions="positionStore.shortPositions"
          :loading="positionStore.loading"
          @refresh="positionStore.fetchPositions()"
        />
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { useSettingsStore } from '@/stores/settingsStore'
import { usePositionStore } from '@/stores/positionStore'
import { useUiStore } from '@/stores/uiStore'
import api from '@/services/api'
import type {
  ManualTradeAction,
  ManualTradeItem,
  ManualTradePreset,
  Position,
  ResolveSymbolsResponse,
  ResolvedSymbol,
} from '@/models/types'
import { getErrorMessage } from '@/utils/errors'
import { formatAmount as formatNumber } from '@/utils/format'
import { debounce } from '@/utils/debounce'
import PnlSummary from '@/components/PnlSummary.vue'
import PositionsTable from '@/components/PositionsTable.vue'
import SmartSelect from '@/components/SmartSelect.vue'

interface ManualRow {
  symbol: string
  action: ManualTradeAction
  value: number
}

const uiStore = useUiStore()
const settingsStore = useSettingsStore()
const positionStore = usePositionStore()
const { smAndDown } = useDisplay()
const isMobile = computed(() => smAndDown.value)
// 手机端下拉限高 45vh（防止铺满全屏），桌面端用固定 420px（矮窗口下 vh 会把菜单压扁）
const coinMenuProps = computed(() =>
  isMobile.value ? { maxHeight: '45vh' } : { maxHeight: '420px' },
)

const actionOptions: { title: string; value: ManualTradeAction }[] = [
  { title: '做多', value: 'long' },
  { title: '做空', value: 'short' },
  { title: '反手', value: 'reverse' },
]

const selectedCoins = ref<string[]>([])
const rows = ref<ManualRow[]>([])
const defaultValue = ref(100)
const resolvedSymbols = ref<Record<string, ResolvedSymbol>>({})
// 交易所全部可交易 USDⓈ-M 基础币种（进入页面时拉取一次；失败时回退为仅币种池）
const exchangeCoins = ref<string[]>([])

let resolveSequence = 0
// 持久化预设：是否已完成恢复、是否正在保存（防止恢复过程触发回写）
let presetHydrated = false
let presetSaving = false

// ---- 持久化：恢复 + 防抖自动保存（存后端 SQLite，跨浏览器/设备生效） ----
const PRESET_MAX_ROWS = 100

const sanitizePreset = (): ManualTradePreset => {
  const validRows = rows.value
    .filter((row) => typeof row.symbol === 'string' && row.symbol)
    .slice(0, PRESET_MAX_ROWS)
    .map((row) => ({
      symbol: row.symbol,
      action: row.action,
      value: Number.isFinite(Number(row.value)) ? Number(row.value) : 0,
    }))
  return {
    selected_coins: selectedCoins.value.slice(0, PRESET_MAX_ROWS),
    rows: validRows,
    default_value: Number(defaultValue.value) || 0,
  }
}

const savePreset = async (): Promise<void> => {
  if (!presetHydrated || presetSaving) return
  presetSaving = true
  try {
    // 通过 store 统一写入：同时更新内存副本，避免其它页面保存整包设置时把旧预设写回
    await settingsStore.patchSettings({ manual_trade_preset: sanitizePreset() })
  } catch (error: unknown) {
    console.warn('保存手动交易预设失败:', getErrorMessage(error))
  } finally {
    presetSaving = false
  }
}

const savePresetDebounced = debounce(savePreset, 800)

const restorePreset = async (): Promise<void> => {
  try {
    if (!settingsStore.settings) {
      await settingsStore.fetchSettings()
    }
  } catch {
    // 获取失败时仍允许页面正常使用（空选择）
    presetHydrated = true
    return
  }
  const preset = settingsStore.settings?.manual_trade_preset
  if (preset && typeof preset === 'object') {
    const coins = Array.isArray(preset.selected_coins) ? preset.selected_coins : []
    const savedRows = Array.isArray(preset.rows) ? preset.rows : []
    const rowMap = new Map(
      savedRows
        .filter((row) => row && typeof row.symbol === 'string')
        .map((row) => [row.symbol, row]),
    )
    const restored = coins
      .filter((symbol) => typeof symbol === 'string')
      .map((symbol) => {
        const saved = rowMap.get(symbol)
        return {
          symbol,
          action: (saved?.action ?? 'long') as ManualTradeAction,
          value: Number.isFinite(Number(saved?.value)) && Number(saved?.value) > 0
            ? Number(saved?.value)
            : (Number(preset.default_value) > 0 ? Number(preset.default_value) : 100),
        }
      })
    // 保留用户已删除出选择但 rows 中仍有记录的币种不恢复（以 selected_coins 为准）
    if (Number(preset.default_value) > 0) {
      defaultValue.value = Number(preset.default_value)
    }
    rows.value = restored
    selectedCoins.value = [...coins]
  }
  presetHydrated = true
}

// 可选币种 = 总池（为空时合并多/空备选池）∪ 交易所全部 USDⓈ-M 永续
const availableCoins = computed(() => {
  const pool =
    settingsStore.availableCoins.length > 0
      ? settingsStore.availableCoins
      : [...settingsStore.availableLongCoins, ...settingsStore.availableShortCoins]
  return [...new Set([...pool, ...exchangeCoins.value])].sort()
})

const isDefaultValueValid = computed(() => {
  const value = Number(defaultValue.value)
  return Number.isFinite(value) && value > 0
})

const isRowValueValid = (row: ManualRow): boolean => {
  const value = Number(row.value)
  return Number.isFinite(value) && value > 0
}

const hasInvalidValue = computed(() => rows.value.some((row) => !isRowValueValid(row)))

// 交易对不可用（如币安无该合约 / 解析失败）时禁止提交，避免后端逐条失败产生部分成交
const hasUnavailable = computed(() =>
  rows.value.some((row) => {
    const resolved = resolvedSymbols.value[row.symbol]
    return !!resolved && !resolved.available
  }),
)

const canExecute = computed(
  () =>
    rows.value.length > 0 &&
    !hasInvalidValue.value &&
    !hasUnavailable.value &&
    !uiStore.isRunning,
)

const showConfirm = ref(false)

const reverseCount = computed(() => rows.value.filter((row) => row.action === 'reverse').length)

const actionTitle = (action: ManualTradeAction): string =>
  actionOptions.find((option) => option.value === action)?.title ?? action

const requestExecute = (): void => {
  if (!canExecute.value) return
  showConfirm.value = true
}

const totalValue = computed(() =>
  rows.value.reduce((sum, row) => (isRowValueValid(row) ? sum + Number(row.value) : sum), 0),
)

const positionsOf = (symbol: string): Position[] =>
  positionStore.positions.filter(
    (position) => position.symbol.toUpperCase() === symbol.toUpperCase(),
  )

const quoteLabel = (resolved: ResolvedSymbol | undefined): string => {
  if (!resolved) return '解析中...'
  if (!resolved.available) return '不可用'
  return resolved.quote ?? '未知'
}

const quoteColor = (resolved: ResolvedSymbol | undefined): string => {
  if (!resolved || !resolved.available) return 'grey'
  return resolved.quote === 'USDC' ? 'teal' : 'blue-grey'
}

const defaultRowValue = (): number => {
  const value = Number(defaultValue.value)
  return Number.isFinite(value) && value > 0 ? value : 0
}

const fetchResolvedSymbols = async (): Promise<void> => {
  const symbols = [...selectedCoins.value]
  if (symbols.length === 0) {
    resolvedSymbols.value = {}
    return
  }
  const sequence = ++resolveSequence
  try {
    const response = await api.get<ResolveSymbolsResponse>('/api/trading/resolve-symbols', {
      params: { symbols: symbols.join(',') },
    })
    if (sequence !== resolveSequence) return
    const map: Record<string, ResolvedSymbol> = {}
    for (const entry of response.data.symbols) {
      map[entry.symbol] = entry
    }
    resolvedSymbols.value = map
  } catch (error: unknown) {
    if (sequence !== resolveSequence) return
    console.warn('解析交易对失败:', getErrorMessage(error))
  }
}

const applyActionToAll = (action: ManualTradeAction): void => {
  rows.value.forEach((row) => {
    row.action = action
  })
}

const clearSelection = (): void => {
  selectedCoins.value = []
}

const removeRow = (symbol: string): void => {
  selectedCoins.value = selectedCoins.value.filter((coin) => coin !== symbol)
}

const executeManualTrade = (): void => {
  if (!canExecute.value) return
  const items: ManualTradeItem[] = rows.value.map((row) => ({
    symbol: row.symbol,
    action: row.action,
    value: Number(row.value),
  }))
  // default_value 非法时不传递（后端每条 item 都已有显式 value），避免提交无效默认值
  const payload: { items: ManualTradeItem[]; default_value?: number } = { items }
  if (isDefaultValueValid.value) {
    payload.default_value = Number(defaultValue.value)
  }
  showConfirm.value = false
  uiStore.launchTask('/api/trading/manual', payload, '手动交易', items.length)
}

// 选中币种变化时：已选币种保留原有动作与价值，新币种按默认价值初始化
watch(selectedCoins, (coins) => {
  const existing = new Map(rows.value.map((row) => [row.symbol, row]))
  rows.value = coins.map(
    (symbol) =>
      existing.get(symbol) ?? {
        symbol,
        action: 'long' as ManualTradeAction,
        value: defaultRowValue(),
      },
  )
  void fetchResolvedSymbols()
})

// 默认价值变化时，仅补充尚未填写有效价值的行
watch(defaultValue, () => {
  const fallback = defaultRowValue()
  if (!fallback) return
  rows.value.forEach((row) => {
    if (!isRowValueValid(row)) {
      row.value = fallback
    }
  })
})

// 持久化：币种/动作/价值/默认价值任一变化后防抖自动保存
watch(selectedCoins, () => {
  if (presetHydrated) savePresetDebounced()
})
watch(
  rows,
  () => {
    if (presetHydrated) savePresetDebounced()
  },
  { deep: true },
)
watch(defaultValue, () => {
  if (presetHydrated) savePresetDebounced()
})

// 任务结束后自动刷新持仓
watch(
  () => uiStore.isRunning,
  (running, previous) => {
    if (previous && !running) {
      void positionStore.fetchPositions()
    }
  },
)

const fetchExchangeCoins = async (): Promise<void> => {
  try {
    const response = await api.get<{ coins: string[] }>('/api/trading/symbols')
    exchangeCoins.value = Array.isArray(response.data.coins) ? response.data.coins : []
  } catch (error: unknown) {
    // 拉取失败不阻塞页面：回退为仅显示币种池
    console.warn('获取交易所币种列表失败，仅使用币种池:', getErrorMessage(error))
  }
}

onMounted(() => {
  void restorePreset()
  void fetchExchangeCoins()
  if (positionStore.positions.length === 0) {
    void positionStore.fetchPositions()
  }
})
</script>

<style scoped>
.manual-table :deep(th) {
  white-space: nowrap;
}
.manual-table :deep(td) {
  vertical-align: middle;
}
</style>
