<!-- frontend/src/views/SettingsView.vue -->
<template>
  <v-container>
    <v-card>
      <v-card-title>应用设置</v-card-title>
      <v-card-text>
        <p class="mb-4">这里可以放置API密钥、主题切换、通知等高级设置。</p>
        <v-text-field label="API Key (示例)" variant="outlined" density="compact"></v-text-field>
        <v-text-field label="Secret Key (示例)" type="password" variant="outlined" density="compact"></v-text-field>
      </v-card-text>
    </v-card>
  </v-container>
</template>
