# 交易终端 · 结构性重设计实施规格（2026-11-13）

> 本文件是实施契约。视觉骨架由 frontend-design-architect 产出，信息架构与任务流由 ux-ui-designer 产出，本文件由 team-lead 汇编并裁定冲突项。
> **实施者必须按本文件执行，不要重新做设计决策。** 若发现规格内部冲突，先报告，不要自行改方案。

---

## 0. 背景

应用当前 6 个一级页面存在三类结构性问题：

1. **页面与内容错位**：仪表盘只有 26 行且与交易页重复；交易页 64 个表单控件占满上半屏，持仓表被挤到一屏半以下；信号页把「看列表」与「配参数」混在 4 个 Tab 里。
2. **参数四处散落**：117 个表单控件分布在 4 个页面（交易 64 / 风控 40 / 信号 11 / 设置 5），用户「调一遍策略」需横跨 4 页约 12 步。
3. **手机端只有单层汉堡菜单**：6 个一级页面切换各需 2 步；9 列信号表、6 列持仓表在手机上横向滚动。

本次重设计目标：**让高频任务一步可达、让参数在同一个页面内可配完、让手机端不再是「PC 缩小版」**。

---

## 1. 信息架构定稿

### 1.1 一级导航

| 顺序 | 名称 | 路由 | 图标 | 位置 |
|---|---|---|---|---|
| 1 | 交易 | `/trading` | `mdi-candlestick-chart` | 底部 Tab 第 1 项 / PC 侧栏第 1 项 / **默认落地页** |
| 2 | 信号 | `/signals` | `mdi-radar` | 底部 Tab 第 2 项 |
| 3 | 风控 | `/protection` | `mdi-shield-check-outline` | 底部 Tab 第 3 项 |
| 4 | 总览 | `/overview` | `mdi-view-dashboard-outline` | 底部 Tab 第 4 项 |
| — | 更多 | 抽屉 | `mdi-dots-horizontal` | 底部 Tab 第 5 项（仅手机） |

「更多」抽屉内含：周期报告 `/reports`（`mdi-newspaper-variant-outline`）、设置 `/settings`（`mdi-cogs`）。

**命名变更**（router meta.title 同步）：仪表盘→**总览**、交易终端→**交易**、信号监控→**信号**、仓位保护→**风控**、应用设置→**设置**。

**路由变更（唯一允许的 path 改动）**：
- `/` → `redirect: '/trading'`（默认落地到最高频任务）
- 总览页 path 由 `/` 改为 `/overview`
- 其余 path 不变

**裁定依据（体验侧定稿）**：Tab 顺序按任务频率（交易最高频），同时让默认落地页 = 最左 Tab，两个目标同时满足。`/` 保留为重定向而不是总览，是为了让「输入域名 → 落在最左 Tab」这条心智模型成立。
**裁定（风控守卫表）**：md（960–1280）保留横滚，但默认隐藏「开仓价」列；lg+ 显示全部列。xs 走卡片化。

### 1.2 每页职责（一句话）

| 页面 | 职责 | 首屏必须看到 |
|---|---|---|
| 交易 | 动作：盯仓 / 开仓 / 平仓 | 盈亏条 + 持仓表 |
| 信号 | 监控：看信号 | KPI 行 + 信号列表 |
| 风控 | 查守卫状态（参数折叠） | 状态卡 + 守卫中的仓位 |
| 总览 | 巡检：账务 + 系统健康度 | KPI 行 + 系统状态条 |
| 报告 | 看报告（配置折叠） | 最近报告内容 |
| 设置 | 一次性配置 | API 配置表单 |

---

## 2. 全局约束（不可违反）

### 2.1 断点
- xs `<600` / sm `600–960` / md `960–1280` / lg `≥1280`
- **md 及以下一律单列**；双列只在 lg+ 出现（交易页主区:侧栏 8:4；总览多空摘要 6:6）
- sm 段：表单字段 `cols="12" sm="6"`，禁止出现 3 列以上

