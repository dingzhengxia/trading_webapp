<!-- frontend/src/components/WeightConfigDialog.vue (最终精确版) -->
<template>
  <v-dialog v-model="show" max-width="500px" persistent>
    <v-card>
      <v-card-title>
        <span class="text-h5">配置多头权重</span>
      </v-card-title>
      <v-card-text>
        <p class="text-caption mb-4">
          修改一个权重后，未手动修改过的项目将自动均分剩余比例。总和必须为 100%。
        </p>
        <v-form ref="form">
          <v-row v-for="(coin) in localWeights" :key="coin.symbol" class="align-center">
            <v-col cols="4">
              <v-label>{{ coin.symbol }}</v-label>
            </v-col>
            <v-col cols="8">
              <v-text-field
                v-model.number="coin.weight"
                @focus="onFocus(coin.symbol)"
                @update:model-value="recalculateWeights(coin.symbol)"
                type="number"
                variant="outlined"
                density="compact"
                suffix="%"
                hide-details
              ></v-text-field>
            </v-col>
          </v-row>
        </v-form>
        <v-divider class="my-4"></v-divider>
        <div class="d-flex justify-space-between">
          <span class="font-weight-bold">总权重:</span>
          <span :class="Math.abs(totalWeight - 100) < 0.001 ? 'text-success' : 'text-error'">
            {{ totalWeight.toFixed(2) }} %
          </span>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-btn color="primary" variant="text" @click="resetAndUnlock">均分权重</v-btn>
        <v-spacer></v-spacer>
        <v-btn color="blue-darken-1" variant="text" @click="close">取消</v-btn>
        <v-btn color="blue-darken-1" variant="tonal" @click="save" :disabled="Math.abs(totalWeight - 100) > 0.001">保存</v-btn>
      </v-card-actions>
    </v-card>
  </template>

<script setup lang="ts">
import { ref, watch, computed, nextTick } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';

const props = defineProps<{
  modelValue: boolean,
}>();
const emit = defineEmits(['update:modelValue']);

const settingsStore = useSettingsStore();
const localWeights = ref<{ symbol: string; weight: number }[]>([]);
const manuallyEdited = ref<Set<string>>(new Set());
let isRecalculating = false;

const show = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
});

const totalWeight = computed(() => {
  return localWeights.value.reduce((sum, item) => sum + (Number(item.weight) || 0), 0);
});

const onFocus = (symbol: string) => {
  manuallyEdited.value.add(symbol);
};

// --- 核心修复：确保总和精确为100的分配算法 ---
const distribute = (total: number, items: { symbol: string; weight: number }[]) => {
  const count = items.length;
  if (count === 0) return;

  const avg = total / count;
  let accumulatedWeight = 0;

  items.forEach((item, index) => {
    if (index === count - 1) {
      // 最后一项使用减法来确保总和精确
      item.weight = parseFloat((total - accumulatedWeight).toFixed(2));
    } else {
      // 其他项四舍五入到两位小数
      const w = parseFloat(avg.toFixed(2));
      item.weight = w;
      accumulatedWeight += w;
    }
  });
};


const recalculateWeights = (editedSymbol: string) => {
  if (isRecalculating) return;
  isRecalculating = true;

  manuallyEdited.value.add(editedSymbol);

  const lockedTotal = localWeights.value
    .filter(item => manuallyEdited.value.has(item.symbol))
    .reduce((sum, item) => sum + (Number(item.weight) || 0), 0);

  const unassignedItems = localWeights.value.filter(item => !manuallyEdited.value.has(item.symbol));

  if (unassignedItems.length > 0) {
    const remainingTotal = 100 - lockedTotal;
    distribute(remainingTotal > 0 ? remainingTotal : 0, unassignedItems);
  }

  nextTick(() => { isRecalculating = false; });
};

const resetAndUnlock = () => {
  manuallyEdited.value.clear();
  distribute(100, localWeights.value);
};

const initWeights = () => {
  if (!settingsStore.settings?.long_coin_list) return;

  const selectedCoins = settingsStore.settings.long_coin_list;
  const currentWeights = settingsStore.settings.long_custom_weights || {};

  manuallyEdited.value.clear(); // 每次打开都重置锁定状态

  localWeights.value = selectedCoins.map(coin => ({
    symbol: coin,
    weight: currentWeights[coin] !== undefined ? currentWeights[coin] : 0
  }));

  if (Object.keys(currentWeights).length === 0 || Math.abs(totalWeight.value - 100) > 0.001) {
    resetAndUnlock();
  } else {
    manuallyEdited.value = new Set(Object.keys(currentWeights));
  }
};

const save = () => {
  if (Math.abs(totalWeight.value - 100) < 0.001) {
    const newWeights: { [key: string]: number } = {};
    localWeights.value.forEach(item => {
      newWeights[item.symbol] = item.weight;
    });
    if (settingsStore.settings) {
        settingsStore.settings.long_custom_weights = newWeights;
    }
    close();
  }
};

const close = () => {
  emit('update:modelValue', false);
};

watch(() => props.modelValue, (newValue) => {
  if (newValue) {
    initWeights();
  }
}, { immediate: true });
</script>
