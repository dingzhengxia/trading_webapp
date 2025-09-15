<!-- 文件路径: frontend/src/components/Snackbar.vue -->
<template>
  <v-snackbar
    v-model="snackbarStore.visible"
    :timeout="snackbarStore.timeout"
    :color="snackbarStore.color"
    location="bottom right"
  >
    {{ snackbarStore.message }}
    <template v-slot:actions>
      <v-btn variant="text" @click="snackbarStore.hide()">
        关闭
      </v-btn>
    </template>
  </v-snackbar>
</template>

<script setup lang="ts">
import { useSnackbarStore } from '@/stores/snackbar';

const snackbarStore = useSnackbarStore();
</script>