### 2.2 高度令牌（base.css `:root`）
- `--tabbar-h: 56px`（底部 Tab 栏）
- `--dock-h: 64px`（固定操作条，当前 :root 写的 80px 与实际不符，必须改为 64）
- 两者均需叠加 `env(safe-area-inset-bottom)`（只在手机断点）

### 2.3 底部留白（P0 修复）
**现状错误**：`base.css` 无条件 `.v-main { padding-bottom: var(--dock-h) }`，导致总览/信号/风控/报告四个没有操作条的页面底部永久多出 80px 空洞，且 :root 的 80px 与 AppDockFooter 实际 64px 不符。

**正确规则**（按页面声明，不按全局）：
- `md+`：无 dock 页面 `padding-bottom: 24px`；有 dock 页面 `calc(var(--dock-h) + 24px)`
- `xs/sm`：无 dock 页面 `calc(var(--tabbar-h) + 16px)`；有 dock 页面 `calc(var(--tabbar-h) + var(--dock-h) + 16px)`
- 由路由 meta `hasDock: true` 驱动（`/trading`、`/settings` 为 true）

### 2.4 视觉层级
- 卡片标题 **16px/600**；表格工具栏标题 **14px/600**（现在的 `text-h6` 是 20px，与 KPI 数字同级，必须降级）
- L1 数字 20px/600 + `.num`；数据正文 13px；辅助说明 12px
- 一屏只允许一组 L1 数字；方向/盈亏色只出现在 L1 数字与 `.dir-badge` 上

### 2.5 表格降级判据
- **≥6 列且在 xs** → 卡片化；≤5 列 → 保留横滚 + 首列 `position: sticky; left: 0`
- sm（600–960）不降级，保留横滚
- 现有可复用组件：`MetricCard` / `SectionHeader` / `EmptyState` / `PageSkeleton` / `PageCard` / `tone.ts` / `format.ts`。**新写组件前先确认没有可复用的。**

### 2.6 不可改动
- 后端接口、`stores/*` 的数据结构与既有 action 名称
- `src/theme/index.ts` 色板、`src/utils/tone.ts` 判色入口
- 路由 path 除第 1.1 节明确的三处变动（`/` 重定向、总览改 `/overview`）外不得改动
- 各页面既有的保存/启动/平仓等动作语义不得改变（只允许改变它们出现的位置）

---

## 3. 工作包 A：应用外壳 + 交易页 + 信号页

**文件所有权：以下文件只允许 WP-A 修改。**

### A1. `src/config/nav.ts`（新建）
导航单一数据源，App.vue / BottomTabBar / 侧栏共用，避免两处重复维护。

```ts
export interface NavItem { path: string; title: string; icon: string }
export const primaryNav: NavItem[] = [
  { path: '/trading', title: '交易', icon: 'mdi-candlestick-chart' },
  { path: '/signals', title: '信号', icon: 'mdi-radar' },
  { path: '/protection', title: '风控', icon: 'mdi-shield-check-outline' },
  { path: '/overview', title: '总览', icon: 'mdi-view-dashboard-outline' },
]
export const secondaryNav: NavItem[] = [
  { path: '/reports', title: '周期报告', icon: 'mdi-newspaper-variant-outline' },
  { path: '/settings', title: '设置', icon: 'mdi-cogs' },
]
```

### A2. `src/router.ts`
- 改 `meta.title`（按 1.1 命名表）与图标
- `/` 改为 `{ path: '/', redirect: '/trading' }`
- 总览页改为 `{ path: '/overview', name: 'overview', component: DashboardView, meta: { title: '总览', icon: 'mdi-view-dashboard-outline' } }`
- 给 `/trading`、`/settings` 加 `meta: { hasDock: true }`，并在 RouteMeta 声明里补 `hasDock?: boolean`

