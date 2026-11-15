<!-- frontend/src/components/WeightConfigDialog.vue -->
<!-- 多头权重：显示「实际生效的分配」，保存即落库，并与币种清单同一次请求提交。
     口径（2026-11-15 用户要求）：默认为均分；只有手动改过才按改的比例。
     旧版两个坑：
     1) 没保存过权重时，弹窗自己算均分展示，后端却按 BTC 40% / ETH 30% 分配 —— 界面在撒谎；
     2) 权重按币名单独存，换清单不同步，旧权重会串到新清单上（全对不上就退回 40/30）。
     现在：两侧共用 reconcileWeights（与后端同一套规则），键集合 = 当前清单、合计 100。 -->
<template>
  <v-dialog v-model="show" max-width="520px" persistent>
    <v-card>
      <v-card-title>
        <span class="text-h5">配置多头权重</span>
      </v-card-title>
      <v-card-text>
        <p class="text-caption mb-3">
          未修改的币种默认均分；手动改一个后，其余未改过的币均分剩余比例。总和必须为 100%。
        </p>

        <v-form ref="form">
          <v-row v-for="coin in localWeights" :key="coin.symbol" class="align-center">
            <v-col cols="4">
              <v-label>{{ coin.symbol }}</v-label>
            </v-col>
            <v-col cols="8">
              <v-text-field
                v-model.number="coin.weight"
                @input="recalculateWeights(coin.symbol)"
                type="number"
                variant="outlined"
                density="compact"
                suffix="%"
                hide-details
              >
                <template #append-inner>
                  <HelpTip :text="HELP.dialog.weightInput" />
                </template>
              </v-text-field>
            </v-col>
          </v-row>
        </v-form>
        <v-divider class="my-4"></v-divider>
        <div class="d-flex justify-space-between">
          <span class="font-weight-bold">总权重:</span>
          <span :class="Math.abs(totalWeight - 100) < 0.001 ? 'text-success' : 'text-error'">
            {{ formatFixed(totalWeight, 2) }} %
          </span>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-btn color="primary" variant="text" @click="fillEven">均分权重</v-btn>
        <HelpTip :text="HELP.dialog.weightAverage" />
        <v-spacer></v-spacer>
        <v-btn color="blue-darken-1" variant="text" :disabled="saving" @click="close">取消</v-btn>
        <v-btn
          color="blue-darken-1"
          variant="tonal"
          :loading="saving"
          @click="save"
          :disabled="Math.abs(totalWeight - 100) > 0.001"
          >保存</v-btn
        >
        <HelpTip :text="HELP.dialog.weightSave" />
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed, nextTick } from 'vue'
import { useSettingsStore } from '@/stores/settingsStore'
import { useSnackbarStore } from '@/stores/snackbar'
import { useDraftSettings } from '@/composables/useDraftSettings'
import { formatFixed, roundTo } from '@/utils/format'
import { reconcileWeights } from '@/utils/weights'
import HelpTip from '@/components/HelpTip.vue'
import { HELP } from '@/config/help'

const props = defineProps<{
  modelValue: boolean
}>()
const emit = defineEmits(['update:modelValue'])

const settingsStore = useSettingsStore()
const snackbarStore = useSnackbarStore()
// 与开仓表单共用同一份草稿：权重和「总价值」必须写在同一个缓冲里，
// 否则一边改了另一边不知道，保存时会被 diff 漏掉
const { draft, commitDraft } = useDraftSettings()

const localWeights = ref<{ symbol: string; weight: number }[]>([])
const manuallyEdited = ref<Set<string>>(new Set())
const saving = ref(false)
let isRecalculating = false

const show = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

const totalWeight = computed(() => {
  return localWeights.value.reduce((sum, item) => sum + (Number(item.weight) || 0), 0)
})

