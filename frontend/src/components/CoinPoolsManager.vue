<!-- frontend/src/components/CoinPoolsManager.vue (持久化修复版) -->
<template>
  <div>
    <!-- 添加新币种UI -->
    <v-card variant="outlined" class="mb-6">
      <v-card-title class="text-subtitle-1 font-weight-medium d-flex align-center">
        <v-icon start>mdi-database-plus-outline</v-icon>
        <span>手动添加币种</span>
      </v-card-title>
      <v-divider></v-divider>
      <v-card-text>
        <div class="d-flex align-center">
          <v-text-field
            v-model="newCoinSymbolUpper"
            label="输入币种代码 (例如: btc)"
            variant="outlined"
            density="compact"
            hide-details
            class="mr-4"
            @keyup.enter="addCoin"
            autofocus
          ></v-text-field>
          <v-btn
            color="primary"
            variant="tonal"
            @click="addCoin"
            :loading="isAddingCoin"
            :disabled="!newCoinSymbol.trim()"
            prepend-icon="mdi-plus"
          >
            添加
          </v-btn>
        </div>
        <div class="text-caption text-medium-emphasis mt-2">
          添加到总池后，您就可以在下方的做多/做空备选池中选择它。
        </div>
      </v-card-text>
    </v-card>

    <v-row>
      <!-- 多头币种池 -->
      <v-col cols="12" md="6">
        <v-card variant="tonal" class="pa-4" style="height: 100%">
          <div class="d-flex align-center mb-2">
            <span class="text-subtitle-1 font-weight-medium"
              >做多币种备选池 ({{ settingsStore.availableLongCoins.length }})</span
            >
            <v-tooltip location="top">
              <template v-slot:activator="{ props }">
                <v-btn
                  icon="mdi-select-all"
                  variant="text"
                  size="small"
                  v-bind="props"
                  @click="selectAllCoins('long')"
                ></v-btn>
              </template>
              <span>全选可用</span>
            </v-tooltip>
          </div>

          <SmartSelect
            :model-value="sortedLongPool"
            :items="availableForLongPool"
            label="从总池中选择做多备选币种（可搜索）"
            multiple
            clearable
            searchable
            @update:model-value="setAvailableLongCoins"
          ></SmartSelect>
        </v-card>
      </v-col>

      <!-- 空头币种池 -->
      <v-col cols="12" md="6">
        <v-card variant="tonal" class="pa-4" style="height: 100%">
          <div class="d-flex align-center mb-2">
            <span class="text-subtitle-1 font-weight-medium"
              >做空币种备选池 ({{ settingsStore.availableShortCoins.length }})</span
            >
            <v-tooltip location="top">
              <template v-slot:activator="{ props }">
                <v-btn
                  icon="mdi-select-all"
                  variant="text"
                  size="small"
                  v-bind="props"
                  @click="selectAllCoins('short')"
                ></v-btn>
              </template>
              <span>全选可用</span>
            </v-tooltip>
          </div>

          <SmartSelect
            :model-value="sortedShortPool"
            :items="availableForShortPool"
            label="从总池中选择做空备选币种（可搜索）"
            multiple
            clearable
            searchable
            @update:model-value="setAvailableShortCoins"
          ></SmartSelect>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import SmartSelect from '@/components/SmartSelect.vue'
import { useSettingsStore } from '@/stores/settingsStore'
import { useSnackbarStore } from '@/stores/snackbar'
import apiClient from '@/services/api'
import { ENDPOINTS } from '@/services/endpoints'
import { debounce } from '@/utils/debounce'
import { getErrorMessage } from '@/utils/errors'

const settingsStore = useSettingsStore()
const snackbarStore = useSnackbarStore()

const MAX_VISIBLE_CHIPS = 3
const isLongPoolExpanded = ref(false)
const isShortPoolExpanded = ref(false)

const newCoinSymbol = ref('')
const isAddingCoin = ref(false)

// T11：原 5 个 watch 收敛为 computed / 事件驱动 ——
// 排序/大写归一走 computed，自动保存由「唯一的池子写入口」触发，不再深度监听。

