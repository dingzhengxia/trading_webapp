<!-- frontend/src/components/AccessKeyDialog.vue (最终安全版) -->
<template>
  <v-dialog v-model="dialog" persistent max-width="400px">
    <v-card>
      <v-card-title>
        <span class="text-h5">请输入访问密钥</span>
      </v-card-title>
      <v-card-text>
        <p class="text-caption mb-4">
          为了安全访问后端服务，请输入在 `user_settings.json` 中配置的 `app_access_key`。
        </p>
        <v-form @submit.prevent="saveKey">
          <v-text-field
            v-model="inputKey"
            label="Access Key"
            required
            autofocus
            :error-messages="error"
            @input="error = ''"
            placeholder="只能包含英文、数字和符号"
          ></v-text-field>
        </v-form>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <!-- --- 核心修改：绑定 loading 状态并调用新 action --- -->
        <v-btn
          color="primary"
          variant="tonal"
          @click="saveKey"
          :loading="authStore.isLoading"
          :disabled="authStore.isLoading"
        >
          确认
        </v-btn>
        <!-- --- 修改结束 --- -->
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useAuthStore } from '@/stores/authStore'

const authStore = useAuthStore()
const inputKey = ref('')
const error = ref('')

const dialog = computed(() => !authStore.isAuthenticated)

// --- 核心修改：重写 saveKey 逻辑 ---
const saveKey = async () => {
  const key = inputKey.value.trim()
  if (!key) {
    error.value = '密钥不能为空'
    return
  }

  const validKeyRegex = /^[\x00-\xFF]*$/
  if (!validKeyRegex.test(key)) {
    error.value = '密钥包含无效字符 (例如中文)，请只使用英文、数字和符号。'
    return
  }
  error.value = ''

  // 调用新的验证 action
  const success = await authStore.validateAndSetKey(key)

  // 如果验证失败，在对话框中显示错误提示
  if (!success) {
    error.value = '访问密钥验证失败，请检查后重试。'
  }
  // 如果成功，isAuthenticated 会变为 true，对话框会自动关闭
}
// --- 修改结束 ---
</script>