// --- 这是最终的、简单且正确的重新计算逻辑 ---
const recalculateWeights = (editedSymbol: string) => {
  if (isRecalculating) return
  isRecalculating = true

  // 核心修正：只有在值发生变动时，才将该项加入“手动编辑”列表
  manuallyEdited.value.add(editedSymbol)

  const unassignedItems = localWeights.value.filter(
    (item) => !manuallyEdited.value.has(item.symbol),
  )

  const lockedTotal = localWeights.value
    .filter((item) => manuallyEdited.value.has(item.symbol))
    .reduce((sum, item) => sum + (Number(item.weight) || 0), 0)

  if (unassignedItems.length > 0) {
    const remainingTotal = 100 - lockedTotal
    distribute(remainingTotal >= 0 ? remainingTotal : 0, unassignedItems)
  } else if (Math.abs(totalWeight.value - 100) > 0.001) {
    const lastItem =
      localWeights.value.find((item) => item.symbol !== editedSymbol) || localWeights.value[0]
    if (lastItem) {
      const diff = 100 - totalWeight.value
      lastItem.weight = roundTo((Number(lastItem.weight) || 0) + diff, 2)
    }
  }

  nextTick(() => {
    isRecalculating = false
  })
}

// 精确的分配函数
const distribute = (total: number, items: { symbol: string; weight: number }[]) => {
  const count = items.length
  if (count === 0) return

  const avg = total / count
  let accumulatedWeight = 0

  items.forEach((item, index) => {
    if (index === count - 1) {
      item.weight = roundTo(total - accumulatedWeight, 2)
    } else {
      const w = roundTo(avg, 2)
      item.weight = w
      accumulatedWeight += w
    }
  })
}

/** 「均分权重」：清空所有锁定，每个币等额（显式写成数字，与后端默认口径一致） */
const fillEven = () => {
  manuallyEdited.value.clear()
  const coins = localWeights.value.map((item) => item.symbol)
  const weights = reconcileWeights(coins, {})
  localWeights.value.forEach((item) => {
    item.weight = weights[item.symbol] ?? item.weight
  })
}

const currentSettings = () => draft.value ?? settingsStore.settings

const initWeights = () => {
  const current = currentSettings()
  manuallyEdited.value.clear()
  const selectedCoins = current?.long_coin_list ?? []
  // 展示的就是「实际会用的那份」：有自定义权重按自定义来（对不上清单的键丢弃、
  // 清单内的新币按剩余比例均分），一个都对不上或没设过就是均分。
  // 与后端 reconcile_weights 同一套规则，界面不再有第二套默认值。
  const weights = reconcileWeights(selectedCoins, current?.long_custom_weights)
  localWeights.value = selectedCoins.map((coin) => ({
    symbol: coin,
    weight: weights[coin] ?? 0,
  }))
}

const save = async () => {
  if (Math.abs(totalWeight.value - 100) > 0.001) return
  const newWeights: { [key: string]: number } = {}
  localWeights.value.forEach((item) => {
    newWeights[item.symbol] = Number(item.weight) || 0
  })

  saving.value = true
  try {
    if (draft.value) {
      // 写草稿 + 立即提交：走的是与「保存」按钮同一条落库通道。
      // 权重必须和清单同一次请求提交（alwaysInclude），否则服务端只能猜这份权重
      // 是给哪个清单配的 —— 旧实现正是这样把上一套清单的权重带了过来。
      draft.value.long_custom_weights = newWeights
      const ok = await commitDraft(true, ['long_coin_list'])
      if (!ok) {
        snackbarStore.show({ message: '权重保存失败，请重试（原因见下方日志）', color: 'error' })
        return
      }
    } else {
      const result = await settingsStore.patchSettings({
        long_coin_list: localWeights.value.map((item) => item.symbol),
        long_custom_weights: newWeights,
      })
      if (!result.ok) {
        snackbarStore.show({ message: `权重保存失败：${result.detail}`, color: 'error' })
        return
      }
    }
    snackbarStore.show({ message: '权重已保存，下次开仓按新比例分配', color: 'success' })
    close()
  } finally {
    saving.value = false
  }
}

const close = () => {
  emit('update:modelValue', false)
}

watch(
  () => props.modelValue,
  (newValue) => {
    if (newValue) {
      // 每次打开弹窗，都重新初始化
      initWeights()
    }
  },
  { immediate: true },
)
</script>
