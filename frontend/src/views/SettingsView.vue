<!-- frontend/src/views/SettingsView.vue -->
<template>
  <v-container>
    <v-row justify="center">
      <v-col cols="12" md="10" lg="8" xl="6">
        <v-skeleton-loader v-if="settingsStore.loading" type="card, article, actions"></v-skeleton-loader>

        <v-card v-else-if="settingsStore.settings">
          <v-card-title class="text-h5">应用设置</v-card-title>

          <v-card-text>
            <!-- API 设置 -->
            <h3 class="settings-subtitle">API 配置</h3>
            <v-row dense>
              <v-col cols="12">
                <v-text-field label="API Key" v-model="settingsStore.settings.api_key" variant="outlined" density="compact" hide-details />
              </v-col>
              <v-col cols="12">
                <v-text-field label="API Secret" v-model="settingsStore.settings.api_secret" type="password" variant="outlined" density="compact" hide-details />
              </v-col>
              <v-col cols="12">
                <v-switch label="使用测试网" v-model="settingsStore.settings.use_testnet" color="primary" inset hide-details />
              </v-col>
            </v-row>

            <v-divider class="my-6"></v-divider>

            <!-- 币种选择 -->
            <h3 class="settings-subtitle">币种选择</h3>
            <v-row dense align="center">
              <!-- 做多列表 -->
              <v-col cols="12" md="5">
                <v-label class="mb-2">做多币种列表</v-label>
                <v-select
                  label="选择做多币种"
                  v-model="settingsStore.settings.long_coin_list" <!-- 直接绑定到 long_coin_list -->
                  :items="availableCoins" <!-- 使用合并后的总列表 -->
                  multiple
                  chips
                  closable-chips
                  variant="outlined"
                  density="compact"
                  clearable
                  @update:model-value="onLongCoinsChanged"
                  :disabled="!settingsStore.settings.enable_long_trades"
                  hint="选择作为做多目标的币种"
                  persistent-hint
                ></v-select>
              </v-col>

              <!-- 移动按钮 -->
              <v-col cols="12" md="2" class="text-center">
                <!-- 移动到做空 -->
                <v-btn
                  icon="mdi-chevron-left"
                  @click="moveSelectedToShort"
                  :disabled="selectedShort.length === 0 || !settingsStore.settings.enable_short_trades"
                  color="primary"
                  variant="tonal"
                  class="mb-2"
                ></v-btn>
                <!-- 移动到做多 -->
                <v-btn
                  icon="mdi-chevron-right"
                  @click="moveSelectedToLong"
                  :disabled="selectedLong.length === 0 || !settingsStore.settings.enable_long_trades"
                  color="primary"
                  variant="tonal"
                ></v-btn>
              </v-col>

              <!-- 做空列表 -->
              <v-col cols="12" md="5">
                <v-label class="mb-2">做空币种列表</v-label>
                <v-select
                  label="选择做空币种"
                  v-model="settingsStore.settings.short_coin_list" <!-- 直接绑定到 short_coin_list -->
                  :items="availableCoinsFilteredForShort" <!-- 使用过滤后的做空可用币种 -->
                  multiple
                  chips
                  closable-chips
                  variant="outlined"
                  density="compact"
                  clearable
                  @update:model-value="onShortCoinsChanged"
                  :disabled="!settingsStore.settings.enable_short_trades"
                  hint="选择作为做空目标的币种"
                  persistent-hint
                ></v-select>
              </v-col>
            </v-row>

            <v-divider class="my-6"></v-divider>

            <!-- 通用开仓设置 -->
            <h3 class="settings-subtitle">通用开仓设置</h3>
            <v-row dense>
              <v-col cols="12" sm="6"><v-text-field label="开仓重试次数" v-model.number="settingsStore.settings.open_maker_retries" type="number" variant="outlined" density="compact" /></v-col>
              <v-col cols="12" sm="6"><v-text-field label="开仓订单超时(s)" v-model.number="settingsStore.settings.open_order_fill_timeout_seconds" type="number" variant="outlined" density="compact" /></v-col>
              <v-col cols="12" sm="6"><v-text-field label="平仓重试次数" v-model.number="settingsStore.settings.close_maker_retries" type="number" variant="outlined" density="compact" /></v-col>
              <v-col cols="12" sm="6"><v-text-field label="平仓订单超时(s)" v-model.number="settingsStore.settings.close_order_fill_timeout_seconds" type="number" variant="outlined" density="compact" /></v-col>
            </v-row>

            <v-divider class="my-6"></v-divider>

            <!-- 代理设置 -->
            <h3 class="settings-subtitle">网络代理</h3>
            <v-row dense>
                <v-col cols="12">
                    <v-switch label="启用代理" v-model="settingsStore.settings.enable_proxy" color="primary" inset hide-details />
                </v-col>
                <v-col cols="12">
                    <v-text-field
                        label="代理 URL (e.g., http://127.0.0.1:19828)"
                        v-model="settingsStore.settings.proxy_url"
                        variant="outlined"
                        density="compact"
                        :disabled="!settingsStore.settings.enable_proxy"
                        hide-details
                    ></v-text-field>
                </v-col>
            </v-row>

          </v-card-text>
           <v-card-actions class="pa-4">
              <v-spacer></v-spacer>
              <v-btn color="success" variant="tonal" @click="saveAllSettings">
                <v-icon left>mdi-content-save</v-icon>
                手动保存全部
              </v-btn>
            </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUiStore } from '@/stores/uiStore';
