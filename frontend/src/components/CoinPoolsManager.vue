<!-- frontend/src/components/CoinPoolsManager.vue (单一数据源最终版) -->
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
        <div class="text-caption text-grey mt-2">
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

          <v-select
            v-model="settingsStore.availableLongCoins"
            :items="filteredLongPoolItems"
            label="从总池中选择做多备选币种"
            multiple
            clearable
            variant="outlined"
            hide-details
            item-title="title"
            item-value="value"
            :menu-props="{ maxHeight: '300px' }"
            :hide-selected="!longPoolShowAll"
            :close-on-content-click="false"
          >
            <template v-slot:selection="{ item, index }">
              <div
                v-if="index === 0"
                class="selection-wrapper"
                :class="{ 'is-expanded': isLongPoolExpanded }"
              >
                <v-chip
                  v-for="(poolItem, chipIndex) in settingsStore.availableLongCoins"
                  :key="`long-${poolItem}`"
                  v-show="isLongPoolExpanded || chipIndex < MAX_VISIBLE_CHIPS"
                  class="ma-1"
                  closable
                  @click:close="removePoolItemValue('long', poolItem)"
                >
                  <span>{{ poolItem }}</span>
                </v-chip>
                <v-chip
                  v-if="
                    !isLongPoolExpanded &&
                    settingsStore.availableLongCoins.length > MAX_VISIBLE_CHIPS
                  "
                  class="ma-1"
                  @mousedown.stop="isLongPoolExpanded = true"
                  size="small"
                >
                  +{{ settingsStore.availableLongCoins.length - MAX_VISIBLE_CHIPS }}
                </v-chip>
                <v-btn
                  v-if="isLongPoolExpanded"
                  icon="mdi-chevron-up"
                  variant="text"
                  size="x-small"
                  @mousedown.stop="isLongPoolExpanded = false"
                  class="ml-1"
                ></v-btn>
              </div>
            </template>

            <template v-slot:prepend-item>
              <div class="d-flex align-center px-4 pt-2 pb-1">
                <v-text-field
                  v-model="longSearch"
                  placeholder="搜索币种..."
                  variant="underlined"
                  density="compact"
                  hide-details
                  class="mr-2"
                  @click.stop
                ></v-text-field>
                <v-switch
                  v-model="longPoolShowAll"
                  label="显示已选"
                  density="compact"
                  color="primary"
                  hide-details
                  class="flex-shrink-0"
                  @click.stop
                ></v-switch>
              </div>
              <v-divider></v-divider>
            </template>

            <template v-slot:item="{ item, props }">
              <v-list-item v-bind="props" class="pl-0">
                <template v-slot:prepend>
                  <v-checkbox-btn
                    :model-value="settingsStore.availableLongCoins.includes(item.value)"
                    readonly
                    class="mr-2"
                  ></v-checkbox-btn>
                </template>
              </v-list-item>
            </template>
          </v-select>
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

          <v-select
            v-model="settingsStore.availableShortCoins"
            :items="filteredShortPoolItems"
            label="从总池中选择做空备选币种"
            multiple
            clearable
            variant="outlined"
            hide-details
            item-title="title"
            item-value="value"
            :menu-props="{ maxHeight: '300px' }"
            :hide-selected="!shortPoolShowAll"
            :close-on-content-click="false"
          >
            <template v-slot:selection="{ item, index }">
              <div
                v-if="index === 0"
                class="selection-wrapper"
                :class="{ 'is-expanded': isShortPoolExpanded }"
              >
                <v-chip
                  v-for="(poolItem, chipIndex) in settingsStore.availableShortCoins"
                  :key="`short-${poolItem}`"
                  v-show="isShortPoolExpanded || chipIndex < MAX_VISIBLE_CHIPS"
                  class="ma-1"
                  closable
                  @click:close="removePoolItemValue('short', poolItem)"
                >
                  <span>{{ poolItem }}</span>
                </v-chip>
                <v-chip
                  v-if="
                    !isShortPoolExpanded &&
                    settingsStore.availableShortCoins.length > MAX_VISIBLE_CHIPS
                  "
                  class="ma-1"
                  @mousedown.stop="isShortPoolExpanded = true"
                  size="small"
                >
                  +{{ settingsStore.availableShortCoins.length - MAX_VISIBLE_CHIPS }}
                </v-chip>
                <v-btn
                  v-if="isShortPoolExpanded"
                  icon="mdi-chevron-up"
                  variant="text"
                  size="x-small"
                  @mousedown.stop="isShortPoolExpanded = false"
                  class="ml-1"
                ></v-btn>
              </div>
            </template>

            <template v-slot:prepend-item>
              <div class="d-flex align-center px-4 pt-2 pb-1">
                <v-text-field
                  v-model="shortSearch"
                  placeholder="搜索币种..."
                  variant="underlined"
                  density="compact"
                  hide-details
                  class="mr-2"
                  @click.stop
                ></v-text-field>
                <v-switch
                  v-model="shortPoolShowAll"
                  label="显示已选"
                  density="compact"
                  color="primary"
                  hide-details
                  class="flex-shrink-0"
                  @click.stop
                ></v-switch>
              </div>
              <v-divider></v-divider>
            </template>

            <template v-slot:item="{ item, props }">
              <v-list-item v-bind="props" class="pl-0">
                <template v-slot:prepend>
                  <v-checkbox-btn
                    :model-value="settingsStore.availableShortCoins.includes(item.value)"
                    readonly
                    class="mr-2"
                  ></v-checkbox-btn>
                </template>
              </v-list-item>
            </template>
          </v-select>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useSettingsStore } from '@/stores/settingsStore'
