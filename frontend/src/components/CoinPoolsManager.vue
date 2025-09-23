<!-- frontend/src/components/CoinPoolsManager.vue (最终完美版) -->
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
              >做多币种备选池 ({{ longPool.length }})</span
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
            v-model="longPool"
            :items="filteredLongPoolItems"
            label="从总池中选择做多备选币种"
            multiple
            clearable
            variant="outlined"
            hide-details
            item-title="title"
            item-value="value"
            :menu-props="{ maxHeight: '300px' }"
            hide-selected
            :close-on-content-click="false"
          >
            <template v-slot:selection="{ item, index }">
                <!-- 修正后的显示逻辑 -->
                <v-chip
                  v-if="isLongPoolExpanded || index < MAX_VISIBLE_CHIPS"
                  class="ma-1"
                  closable
                  @click:close="removePoolItem('long', item)"
                >
                  <span>{{ item.title }}</span>
                </v-chip>

                <v-chip
                  v-if="!isLongPoolExpanded && index === MAX_VISIBLE_CHIPS"
                  class="ma-1"
                  @mousedown.stop="isLongPoolExpanded = true"
                  size="small"
                >
                  +{{ longPool.length - MAX_VISIBLE_CHIPS }}
                </v-chip>

                <v-btn
                  v-if="isLongPoolExpanded && index === longPool.length - 1"
                  icon="mdi-chevron-up"
                  variant="text"
                  size="x-small"
                  @mousedown.stop="isLongPoolExpanded = false"
                  class="ml-1"
                ></v-btn>
            </template>

            <template v-slot:prepend-item>
              <v-text-field
                v-model="longSearch"
                placeholder="搜索币种..."
                variant="underlined"
                density="compact"
                hide-details
                class="px-4 mb-2"
                @click.stop
              ></v-text-field>
              <v-divider></v-divider>
            </template>

            <template v-slot:item="{ item, props }">
              <v-list-item v-bind="props" class="pl-0">
                <template v-slot:prepend>
                  <v-checkbox-btn
                    :model-value="longPool.includes(item.value)"
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
              >做空币种备选池 ({{ shortPool.length }})</span
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
            v-model="shortPool"
            :items="filteredShortPoolItems"
            label="从总池中选择做空备选币种"
            multiple
            clearable
            variant="outlined"
            hide-details
            item-title="title"
            item-value="value"
            :menu-props="{ maxHeight: '300px' }"
            hide-selected
            :close-on-content-click="false"
          >
            <template v-slot:selection="{ item, index }">
                <!-- 修正后的显示逻辑 -->
                <v-chip
                  v-if="isShortPoolExpanded || index < MAX_VISIBLE_CHIPS"
                  class="ma-1"
                  closable
                  @click:close="removePoolItem('short', item)"
                >
                  <span>{{ item.title }}</span>
                </v-chip>

                <v-chip
                  v-if="!isShortPoolExpanded && index === MAX_VISIBLE_CHIPS"
                  class="ma-1"
                  @mousedown.stop="isShortPoolExpanded = true"
                  size="small"
                >
                  +{{ shortPool.length - MAX_VISIBLE_CHIPS }}
                </v-chip>

                <v-btn
                  v-if="isShortPoolExpanded && index === shortPool.length - 1"
                  icon="mdi-chevron-up"
                  variant="text"
                  size="x-small"
                  @mousedown.stop="isShortPoolExpanded = false"
                  class="ml-1"
                ></v-btn>
            </template>

            <template v-slot:prepend-item>
              <v-text-field
                v-model="shortSearch"
                placeholder="搜索币种..."
                variant="underlined"
                density="compact"
                hide-details
                class="px-4 mb-2"
                @click.stop
              ></v-text-field>
              <v-divider></v-divider>
            </template>

            <template v-slot:item="{ item, props }">
              <v-list-item v-bind="props" class="pl-0">
                <template v-slot:prepend>
                  <v-checkbox-btn
                    :model-value="shortPool.includes(item.value)"
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

const longPool = ref([...settingsStore.availableLongCoins])
const shortPool = ref([...settingsStore.availableShortCoins])
const longSearch = ref('')
const shortSearch = ref('')
const newCoinSymbol = ref('')
const isAddingCoin = ref(false)

watch(newCoinSymbol, (newValue) => {
  if (newValue && newValue !== newValue.toUpperCase()) {
    newCoinSymbol.value = newValue.toUpperCase()
  }
})

// REFACTOR: 修正为使用 item 对象
const removePoolItem = (poolType: 'long' | 'short', item: { value: string }) => {
  const pool = poolType === 'long' ? longPool : shortPool
  const index = pool.value.indexOf(item.value)
  if (index >= 0) {
    pool.value.splice(index, 1)
  }
}

const allAvailableCoins = computed(() => [...new Set(settingsStore.availableCoins)].sort())
const mapToSelectItems = (coins: string[]) => coins.map((coin) => ({ title: coin, value: coin }))

const availableForLongPool = computed(() => {
  const shortSet = new Set(shortPool.value)
  return mapToSelectItems(allAvailableCoins.value.filter((coin) => !shortSet.has(coin)))
})

const availableForShortPool = computed(() => {
  const longSet = new Set(longPool.value)
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
    longPool.value = availableForLongPool.value.map((item) => item.value)
  } else if (poolType === 'short') {
    shortPool.value = availableForShortPool.value.map((item) => item.value)
  }
}

const savePools = async () => {
  try {
    await apiClient.post('/api/settings/update-coin-pools', {
      long_coins_pool: longPool.value,
      short_coins_pool: shortPool.value,
    })
    settingsStore.updateAvailablePools(longPool.value, shortPool.value)
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
    const response = await apiClient.post('/api/settings/add-coin', { coin: symbol })
    settingsStore.availableCoins = response.data
    newCoinSymbol.value = ''
    snackbarStore.show({ message: `币种 '${symbol}' 添加成功！`, color: 'success' })
  } catch (error: any)
{
    const errorMsg = error.response?.data?.detail || error.message
    snackbarStore.show({ message: `添加失败: ${errorMsg}`, color: 'error' })
  } finally {
    isAddingCoin.value = false
  }
}

watch(
  () => settingsStore.availableLongCoins,
  (newVal) => (longPool.value = [...newVal]),
  { deep: true },
)

watch(
  () => settingsStore.availableShortCoins,
  (newVal) => (shortPool.value = [...newVal]),
  { deep: true },
)

watch(longPool, (newVal) => {
  if (newVal.length <= MAX_VISIBLE_CHIPS) {
    isLongPoolExpanded.value = false
  }
})

watch(shortPool, (newVal) => {
  if (newVal.length <= MAX_VISIBLE_CHIPS) {
    isShortPoolExpanded.value = false
  }
})

defineExpose({ savePools })
</script>

<style scoped>
/*
  v-select 的 selection 插槽默认会把所有内容放在一个 flex 容器里，
  为了让我们的滚动容器能正确工作，需要让它占据全部宽度。
*/
.selection-wrapper {
  display: flex;
  flex-wrap: wrap;
  width: 100%;
  align-items: center;
}

.selection-wrapper.is-expanded {
  max-height: 350px;
  overflow-y: auto;
}
</style>