import { debounce } from 'lodash-es';

const modelValue = defineModel<string>();

const settingsStore = useSettingsStore();
const uiStore = useUiStore();

const rebalanceMethods = [
  { value: 'multi_factor_weakest', text: '多因子弱势策略' },
  { value: 'foam', text: 'FOAM强势动量' }
];

// --- debounce 用于保存币种选择 ---
const debouncedSavePoolSelection = debounce(() => {
  if (settingsStore.settings) {
    settingsStore.updateCoinPoolSelection(
      settingsStore.settings.long_coin_list, // 直接传递 long_coin_list
      settingsStore.settings.short_coin_list // 直接传递 short_coin_list
    );
  }
}, 500);
// --- debounce 结束 ---

const saveAllSettings = () => {
  if (settingsStore.settings) {
    settingsStore.saveSettings();
  }
};

onMounted(() => {
  if (!settingsStore.settings) {
    settingsStore.fetchSettings();
  }
});

// --- 币种管理逻辑 ---
// 选中的币种 (用于 v-select 的 value)
const selectedLong = ref<string[]>([]);
const selectedShort = ref<string[]>([]);

// 计算过滤后的可用币种列表，确保一个币种不会同时出现在两个列表的选项中
const availableCoinsFilteredForLong = computed(() => {
  if (!settingsStore.settings) return [];
  // 做多列表的选项：全局列表减去已在做空列表中的
  return settingsStore.availableCoins.filter(coin =>
    !settingsStore.settings!.short_coin_list.includes(coin)
  );
});

const availableCoinsFilteredForShort = computed(() => {
  if (!settingsStore.settings) return [];
  // 做空列表的选项：全局列表减去已在做多列表中的
  return settingsStore.availableCoins.filter(coin =>
    !settingsStore.settings!.long_coin_list.includes(coin)
  );
});

// 当用户直接在 v-select 中增删币种时的处理
const onLongCoinsChanged = (newVal: string[]) => {
    if (settingsStore.settings) {
        settingsStore.settings.long_coin_list = newVal; // 直接更新 long_coin_list
        debouncedSavePoolSelection();
    }
};

const onShortCoinsChanged = (newVal: string[]) => {
    if (settingsStore.settings) {
        settingsStore.settings.short_coin_list = newVal; // 直接更新 short_coin_list
        debouncedSavePoolSelection();
    }
};

// 移动选中的币种到做多列表
const moveSelectedToLong = () => {
    if (!settingsStore.settings) return;

    // 1. 将选中的做空币种添加到做多列表中 (去重)
    settingsStore.settings.long_coin_list = Array.from(new Set([
        ...settingsStore.settings.long_coin_list,
        ...selectedShort.value
    ]));
    // 2. 从做空列表中移除这些币种
    settingsStore.settings.short_coin_list = settingsStore.settings.short_coin_list.filter(
        coin => !selectedShort.value.includes(coin)
    );

    // 3. 清空选择
    selectedShort.value = [];
    selectedLong.value = [];

    // 4. 保存更改
    debouncedSavePoolSelection();
};

// 移动选中的币种到做空列表
const moveSelectedToShort = () => {
    if (!settingsStore.settings) return;

    // 1. 将选中的做多币种添加到做空列表中
    settingsStore.settings.short_coin_list = [
        ...settingsStore.settings.short_coin_list,
        ...selectedLong.value
    ];
    // 2. 从做多列表中移除这些币种
    settingsStore.settings.long_coin_list = settingsStore.settings.long_coin_list.filter(
        coin => !selectedLong.value.includes(coin)
    );

    // 3. 清空选择
    selectedLong.value = [];
    selectedShort.value = [];

    // 4. 保存更改
    debouncedSavePoolSelection();
};

</script>

<style scoped>
.settings-subtitle {
  font-size: 1rem;
  font-weight: 500;
  color: #a9b3c1;
  margin-bottom: 16px;
}
</style>
