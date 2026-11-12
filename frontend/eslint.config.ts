import { globalIgnores } from 'eslint/config'
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import pluginVue from 'eslint-plugin-vue'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'

// To allow more languages other than `ts` in `.vue` files, uncomment the following lines:
// import { configureVueProject } from '@vue/eslint-config-typescript'
// configureVueProject({ scriptLangs: ['ts', 'tsx'] })
// More info at https://github.com/vuejs/eslint-config-typescript/#advanced-setup

export default defineConfigWithVueTs(
  {
    name: 'app/files-to-lint',
    files: ['**/*.{ts,mts,tsx,vue}'],
  },

  globalIgnores(['**/dist/**', '**/dist-ssr/**', '**/coverage/**', '**/.tmp/**']),

  pluginVue.configs['flat/essential'],
  vueTsConfigs.recommended,
  skipFormatting,

  {
    name: 'app/rules',
    rules: {
      // Vuetify 数据表格使用 v-slot:item.xxx 写法，需要允许 slot 修饰符
      'vue/valid-v-slot': ['error', { allowModifiers: true }],
    },
  },

  // ---------------------------------------------------------------------
  // T10 架构护栏（ARCH R-P2-3 / R-P2-4）：
  // 1. 后端路径只允许出现在 services/endpoints.ts，禁止裸写 '/api/'；
  // 2. 显示格式化统一走 utils/format.ts，禁止组件直接 toFixed/toLocaleString。
  // ---------------------------------------------------------------------
  {
    name: 'app/architecture-guards',
    files: ['**/*.{ts,mts,tsx,vue}'],
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector: "Literal[value*='/api/']",
          message:
            "禁止裸 '/api/' 字符串：请使用 @/services/endpoints 的 ENDPOINTS 常量或 api 门面。",
        },
        {
          selector: "TemplateElement[value.raw*='/api/']",
          message:
            "禁止在模板字符串中裸写 '/api/'：请使用 @/services/endpoints 的 ENDPOINTS 常量。",
        },
        {
          selector: "MemberExpression[property.name='toFixed']",
          message: '禁止直接调用 toFixed：请使用 @/utils/format 的格式化函数（formatFixed 等）。',
        },
        {
          selector: "MemberExpression[property.name='toLocaleString']",
          message:
            '禁止直接调用 toLocaleString：请使用 @/utils/format 的格式化函数（formatAmount 等）。',
        },
      ],
    },
  },

  {
    // 格式化工具本身是唯一合法实现点
    name: 'app/format-utils-exception',
    files: ['src/utils/format.ts', 'src/utils/tone.ts'],
    rules: {
      'no-restricted-syntax': 'off',
    },
  },
)
