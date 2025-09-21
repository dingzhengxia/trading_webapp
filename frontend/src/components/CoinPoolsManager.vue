<!-- frontend/src/components/CoinPoolsManager.vue (完整代码) -->
<template>
  <div>
    <v-row>
      <v-col cols="12" md="6">
        <v-card variant="tonal" class="pa-4">
          <div class="d-flex align-center mb-2">
            <span class="text-subtitle-1 font-weight-medium">做多币种备选池 ({{ longPool.length }})</span>
            <v-tooltip location="top">
              <template v-slot:activator="{ props }">
                <v-btn icon="mdi-select-all" variant="text" size="small" v-bind="props" @click="selectAllCoins('long')"></v-btn>
              </template>
              <span>全选可用</span>
            </v-tooltip>
          </div>

          <Multiselect
            v-model="longPool"
            :options="availableForLongPool"
            :multiple="true"
            :taggable="true"
            tag-placeholder="按回车添加新币种"
            placeholder="选择或搜索币种"
            label="title"
            track-by="value"
            @tag="addTag($event, 'long')"
          />

        </v-card>
      </v-col>

      <v-col cols="12" md="6">
        <v-card variant="tonal" class="pa-4">
          <div class="d-flex align-center mb-2">
            <span class="text-subtitle-1 font-weight-medium">做空币种备选池 ({{ shortPool.length }})</span>
             <v-tooltip location="top">
              <template v-slot:activator="{ props }">
                <v-btn icon="mdi-select-all" variant="text" size="small" v-bind="props" @click="selectAllCoins('short')"></v-btn>
              </template>
              <span>全选可用</span>
            </v-tooltip>
          </div>

          <Multiselect
            v-model="shortPool"
            :options="availableForShortPool"
            :multiple="true"
            :taggable="true"
            tag-placeholder="按回车添加新币种"
            placeholder="选择或搜索币种"
            label="title"
            track-by="value"
            @tag="addTag($event, 'short')"
          />

        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<style>
/*
  全局样式，适配 PrimeVue 组件以更好地融入 Vuetify 暗色主题。
  移除 scoped 以便样式能正确应用到 PrimeVue 的弹出菜单。
*/
@import "vue-multiselect/dist/vue-multiselect.css";

:root {
  /* General */
  --ms-font-size: 0.875rem;
  --ms-line-height: 1.25rem;
  --ms-bg: #2E2E2E;
  --ms-bg-disabled: #424242;

  /* Border */
  --ms-border-color: #4a4a4a;
  --ms-border-width: 1px;
  --ms-radius: 4px;

  /* Ring */
  --ms-ring-width: 3px;
  --ms-ring-color: #1867C080;

  /* Text */
  --ms-placeholder-color: rgba(255, 255, 255, 0.5);
  --ms-text-color: rgba(255, 255, 255, 0.8);
  --ms-text-color-disabled: #9e9e9e;

  /* Dropdown */
  --ms-dropdown-bg: #363636;
  --ms-dropdown-border-color: #4a4a4a;
  --ms-dropdown-border-width: 1px;

  /* Options */
  --ms-option-bg-pointed: #4a4a4a;
  --ms-option-bg-selected: #1867C0;
  --ms-option-bg-selected-pointed: #1E88E5;
  --ms-option-color-pointed: #FFFFFF;
  --ms-option-color-selected: #FFFFFF;
  --ms-group-label-bg-pointed: var(--ms-option-bg-pointed);
  --ms-group-label-color-pointed: var(--ms-option-color-pointed);

  /* Tags */
  --ms-tag-bg: #1867C0;
  --ms-tag-color: #FFFFFF;
  --ms-tag-radius: 4px;
}
</style>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUiStore } from '@/stores/uiStore';
import apiClient from '@/services/api';
import Multiselect from 'vue-multiselect';

const settingsStore = useSettingsStore();
const uiStore = useUiStore();

// vue-multiselect 在 v-model 中需要对象数组
const longPool = ref<{title: string, value: string}[]>(
  settingsStore.availableLongCoins.map(c => ({ title: c, value: c }))
);
const shortPool = ref<{title: string, value: string}[]>(
  settingsStore.availableShortCoins.map(c => ({ title: c, value: c }))
);

const allAvailableCoins = computed(() => [...new Set(settingsStore.availableCoins)].sort());
const mapToSelectItems = (coins: string[]) => coins.map(coin => ({ title: coin, value: coin }));

// :options 仍然是对象数组
const availableForLongPool = computed(() => {
  const shortSet = new Set(shortPool.value.map(c => c.value));
  const available = allAvailableCoins.value.filter(coin => !shortSet.has(coin));
  return mapToSelectItems(available);
});

const availableForShortPool = computed(() => {
  const longSet = new Set(longPool.value.map(c => c.value));
  const available = allAvailableCoins.value.filter(coin => !longSet.has(coin));
  return mapToSelectItems(available);
});

const selectAllCoins = (poolType: 'long' | 'short') => {
  if (poolType === 'long') {
    longPool.value = availableForLongPool.value;
  } else if (poolType === 'short') {
    shortPool.value = availableForShortPool.value;
  }
};

// 新增 addTag 函数，用于处理用户手动输入新标签
const addTag = (newTag: string, type: 'long' | 'short') => {
  const tag = { title: newTag.toUpperCase(), value: newTag.toUpperCase() };
  if (type === 'long') {
    longPool.value.push(tag);
  } else {
    shortPool.value.push(tag);
  }
}

const savePools = async () => {
  try {
    await apiClient.post('/api/settings/update-coin-pools', {
      long_coins_pool: longPool.value.map(c => c.value), // 保存时只提取 value
      short_coins_pool: shortPool.value.map(c => c.value),
    });
    settingsStore.updateAvailablePools(
      longPool.value.map(c => c.value),
      shortPool.value.map(c => c.value)
    );
    uiStore.logStore.addLog({ message: '币种备选池已成功保存。', level: 'success', timestamp: new Date().toLocaleTimeString() });
  } catch (error: any) {
    const errorMsg = error.response?.data?.detail || error.message;
    uiStore.logStore.addLog({ message: `保存币种备选池失败: ${errorMsg}`, level: 'error', timestamp: new Date().toLocaleTimeString() });
  }
};

watch(
  () => settingsStore.availableLongCoins,
  (newVal) => { longPool.value = newVal.map(c => ({ title: c, value: c })); }, { deep: true }
);

watch(
  () => settingsStore.availableShortCoins,
  (newVal) => { shortPool.value = newVal.map(c => ({ title: c, value: c })); }, { deep: true }
);

defineExpose({
  savePools
});
</script>