### A3. `src/components/BottomTabBar.vue`（新建）
- 手机专用（`class="d-md-none"`），固定底部，高 `var(--tabbar-h)` + `env(safe-area-inset-bottom)`
- 4 个 `primaryNav` 项 + 第 5 项「更多」（`mdi-dots-horizontal`，点击 emit `open-more`）
- 当前路由高亮：`path` 精确匹配；`/trading` 为默认落地，进入 `/` 时已被重定向，无需特殊处理
- 语义：`<nav role="navigation" aria-label="主导航">`，每项含图标 + 10px 文字，触控区高 ≥56px
- 样式写进 `base.css` 的 `.app-tabbar` 规则里，组件内不写 scoped 布局硬编码

### A4. `src/App.vue`
- app-bar 结构改为：**左**（`d-md-none` 汉堡按钮）→ 标题 → spacer → 状态 chip → 主题 → 日志
  - 状态 chip 在 `<600px` 只显示 8px 圆点（隐藏文字），避免 375px 下 5 个元素挤压
- 抽屉：`mdAndUp` 才 permanent；手机 overlay，宽 `min(280px, 80vw)`
- 侧栏导航改用 `nav.ts`：`primaryNav` + `v-divider` + `secondaryNav`，与底部 Tab 顺序一致
- `<v-main :class="{ 'with-dock': hasDock }">`，`hasDock` 从 `route.meta.hasDock` 计算
- 挂载 `<BottomTabBar @open-more="drawer = true" />`
- 「更多」打开的是同一个抽屉（手机上抽屉只需展示 secondaryNav，primaryNav 已在 Tab 栏）

### A5. `src/styles/base.css`
- 修正 `--dock-h: 64px`，新增 `--tabbar-h: 56px`
- **删除**全局 `.v-main { padding-bottom: var(--dock-h) }`，改为按 2.3 的规则（`.v-main` / `.v-main.with-dock`，配合 `@media (max-width: 959px)`）
- 新增 `.app-tabbar` 样式（含 safe-area、毛玻璃或纯色底、上边框用 `--v-border-color`）
- `.app-dock` 在 `@media (max-width: 959px)` 下 `bottom: calc(var(--tabbar-h) + env(safe-area-inset-bottom))`
- 卡片标题降级工具类（若需要）：统一在组件里用 `text-subtitle-1 font-weight-medium`，不要新增工具类

### A6. `src/components/AppDockFooter.vue`
- 内容区对齐 `.page-shell` 的 `max-width: 1600px`（现在全宽，与窄列设置页失衡）
- 手机上按 A5 抬高 `bottom`

### A7. `src/components/ConfigDrawer.vue`（新建，共享容器）
交易页与信号页共用，**必须复用，禁止各写一套**。

- Props：`modelValue`、`title`、`icon`、`tabs: { key: string; title: string; icon?: string }[]`、`defaultTab?`
- PC（`mdAndUp`）：右侧 `v-navigation-drawer`，宽 520，`temporary`
- 手机：全屏 `v-dialog`（`fullscreen`）+ 顶部工具栏（标题 + 关闭）
- 内部：`v-tabs`（`class="tabs-quiet"`）+ `v-window`，每个 Tab 用 `<slot :name="tab.key" />`
- 抽屉打开时，页面 dock 被遮罩覆盖（Vuetify overlay 天然满足，无需额外处理）
- 支持 `?tab=` 深链：`modelValue` 为 true 时按 `defaultTab` 或 query 选 Tab，切换 Tab 时同步 `router.replace({ query })`（保留现有深链能力）

