<!-- frontend/src/components/ConfigDrawer.vue -->
<!-- 共享参数抽屉容器（规格 §3 A7）：交易页与信号页复用，禁止各写一套。
     PC（md+）：右侧 temporary 导航抽屉，宽 520；手机：全屏 dialog + 顶部工具栏。
     Tab 骨架由本组件提供，内容通过具名插槽注入（插槽名 = tab.key）。
     支持 ?tab= 深链：打开时按 query / defaultTab 定位，切换 Tab 时 router.replace 同步。

     结构固定为：标题行 → 分隔线 → Tabs → 滚动内容区 →（可选）动作区。
     动作区是滚动区的平级兄弟且排在最后，flex 列布局下天然贴底，
     不需要 position:sticky / elevation / box-shadow 也能常驻可见。 -->
<template>
  <!-- md+ 用导航抽屉、<md 用全屏对话框：外壳不同，内部结构完全一致，
       用动态组件复用同一份 Tab / 内容模板，避免两份重复代码 -->
  <component :is="overlayComponent" v-model="show" v-bind="overlayProps">
    <div class="config-drawer__frame d-flex flex-column">
      <div class="d-flex align-center ga-2 px-4 py-3">
        <v-icon v-if="icon" size="18" color="primary">{{ icon }}</v-icon>
        <span ref="titleEl" class="text-subtitle-1 font-weight-medium" tabindex="-1">
          {{ title }}
        </span>
        <v-spacer />
        <v-btn
          icon="mdi-close"
          variant="text"
          size="small"
          aria-label="关闭配置面板"
          @click="show = false"
        />
      </div>

      <v-divider />

      <v-tabs v-model="tab" class="tabs-quiet px-2" show-arrows>
        <v-tab v-for="item in tabs" :key="item.key" :value="item.key">
          <v-icon v-if="item.icon" start size="16">{{ item.icon }}</v-icon>
          {{ item.title }}
        </v-tab>
      </v-tabs>

      <div class="config-drawer__body flex-grow-1 overflow-y-auto pa-4">
        <v-window v-model="tab">
          <v-window-item v-for="item in tabs" :key="item.key" :value="item.key">
            <slot :name="item.key" />
          </v-window-item>
        </v-window>
      </div>

      <!-- 动作区：不随 Tab 切换隐藏（调用方不传 actions 插槽就整块不渲染，
           例如信号页）。tab 作为插槽 prop 暴露，便于调用方按 Tab 定制文案。 -->
      <template v-if="$slots.actions">
        <v-divider />
        <div class="config-drawer__actions" role="group" aria-label="开仓动作">
          <slot name="actions" :tab="tab" />
        </div>
      </template>
    </div>
  </component>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
// 按需引入（T12）：外壳组件经 <component :is> 动态渲染且 vite-plugin-vuetify
// 无法静态分析字符串派发，必须显式 import 并直接传组件对象（传字符串
// 'v-dialog' 在按需引入下查不到全局注册会退化为原生元素）
import { VDialog, VNavigationDrawer } from 'vuetify/components'

export interface ConfigTab {
  key: string
  title: string
  icon?: string
}

const props = withDefaults(
  defineProps<{
    title: string
    icon?: string
    tabs: ConfigTab[]
    defaultTab?: string
  }>(),
  { icon: '', defaultTab: '' },
)

const show = defineModel<boolean>({ default: false })

const { mdAndUp } = useDisplay()

const overlayComponent = computed(() => (mdAndUp.value ? VNavigationDrawer : VDialog))
const overlayProps = computed(() =>
  mdAndUp.value
    ? { location: 'right' as const, temporary: true, width: 520 }
    : { fullscreen: true },
)

const route = useRoute()
const router = useRouter()
const fallbackTab = (): string => props.defaultTab || props.tabs[0]?.key || ''

// 初始化即处理深链（组件挂载时 modelValue 就可能为 true，比如带着 ?tab= 直接进页面）
const initialQueryTab = String(route.query.tab ?? '')
const tab = ref(
  props.tabs.some((t) => t.key === initialQueryTab) ? initialQueryTab : fallbackTab(),
)

// 每次打开时按 query / defaultTab 重新定位，深链能力与旧版一致
watch(show, (open) => {
  if (!open) return
  const q = String(route.query.tab ?? '')
  tab.value = props.tabs.some((t) => t.key === q) ? q : fallbackTab()
})

// 切换 Tab 时同步到 ?tab=（保留其余 query），刷新/分享链接仍能落到同一 Tab
watch(tab, (key) => {
  if (!show.value || !key || key === route.query.tab) return
  void router.replace({ query: { ...route.query, tab: key } })
})

// ---- 焦点管理（键盘/读屏）：打开把焦点送到标题，关闭把焦点还给触发元素 ----
const titleEl = ref<HTMLElement | null>(null)
/** 打开瞬间的焦点位置：关闭后还回去，避免焦点掉到 body、键盘用户丢失位置 */
let restoreFocusTo: HTMLElement | null = null

watch(show, async (open) => {
  if (!open) {
    const target = restoreFocusTo
    restoreFocusTo = null
    await nextTick()
    target?.focus()
    return
  }
  const active = document.activeElement
  restoreFocusTo = active instanceof HTMLElement ? active : null
  // 等外壳挂载完再 focus；标题是 tabindex="-1"，只是程序化聚焦点，不进 Tab 序
  await nextTick()
  titleEl.value?.focus()
})
</script>

<style scoped>
.config-drawer__frame {
  height: 100%;
  min-height: 0;
  /* 手机上外壳是 v-dialog（全屏），对话框本身没有底色，
     不给 surface 会和背后的页面叠在一起看不清 */
  background: rgb(var(--v-theme-surface));
}

/* 抽屉内一律单列：面板原本是按整页宽度写的 md=6 / md=4 栅格，
   塞进 520px 抽屉后每列只剩 150–240px，标签会被描边压住、hint 会互相挤。
   断点判断基于视口宽度（不是容器宽度），所以只能在这里强制拉平。
   注意 Vuetify 的列没有裸 .v-col 类（是 v-col-12 / v-col-md-6），必须用属性匹配。 */
.config-drawer__body :deep([class*='v-col']) {
  flex: 0 0 100%;
  max-width: 100%;
}

/* 动作区：常驻在滚动区之外的最后一块。
   底色必须显式给 surface —— 手机壳是 v-dialog，内容区滚动到底时
   半透明叠层会透出后面的页面；这里用实心 surface 收口。
   不加 box-shadow / elevation / sticky：它是 flex 列的最后一项，本来就不动。 */
.config-drawer__actions {
  background: rgb(var(--v-theme-surface));
  padding: 12px 16px;
}

/* 手机断点（与 base.css 的 960px 保持一致）：底部安全区避让，
   否则 iPhone 的 Home 指示条会压住主按钮 */
@media (max-width: 959px) {
  .config-drawer__actions {
    padding-bottom: max(12px, env(safe-area-inset-bottom));
  }
}
</style>