/** 输入框大写归一（原 watch(newCoinSymbol) 的 computed 化） */
const newCoinSymbolUpper = computed({
  get: () => newCoinSymbol.value,
  set: (value: string) => {
    newCoinSymbol.value = String(value ?? '').toUpperCase()
  },
})

/** 池子展示永远有序（原 watch 内 in-place sort 的 computed 化） */
const sortedLongPool = computed(() => [...settingsStore.availableLongCoins].sort())
const sortedShortPool = computed(() => [...settingsStore.availableShortCoins].sort())

// --- 带防抖的自动保存 ---
const savePoolsDebounced = debounce(() => {
  savePools(true) // 传入一个参数标记为自动保存
}, 1500)

const allAvailableCoins = computed(() => [...new Set(settingsStore.availableCoins)].sort())
const mapToSelectItems = (coins: string[]) => coins.map((coin) => ({ title: coin, value: coin }))

const availableForLongPool = computed(() => {
  const shortSet = new Set(settingsStore.availableShortCoins)
  return mapToSelectItems(allAvailableCoins.value.filter((coin) => !shortSet.has(coin)))
})

const availableForShortPool = computed(() => {
  const longSet = new Set(settingsStore.availableLongCoins)
  return mapToSelectItems(allAvailableCoins.value.filter((coin) => !longSet.has(coin)))
})

// SmartSelect 回写（多选）：唯一的池子写入口 —— 保持池子为有序字符串数组，
// 数量缩回阈值以内时收起展开态，并触发防抖自动保存。
const applyPool = (poolType: 'long' | 'short', coins: string[]) => {
  const sorted = [...coins].sort()
  if (poolType === 'long') {
    settingsStore.availableLongCoins = sorted
    if (sorted.length <= MAX_VISIBLE_CHIPS) isLongPoolExpanded.value = false
  } else {
    settingsStore.availableShortCoins = sorted
    if (sorted.length <= MAX_VISIBLE_CHIPS) isShortPoolExpanded.value = false
  }
  savePoolsDebounced()
}

const setAvailableLongCoins = (value: string | number | (string | number)[] | null | undefined) => {
  applyPool('long', Array.isArray(value) ? value.map(String) : [])
}

const setAvailableShortCoins = (value: string | number | (string | number)[] | null | undefined) => {
  applyPool('short', Array.isArray(value) ? value.map(String) : [])
}

const selectAllCoins = (poolType: 'long' | 'short') => {
  if (poolType === 'long') {
    applyPool('long', availableForLongPool.value.map((item) => item.value))
  } else if (poolType === 'short') {
    applyPool('short', availableForShortPool.value.map((item) => item.value))
  }
}

const savePools = async (isAutoSave = false) => {
  try {
    await apiClient.post(ENDPOINTS.settingsUpdateCoinPools, {
      long_coins_pool: [...settingsStore.availableLongCoins].sort(),
      short_coins_pool: [...settingsStore.availableShortCoins].sort(),
    })
    if (!isAutoSave) {
        snackbarStore.show({ message: '币种备选池已成功保存。', color: 'success' })
    } else {
        console.log("Coin pools auto-saved successfully.")
    }
  } catch (error: unknown) {
    snackbarStore.show({ message: `保存币种备选池失败: ${getErrorMessage(error)}`, color: 'error' })
  }
}

const addCoin = async () => {
  const symbol = newCoinSymbol.value.trim()
  if (!symbol || isAddingCoin.value) return

  isAddingCoin.value = true
  try {
    const response = await apiClient.post(ENDPOINTS.settingsAddCoin, { coin: symbol })
    settingsStore.availableCoins.splice(0, settingsStore.availableCoins.length, ...response.data)
    newCoinSymbol.value = ''
    snackbarStore.show({ message: `币种 '${symbol}' 添加成功！`, color: 'success' })
  } catch (error: unknown) {
    snackbarStore.show({ message: `添加失败: ${getErrorMessage(error)}`, color: 'error' })
  } finally {
    isAddingCoin.value = false
  }
}

// 让父组件可以通过 ref 调用手动保存
defineExpose({ savePools })
</script>

<style scoped>
</style>