### A8. `src/views/TradingView.vue`
- 区块顺序改为：`PnlSummary` → `PositionsPanel`（多空持仓表，lg 双列 6:6，<lg 纵向）→ `OpenHistoryPanel`
- `ControlPanel` **整体移入 ConfigDrawer**，Tab 结构保持：`general`（通用开仓设置）/ `rebalance`（智能再平衡）
- dock 按钮改为三个：`开仓设置`（`mdi-tune-vertical`，打开抽屉）/ `校准 SL/TP` / `开始开仓`
- 「生成再平衡计划」从 dock 移入抽屉的 rebalance Tab 底部（它依赖该 Tab 的参数）
- 首次进入且 `settingsStore.settings` 中多空币种列表均为空时，在持仓表上方显示可关闭的 `v-alert`：「还没配置开仓参数，先设置币种与金额 →」，点击打开抽屉
- `activeTab` 与 dock 的联动逻辑随之调整（现在只服务抽屉内部）

### A9. `src/components/ControlPanel.vue`
- 内部逻辑、`settingsStore` 交互、两个 Tab 内容**全部保留**
- 只做两件事：①移除自身 `v-card` 外框改为抽屉内容（或保留 card 但去掉阴影，二选一，保持视觉一致即可）；②把「生成再平衡计划」按钮接入 rebalance Tab 底部（新增 props `isGeneratingPlan` + emit `generate-rebalance`，由父组件传实现）
- `h3` 标题若有残留，改 `SectionHeader`

### A10. `src/views/SignalsView.vue`
- 页面只保留：KPI×4 → 状态点行 + 最近错误 Alert → **信号列表**（首屏可见）→ 「纸面跟踪明细」折叠区（`v-expansion-panel`，默认收起，含纸面持仓/已平仓统计/前视收益）
- `ScanScopePanel` / `PushAutoPanel` / `ExitStatsPanel` 的**参数部分**迁入 ConfigDrawer（3 个 Tab：扫描范围 / 推送与开仓 / 出场规则）
- `ExitStatsPanel` 拆分为两块：**查看类**（纸面持仓、已平仓统计、前视收益）留在页面折叠区；**参数类**（出场层规则、实盘超时/巡检参数）进抽屉
- 信号列表工具栏右侧加 `配置` 按钮（`mdi-cog`）打开抽屉
- 保留 `?tab=` 深链，映射到抽屉 Tab

### A11. `src/components/signals/SignalListPanel.vue`
- **xs 卡片化**（9 列，满足降级判据）：
  - 头行：币种（14px/600）+ `.dir-badge` + 时间（右，12px）
  - 次行：策略 · 周期 · 价格（12px，`.num`）
  - 第三行：量能达标色点 + 量能倍数（若 > 门槛用 `up` 色，否则 `text-medium-emphasis`）
  - **可点展开**：展开后显示量能与前视收益、完整 `message`（3 行 clamp）
- sm+ 保留现有表格，外层加 `overflow-x: auto` + 首列 sticky
- `前视` 列在 xs 隐藏（进展开区）

---

## 4. 工作包 B：总览页 + 风控页 + 报告页 + 移动端表格

**文件所有权：以下文件只允许 WP-B 修改。**
**WP-B 不得修改：`App.vue` / `router.ts` / `base.css` / `mobile.css` / `AppDockFooter.vue` / `BottomTabBar.vue` / `ConfigDrawer.vue` / `TradingView.vue` / `SignalsView.vue` / `ControlPanel.vue` / `signals/*`。**

### B1. `src/views/DashboardView.vue`（重写为总览）
区块顺序：
1. **KPI 行**（4 个 `MetricCard`，xs 两列）：总浮动盈亏（`pnlTone`）/ 持仓数 / 总名义价值 / 今日已实现（若无接口则显示「—」并留注释）
2. **系统状态条**（新组件 `components/overview/SystemStatusStrip.vue`）：4 个可点击状态块 —— 扫描（开/关 + 上次扫描时间）/ 自动开仓（开/关）/ 风控（守护中 / 停用 + 守卫仓位数）/ 连接（WS 状态）。异常项用 `error` 色描边，点击跳对应页面
3. **多空持仓摘要**（`lg` 6:6 双列，<lg 纵向，新组件 `components/overview/PositionSideSummary.vue`）：每侧显示「N 个持仓 · 总价值 · 盈亏合计」+ 最新 3 条紧凑行（合约 / 盈亏%），底部「查看全部 →」跳 `/trading`
4. **最新信号 Top 3**（紧凑列表，点击跳 `/signals`）
5. **风控最近动作 Top 3**（复用风控接口的 `recent_actions`，点击跳 `/protection`）

