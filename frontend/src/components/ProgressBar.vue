<template>
  <v-footer v-if="uiStore.progress.show" app class="pa-0" style="z-index: 1008;">
    <v-card flat tile class="flex" color="blue-grey-darken-3">
      <v-card-text class="py-2">
        <v-row align="center" no-gutters>
          <v-col cols="12" sm="3">
            <span class="text-caption font-weight-bold">
              {{ uiStore.progress.task_name }} ({{ uiStore.progress.current }} / {{ uiStore.progress.total }})
            </span>
          </v-col>
          <v-col cols="12" sm="9">
            <v-progress-linear
              :model-value="progressPercentage"
              color="light-blue-accent-3"
              height="20"
              striped
              stream
            >
              <strong class="text-white">{{ Math.ceil(progressPercentage) }}%</strong>
            </v-progress-linear>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>
  </v-footer>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useUiStore } from '@/stores/uiStore';

const uiStore = useUiStore();

const progressPercentage = computed(() => {
  if (uiStore.progress.total === 0) return 0;
  return (uiStore.progress.current / uiStore.progress.total) * 100;
});
</script>
