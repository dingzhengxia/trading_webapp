<!-- frontend/src/components/WeightConfigDialog.vue -->
<!-- 多头权重：显示「实际生效的分配」，保存即落库。
     旧版两个坑（2026-11-15 用户反馈「我设的是均分，BTC 怎么跑到 40%」）：
     1) 没保存过权重时，弹窗自己算出均分 33.33/33.33/33.33 展示，但后端无权重时用的是
        BTC 40% / ETH 30% / 其余均分 —— 界面在撒谎，用户看一眼就以为已是均分；
     2) 保存只改内存里的 settingsStore，没走落库通道，刷新即丢。
     现在：编辑对象是与表单共用的草稿（useDraftSettings），保存 = 写草稿 + 立即提交。 -->
<template>
  <v-dialog v-model="show" max-width="520px" persistent>
    <v-card>
      <v-card-title>
        <span class="text-h5">配置多头权重</span>
      </v-card-title>
      <v-card-text>
        <p class="text-caption mb-3">
          修改一个权重后，未手动修改过的项目将自动均分剩余比例。总和必须为 100%。
        </p>

        <v-alert
          v-if="usingDefault"
          type="info"
          variant="tonal"
          density="compact"
          class="mb-3 text-caption"
        >
          你还没有保存过自定义权重。这里是后端实际会用的默认分配（BTC 40% / ETH 30% / 其余均分）——
          想要每个币等额，点下面的「均分权重」再保存。
        </v-alert>

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
import { defaultWeights, evenWeights } from '@/utils/weights'
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
/** 当前展示的是「后端默认分配」而不是已保存的自定义权重 */
const usingDefault = ref(false)
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
  usingDefault.value = false

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

/** 「均分权重」：清空所有锁定，每个币等额（显式写成数字，不再依赖后端的默认分配） */
const fillEven = () => {
  manuallyEdited.value.clear()
  usingDefault.value = false
  const weights = evenWeights(localWeights.value.map((item) => item.symbol))
  localWeights.value.forEach((item) => {
    item.weight = weights[item.symbol] ?? item.weight
  })
}

const currentSettings = () => draft.value ?? settingsStore.settings

const initWeights = () => {
  const current = currentSettings()
  if (!current?.long_coin_list) return
  const selectedCoins = current.long_coin_list
  const savedWeights = current.long_custom_weights || {}

  // 关键：每次打开弹窗，都必须清空“手动编辑”的记录！
  manuallyEdited.value.clear()

  const hasSaved = selectedCoins.some((coin) => Number(savedWeights[coin]) > 0)
  const seed = hasSaved ? savedWeights : defaultWeights(selectedCoins)
  usingDefault.value = !hasSaved
  localWeights.value = selectedCoins.map((coin) => ({
    symbol: coin,
    weight: seed[coin] !== undefined ? Number(seed[coin]) : 0,
  }))

  // 没有任何可用权重（老配置/币种全换过）→ 直接均分，至少让总和是 100
  if (!hasSaved && Math.abs(totalWeight.value - 100) > 0.001) {
    fillEven()
  }
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
      // 写草稿 + 立即提交：走的是与「保存」按钮同一条落库通道
      draft.value.long_custom_weights = newWeights
      const ok = await commitDraft(true)
      if (!ok) {
        snackbarStore.show({ message: '权重保存失败，请重试（原因见下方日志）', color: 'error' })
        return
      }
    } else {
      const result = await settingsStore.patchSettings({ long_custom_weights: newWeights })
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