import { useSnackbarStore } from '@/stores/snackbar'
import apiClient from '@/services/api'

const settingsStore = useSettingsStore()
const snackbarStore = useSnackbarStore()

const MAX_VISIBLE_CHIPS = 3
const isLongPoolExpanded = ref(false)
const isShortPoolExpanded = ref(false)
const longPoolShowAll = ref(false)
const shortPoolShowAll = ref(false)

const longSearch = ref('')
const shortSearch = ref('')
const newCoinSymbol = ref('')
const isAddingCoin = ref(false)

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

const filteredLongPoolItems = computed(() => {
  if (!longSearch.value) return availableForLongPool.value
  return availableForLongPool.value.filter((item) =>
    item.title.toLowerCase().includes(longSearch.value.toLowerCase()),
  )
})

const filteredShortPoolItems = computed(() => {
  if (!shortSearch.value) return availableForShortPool.value
  return availableForShortPool.value.filter((item) =>
    item.title.toLowerCase().includes(shortSearch.value.toLowerCase()),
  )
})

const selectAllCoins = (poolType: 'long' | 'short') => {
  if (poolType === 'long') {
    settingsStore.availableLongCoins = availableForLongPool.value.map((item) => item.value)
  } else if (poolType === 'short') {
    settingsStore.availableShortCoins = availableForShortPool.value.map((item) => item.value)
  }
}

const savePools = async () => {
  try {
    await apiClient.post('/api/settings/update-coin-pools', {
      long_coins_pool: settingsStore.availableLongCoins,
      short_coins_pool: settingsStore.availableShortCoins,
    })
    snackbarStore.show({ message: '币种备选池已成功保存。', color: 'success' })
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message
    snackbarStore.show({ message: `保存币种备选池失败: ${errorMsg}`, color: 'error' })
  }
}

const addCoin = async () => {
  const symbol = newCoinSymbol.value.trim()
  if (!symbol || isAddingCoin.value) return

  isAddingCoin.value = true
  try {
    await apiClient.post('/api/settings/add-coin', { coin: symbol })
    await settingsStore.fetchSettings()
    newCoinSymbol.value = ''
    snackbarStore.show({ message: `币种 '${symbol}' 添加成功！`, color: 'success' })
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message
    snackbarStore.show({ message: `添加失败: ${errorMsg}`, color: 'error' })
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

defineExpose({ savePools })
</script>

<style scoped>
.selection-wrapper {
  display: flex;
  flex-wrap: wrap;
  width: 100%;
  align-items: center;
}

.selection-wrapper.is-expanded {
  max-height: 150px;
  overflow-y: auto;
}
</style>
