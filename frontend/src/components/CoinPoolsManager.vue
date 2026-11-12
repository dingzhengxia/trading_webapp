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
            v-model="newCoinSymbol"
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
            :model-value="settingsStore.availableLongCoins"
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
            :model-value="settingsStore.availableShortCoins"
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
import { ref, computed, watch } from 'vue'
import SmartSelect from '@/components/SmartSelect.vue'
import { useSettingsStore } from '@/stores/settingsStore'
import { useSnackbarStore } from '@/stores/snackbar'
import apiClient from '@/services/api'
import { debounce } from '@/utils/debounce'
import { getErrorMessage } from '@/utils/errors'

const settingsStore = useSettingsStore()
const snackbarStore = useSnackbarStore()

const MAX_VISIBLE_CHIPS = 3
const isLongPoolExpanded = ref(false)
const isShortPoolExpanded = ref(false)
const longPoolShowAll = ref(false)
const shortPoolShowAll = ref(false)

const newCoinSymbol = ref('')
const isAddingCoin = ref(false)

// --- 核心修正：创建一个带防抖的保存函数 ---
const savePoolsDebounced = debounce(() => {
  savePools(true) // 传入一个参数标记为自动保存
}, 1500)

// --- 核心修正：增加 watch 侦听器来触发自动保存 ---
watch(
  () => settingsStore.availableLongCoins,
  () => {
    savePoolsDebounced()
  },
  { deep: true },
)

watch(
  () => settingsStore.availableShortCoins,
  () => {
    savePoolsDebounced()
  },
  { deep: true },
)


watch(newCoinSymbol, (newValue) => {
  if (newValue && newValue !== newValue.toUpperCase()) {
    newCoinSymbol.value = newValue.toUpperCase()
  }
})

const removePoolItemValue = (poolType: 'long' | 'short', value: string) => {
  const pool =
    poolType === 'long'
      ? settingsStore.availableLongCoins
      : settingsStore.availableShortCoins
  const index = pool.indexOf(value)
  if (index >= 0) {
    pool.splice(index, 1)
  }
}

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

// SmartSelect 回写（多选）：保持池子为字符串数组
const setAvailableLongCoins = (value: string | number | (string | number)[] | null | undefined) => {
  settingsStore.availableLongCoins = Array.isArray(value) ? value.map(String) : []
}

const setAvailableShortCoins = (value: string | number | (string | number)[] | null | undefined) => {
  settingsStore.availableShortCoins = Array.isArray(value) ? value.map(String) : []
}

const selectAllCoins = (poolType: 'long' | 'short') => {
  if (poolType === 'long') {
    settingsStore.availableLongCoins = availableForLongPool.value.map((item) => item.value)
  } else if (poolType === 'short') {
    settingsStore.availableShortCoins = availableForShortPool.value.map((item) => item.value)
  }
}

const savePools = async (isAutoSave = false) => {
  try {
    await apiClient.post('/api/settings/update-coin-pools', {
      long_coins_pool: settingsStore.availableLongCoins,
      short_coins_pool: settingsStore.availableShortCoins,
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
    const response = await apiClient.post('/api/settings/add-coin', { coin: symbol })
    settingsStore.availableCoins.splice(0, settingsStore.availableCoins.length, ...response.data)
    newCoinSymbol.value = ''
    snackbarStore.show({ message: `币种 '${symbol}' 添加成功！`, color: 'success' })
  } catch (error: unknown) {
    snackbarStore.show({ message: `添加失败: ${getErrorMessage(error)}`, color: 'error' })
  } finally {
    isAddingCoin.value = false
  }
}

watch(
  () => settingsStore.availableLongCoins,
  (newList) => {
    if (newList) {
      if (newList.length <= MAX_VISIBLE_CHIPS) {
        isLongPoolExpanded.value = false
      }
      newList.sort()
    }
  },
  { deep: true },
)

watch(
  () => settingsStore.availableShortCoins,
  (newList) => {
    if (newList) {
      if (newList.length <= MAX_VISIBLE_CHIPS) {
        isShortPoolExpanded.value = false
      }
      newList.sort()
    }
  },
  { deep: true },
)

// 让父组件可以通过 ref 调用手动保存
defineExpose({ savePools })
</script>

<style scoped>
</style>
