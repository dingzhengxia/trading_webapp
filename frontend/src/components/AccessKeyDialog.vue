<template>
  <v-dialog v-model="dialog" persistent max-width="400px">
    <v-card>
      <v-card-title>
        <span class="text-h5">请输入访问密钥</span>
      </v-card-title>
      <v-card-text>
        <v-form @submit.prevent="saveKey">
          <v-text-field
            v-model="inputKey"
            label="Access Key"
            required
            autofocus
            :error-messages="error"
          ></v-text-field>
        </v-form>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="primary" variant="tonal" @click="saveKey">确认</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useAuthStore } from '@/stores/authStore';

const authStore = useAuthStore();
const inputKey = ref('');
const error = ref('');

// 对话框的显示状态直接取决于 store 中是否有 key
const dialog = computed(() => !authStore.isAuthenticated);

const saveKey = () => {
  if (!inputKey.value.trim()) {
    error.value = '密钥不能为空';
    return;
  }
  error.value = '';
  authStore.setAccessKey(inputKey.value);
};
</script>