**必须移除**：完整可操作的 `PositionsPanel`（平仓/反手操作只允许在交易页出现，保证入口唯一）。总览页只做只读聚合。

### B2. `src/views/ProtectionView.vue`
- 首屏只留：状态卡（启用/演练/守护中/chips）→ 守卫中的仓位表 → 最近保护动作
- **40 个参数控件收进 `v-expansion-panels`**，分三组：核心参数 / v2 分档参数 / 执行开关（浮盈保护·紧急止损·灾难止损）
- 折叠面板标题行必须显示当前值摘要（如「核心参数 · TP1 2% / TP2 4% / 回看 20」），收起状态也能读到关键值
- 守卫表：xs 卡片化（TP1/TP2/躺平三列合并为 chip 组，点开看具体价），md 隐藏「开仓价」列，lg 全列
- 保存按钮保持在页面底部 dock 还是页内？——**保持现状（页内保存按钮）**，本页无 dock

### B3. `src/views/ReportsView.vue`
- 顺序改为：**最近报告内容置顶** → 报告卡片×N（开关/周期/生成）→ 钉钉推送配置（`.env` 说明长文默认折叠成一行「推送配置说明 ▸」）
- 报告配置卡 `lg="6"` 双列

### B4. `src/components/PositionsTable.vue`
- **xs 卡片化**：头行 合约 + `.dir-badge` + 浮动盈亏（`.num` 16px/600，up/down 色，右对齐）；次行 回报率 · 名义价值（12px 两列网格）；底部 反手 / 平仓按钮（高 40px，右对齐）
- xs 隐藏 checkbox 列与「开仓均价」（进卡片展开）
- 批量选择：xs 用卡片长按多选或顶部「多选」开关（实现任选其一，能完成批量平仓即可）
- sm+ 保留表格；`height` 在 xs 改为 `auto`（现在两张表各 45vh，加起来 90vh，手机上交易页一屏放不下别的）
- 行内按钮 size 从 `x-small` 提到 `small`（手机触控）

### B5. `src/components/OpenHistoryPanel.vue`
- xs 卡片化：币种 / 动作来源 / 时间 / 结果状态；选币快照细节进展开
- 若判定列数 ≤5 则保留横滚 + sticky 首列（实施者按实际列数判断，并在报告里说明结论）

---

## 5. 验收标准

每个工作包自检，全部满足才算完成：

1. `npx vue-tsc --build --force` 零错误
2. `npm run build` 通过（含对比度守门脚本）；WP-B 若与 WP-A 并行，**不要跑 `npm run build`**，只跑类型检查，最终构建由主理人统一执行
3. 1440px / 1280px / 1024px / 768px / 375px 五个宽度下无横向溢出（`document.documentElement.scrollWidth <= innerWidth + 1`）
4. 375px 下：底部 Tab 栏 5 项可点、当前页高亮正确；有 dock 的页面 dock 浮在 Tab 栏之上不重叠；无 dock 的页面底部无多余空白
5. 深色与浅色主题下均无「浅底浅字」或硬编码色（不得出现 `#fff` / `rgba(0,0,0,...)` 之类裸色值，除既有合法用法）
6. 关键操作（开始开仓 / 平仓 / 反手 / 保存）在改造后功能不变——必须实际点击验证，不能只看代码
7. 无新增 ≥10 行的重复代码块；相同结构必须提组件（尤其是卡片容器、状态条、摘要行）

## 6. 交付报告格式

完成后向 team-lead 报告：改动文件清单（含新增）、每个工作包的完成项与未完成项、验收 1–7 的实测结果、发现的规格冲突或风险。**不要只写「已完成」。**
