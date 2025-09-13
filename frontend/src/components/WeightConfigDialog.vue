<!-- frontend/src/components/WeightConfigDialog.vue -->
<template>
  <v-dialog v-model="show" max-width="500px" persistent>
    <v-card>
      <v-card-title>
        <span class="text-h5">配置多头权重</span>
      </v-card-title>
      <v-card-text>
        <p class="text-caption mb-4">
          修改一个权重后，未修改的将自动均分剩余比例。总和必须为 100%。
        </p>
        <v-form ref="form">
          <v-row v-for="(coin, index) in localWeights" :key="coin.symbol" class="align-center">
            <v-col cols="4">
              <v-label>{{ coin.symbol }}</v-label>
            </v-col>
            <v-col cols="8">
              <v-text-field
                v-model.number="coin.weight"
                @focus="onFocus(coin.symbol)"
                @update:model-value="recalculateWeights(index)"
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
          <span :class="Math.abs(totalWeight - 100) < 0.01 ? 'text-success' : 'text-error'">
            {{ totalWeight.toFixed(2) }} %
          </span>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-btn color="primary" variant="text" @click="resetWeights">均分权重</v-btn>
        <v-spacer></v-spacer>
        <v-btn color="blue-darken-1" variant="text" @click="close">取消</v-btn>
        <v-btn color="blue-darken-1" variant="tonal" @click="save" :disabled="Math.abs(totalWeight - 100) > 0.01">保存</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';
// 不再需要 uiStore，因为显隐由 props 控制

const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits(['update:modelValue']);

const settingsStore = useSettingsStore();
const localWeights = ref<{ symbol: string; weight: number }[]>([]);
const manuallyEdited = ref<Set<string>>(new Set());
let isRecalculating = false;

// 核心修复：使用 computed 属性来同步 v-model
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

const recalculateWeights = (editedIndex: number) => {
  if (isRecalculating) return;
  isRecalculating = true;

  const editedWeight = Number(localWeights.value[editedIndex].weight) || 0;
  if (editedWeight > 100) localWeights.value[editedIndex].weight = 100;
  if (editedWeight < 0) localWeights.value[editedIndex].weight = 0;

  const manuallySetTotal = Array.from(manuallyEdited.value).reduce((sum, symbol) => {
      const item = localWeights.value.find(lw => lw.symbol === symbol);
      return sum + (Number(item?.weight) || 0);
  }, 0);

  const remainingTotal = 100 - manuallySetTotal;
  const unassignedItems = localWeights.value.filter(item => !manuallyEdited.value.has(item.symbol));

  if (unassignedItems.length > 0 && remainingTotal >= 0) {
      const avg = remainingTotal / unassignedItems.length;
      unassignedItems.forEach((item, index) => {
          item.weight = (index === unassignedItems.length - 1)
              ? parseFloat((100 - manuallySetTotal - (avg * (unassignedItems.length - 1))).toFixed(2))
              : parseFloat(avg.toFixed(2));
      });
  } else if (unassignedItems.length > 0 && remainingTotal < 0) {
      unassignedItems.forEach(item => item.weight = 0);
  }

  setTimeout(() => { isRecalculating = false; }, 10);
};

const initWeights = () => {
  if (!settingsStore.settings.long_coin_list) return;
  const selectedCoins = settingsStore.settings.long_coin_list;
  const currentWeights = settingsStore.settings.long_custom_weights || {};
  manuallyEdited.value.clear();

  localWeights.value = selectedCoins.map(coin => {
    if(currentWeights[coin] !== undefined){
      manuallyEdited.value.add(coin);
    }
    return {
      symbol: coin,
      weight: currentWeights[coin] || 0
    };
  });

  if (Object.keys(currentWeights).length === 0 || Math.abs(totalWeight.value - 100) > 0.01) {
    resetWeights();
  }
};

const resetWeights = () => {
  manuallyEdited.value.clear();
  const count = localWeights.value.length;
  if (count === 0) return;
  const avgWeight = 100 / count;

  let accumulatedWeight = 0;
  localWeights.value.forEach((item, index) => {
    if (index === count - 1) {
      item.weight = parseFloat((100 - accumulatedWeight).toFixed(2));
    } else {
      const w = parseFloat(avgWeight.toFixed(2));
      item.weight = w;
      accumulatedWeight += w;
    }
  });
};

const save = () => {
  if (Math.abs(totalWeight.value - 100) < 0.01) {
    const newWeights: { [key: string]: number } = {};
    localWeights.value.forEach(item => {
      newWeights[item.symbol] = item.weight;
    });
    // @ts-ignore
    settingsStore.settings.long_custom_weights = newWeights;
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
});
</script>
