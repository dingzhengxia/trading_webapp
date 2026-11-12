# PRD — 增量重构 Phase 3（复用 / 性能 / 安全 / 限流合规 / 整合 / 完整性）

> 作者：产品经理 Alice（software-product-manager）
> 日期：2026-11-13（基于当日代码抽查核实）
> 范围：**只描述本次增量变更**，不重写历史。历史契约见 `REFACTORING_REPORT.md`（Phase 1）、`MERGE_PLAN.md`（Phase 2）、`CODE_REVIEW.md`（2026-11-06 审计）。
> 项目现状：后端 `backend/app` 约 12.4k 行（新增 protection v2、reports、open-history、signals dispatcher/tracker/exit 等模块），前端 `frontend/src` 约 9.6k 行。

---

## 1. 产品目标与重构范围

本次增量重构围绕六个维度，目标正交：

| 维度 | 目标 | 度量 |
|---|---|---|
| ① 代码复用 | 不允许存在 ≥10 行的重复代码段未合并；前端格式化/API 路径收敛到单一来源 | `rg` 扫描无 ≥10 行重复段；`toFixed/toLocaleString` 仅存在于 `utils/format.ts` |
| ② 性能 | 首屏体积与扫描线程派发降低 | Vuetify 按需引入后 CSS 显著缩减；策略线程派发从 O(策略数) 降到 O(symbol×timeframe) |
| ③ 安全 | WS 鉴权、密钥不泄露、裸仓不裸露 | 无 token 的 WS 连接被拒绝；SL/TP 失败后仓位不处于无保护状态 |
| ④ Binance API 限流合规 | **所有 REST 调用必须经 RestGuardian**（含交易链路） | 生产代码 grep 无绕过 RestGuardian 的 `exchange.<rest_method>` 直调（fake/test 除外） |
| ⑤ 整合 | 写入口收敛：每个配置域只有一条写路径；超大文件拆分 | 前端每个配置域只有一个 store/写入口；后端单文件 ≤800 行（analysis 策略文件除外） |
| ⑥ 程序完整功能 | 不留静默失效的功能（勾选了不生效、配置了不读取） | 每个前端可配置项有端到端生效验证或明确移除 |

**非目标**：不改变交易行为语义（见第 4 节约束）；不改 `signals/analysis/*` 策略判定逻辑；不引入需联网安装的新依赖（Vuetify 按需插件若本地不可用，见待确认问题 Q3）。

---

## 2. 现状核实结论（CODE_REVIEW.md 第 3 节逐条甄别）

> 方法：逐条对照当前代码抽查验证，未照抄旧报告。

### 2.1 P0 条目（原「资金安全」清单）

| 原条目 | 现状 | 结论 |
|---|---|---|
| P0-1 下单幂等 `newClientOrderId` | `logic/exchange_logic_async.py` 的 `create_order`（L355）仍不带 clientOrderId，超时后无反查机制。protection v2 仅为**自己的**单子生成 `PM_WS_R_*`（`protection/engine.py`），交易主链路未覆盖 | **仍有效，保留 P0** |
| P0-2 裸仓回收 | `process_order_with_sl_tp_async`（L518-524）SL/TP 失败仍只记 error 返回 False，仓位裸露。protection v2 可作事后兜底但其 `position_protection.enabled` 默认 False，不构成保障 | **仍有效，保留 P0** |
| P0-3 平仓可成交性兜底 | 平仓链路仍是纯 post-only 轮询重试（`_execute_maker_order_with_retry_async`），无盘口下调/IOC 兜底。protection v2 的应急减仓走市价是另一条路径，不解决反手任务失败 | **仍有效**（保留 P0，见 R-P0-3） |
| P0-4 持仓模式检测 | 交易主链路 `create_order`/平仓单不传 `positionSide`，启动时无 `fetch_position_mode` 探测。protection v2 已完整支持 Hedge Mode（`positionSide` 透传），但只保护它自己管理的仓位 | **仍有效，保留 P0**（主链路） |
| P0-5 最小名义价值校验 | 只有 `amount` 最小量检查（`_min_order_amount`），无 `minNotional`（5 USDT）校验，全仓 grep 无 4164 处理 | **仍有效，保留 P0** |
| P0-6 WS 鉴权 | `main.py` `/ws`（L85-100）无任何 token 校验，`services/websocket.ts` 也不带 token；任何能访问端口的人可收全部交易日志/持仓推送 | **仍有效，保留 P0** |

另核实（原第 1 节已修复项确认未回退）：入场价回退、full_symbol+方向精确匹配、全平复核补平、部分成交按剩余量重试、撤单失败即中止、密钥掩码、配置批量写、fetch_positions 异常上抛等均在。

### 2.2 P1 条目（可靠性/体验清单）

| 原条目 | 现状 | 结论 |
|---|---|---|
| P1-1 RestGuardian 接入交易链路 | `logic/*`、`core/trading_service.py`、`api/positions.py`、`api/rebalance.py` 全部直调 `exchange.fetch_positions/create_order/fetch_order/cancel_order/fetch_order_book/fetch_tickers`；RestGuardian 仅覆盖 signals 行情、protection、reports | **仍有效 → 升级为本次硬性要求（维度④）** |
| P1-2 配置热更新补全 | `scanner.py` 的 `signal_scan_interval_seconds` 仍在 `start()` 一次性读取（L122），循环内不刷新；`api_*` 限流参数不在 `DEFAULT_CONFIG`（前端不可改）；策略参数已迁 SQLite（`signals/config_store.py`，比旧报告演进） | **部分有效**（interval 热更新 + api_* 入 DEFAULT_CONFIG 保留；timeframes 等已由 config_store 解决 → 已过时部分删除） |
| P1-3 `high_funding_rate` 静默失效 | 全仓 grep 零匹配，白名单中已移除 | **已实施/已过时** |
| P1-4 扫描性能 | K 线已并发拉取（`asyncio.gather` + market_data in-flight 去重 + 共享 exchange）；但策略仍**每个策略一次 `to_thread`**（scanner L?: `asyncio.to_thread(func, ...)` 逐策略派发） | **部分实施**（K 线并发已完成；策略合并派发保留） |
| P1-5 `fetchSettings` 失败语义 | `settingsStore.saveGeneralSettings` 已返回 `{ok, detail}`，authStore 走 `/api/status` 探针 | **已实施** |
| P1-6 ControlPanel 草稿模式 | 无 `draft/cloneDeep/hydrated`；ControlPanel 3 个 watcher、CoinPoolsManager 5 个 watcher 仍并存；已改用 `patchSettings`（部分改善） | **大部分有效** |
| P1-7 再平衡计划后端重算 | 前端 `RebalanceDialog.vue` 无 `/api/rebalance/plan` 调用 | **仍有效**（降 P2，风险窗口小） |
| P1-8 Vuetify 按需引入 | `main.ts` 仍全量 `import * as components/directives`，vite.config 无 vite-plugin-vuetify、无 manualChunks | **仍有效** |
| P1-9 业务 ValueError → 400 | `api/rebalance.py` 已统一捕获 ValueError 转 400 | **已实施** |
| P1-10 前端写入口收敛 | `/api/settings` 只经 `settingsStore`（saveGeneralSettings/patchSettings）写入；`signal_auto_trade_enabled` 只走 `/api/signals/auto-trade`。但新增了散点：SignalsView 对 `/api/signals/config` 8 处逐字段 post、ProtectionView 直接 post `/api/protection/config` | **基本实施 + 新增散点纳入本次整合** |

### 2.3 P2 条目（可维护性清单）

| 原条目 | 现状 | 结论 |
|---|---|---|
| 拆分超大文件 | 好转但未完成：SignalsView 已拆出 `components/signals/*` 面板但主文件仍 **1222 行**；新增 **protection/engine.py 2108 行**（当前最大单文件）；ProtectionView.vue 827 行、ControlPanel.vue 630 行；ManualTradeView.vue 已不存在（并入/演进） | **仍有效，范围更新** |
| 抽公共工具 | `utils/format.ts` 已存在，但 `toFixed/toLocaleString` 仍散落 23 处（8 个文件）；无 `services/endpoints.ts`，API 路径字符串散落约 15 个路径 × 41 处引用 | **部分实施，继续** |
| 日志统一 | signals/protection/reports 用 loguru 且有 `ui_log_sink` 桥接；核心链路仍有 **30 处 `print`**（main.py 12、config.py 5、database.py 6、exchange_manager.py 3、open_history.py 1、signals/runtime.py 3） | **部分实施，继续** |
| 死代码清理 | 未系统核实（signals 新增多文件），随本次拆分顺带清理 | 仍有效 |
| 命名 `InterruptedError` | `logic/exceptions.py` 仍导出覆盖内建语义的 `InterruptedError`，exchange_logic L8 在用 | **仍有效** |
| eslint type-checked / vitest | 未启用 `recommendedTypeChecked`；无前端单测 | **仍有效** |
| config.py import 期副作用 | `config.py` L21 仍在 import 期执行 `database.init_db()`（建库+迁移） | **仍有效** |

### 2.4 旧报告未覆盖、本次新增发现（项目演进产生）

1. **protection/engine.py 巨石化（2108 行）**：单文件混含配置加载（自带 `_load_config`/`_deep_merge_defaults` —— 与 `signals/config_store.py` 又一套配置源）、JSON 状态持久化、stop/TP 管理、应急减仓、行情快照、锁与冷却六类职责。
2. **配置来源再度增多**：`load_settings()`（user settings）+ `signal_config.json`/config_store（策略参数）+ protection v2 内嵌 defaults —— protection 的配置既不在 settings 页也不在策略配置页，形成第三套。
3. **`fetch_klines_async`（exchange_logic L531）与 `signals/market_data.get_ohlcv` 职责重复**：rebalance 走前者（无缓存无限流），绕过 RestGuardian。
4. **前端 toggle 散点写**：SignalsView 对 `/api/signals/config` 有 8 处单字段 post（每个开关一个请求 + 一份错误处理），ProtectionView 表单整包 post，两者模式不同。
5. **防护市价单与静态审计的关系需固化**：protection v2 应急减仓使用市价（设计如此），`test_static_audit.py` 当前按 AST 全局断言无 market —— 需确认白名单口径有测试锁定，防止后续"偷偷"加开仓市价单或误报。

---

## 3. 需求池

优先级定义：P0 = 资金安全/安全，不做不能上线；P1 = 性能与限流合规；P2 = 复用与整合。

### P0（资金安全 / 安全）

#### R-P0-1 下单幂等：newClientOrderId + 超时反查
- **问题**：`_execute_maker_order_with_retry_async` 提交限价单后若 `create_order` 请求超时/网络断开，服务端可能已接单；当前直接判失败重下 → 双倍仓位。这是最典型的真实事故路径。
- **期望行为**：每次 `create_order` 带确定性 `newClientOrderId`（如 `TWA_{request_id}_{coin}_{seq}`，长度合规 ≤36）；捕获 `RequestTimeout/NetworkError` 后按 clientOrderId 调 `fetch_order`（或 `fetch_open_orders`）反查：查到 → 接管该单继续等待成交；查不到 → 才允许重下。SL/TP 条件单同样带 clientOrderId（`sl_tp_logic_async.py`）。
- **涉及文件**：`logic/exchange_logic_async.py`、`logic/sl_tp_logic_async.py`、`core/trading_service.py`（传递 request_id）。
- **验收标准**：离线测试 —— fake exchange 首次 `create_order` 抛 RequestTimeout 且订单实际入簿 → 断言不重复下单、原单被接管跟踪；查不到时才重试；clientOrderId 格式与唯一性有断言。

#### R-P0-2 裸仓回收（SL/TP 失败兜底）
- **问题**：开仓成功但 `set_tp_sl_for_position_async` 失败时仅返回 False，仓位无止损裸露，直到人工发现。
- **期望行为**：新增配置 `unprotected_position_action ∈ {auto_close, keep_alert}`，**默认 `auto_close`**：SL/TP 失败 → 立即对该仓位执行全平（复用 `close_position_async`，走限价 post-only + 全平复核）；全平也失败 → 置为 error 并在状态/前端强提示。`keep_alert` 时至少把任务标记为危险态。若 protection v2 已启用且接管该仓位，可跳过自动平仓（避免双重处置）。
- **涉及文件**：`logic/exchange_logic_async.py`、`config/config.py`（DEFAULT_CONFIG + 范围校验）、`core/trading_service.py`、前端设置页。
- **验收标准**：离线测试 —— SL/TP 注入失败 → 断言触发全平（reduceOnly 限价）且任务结果如实反映；`keep_alert` 分支不触碰仓位；protection 接管时不重复平仓。

#### R-P0-3 持仓模式检测（Hedge Mode 兼容，交易主链路）
- **问题**：账户若为双向持仓（Hedge Mode），交易主链路的 `create_order`/平仓单不带 `positionSide` 会被拒（-4061/-1106 类），开仓/平仓/反手全部失败；protection v2 已支持但主链路无探测。
- **期望行为**：`initialize_exchange_async` 后调用 `fetch_position_mode`（或读 position risk 的 positionSide 字段）探测一次；双向模式时主链路所有开仓/平仓/SL/TP 单自动补 `positionSide`（LONG/SHORT，跟随订单方向）。探测结果缓存在任务级 exchange 上下文。
- **涉及文件**：`logic/exchange_logic_async.py`（initialize + `_execute_maker_order_with_retry_async` + `close_position_async`）、`logic/sl_tp_logic_async.py`。
- **验收标准**：离线测试 —— fake exchange 报告 hedge 模式 → 断言所有 `create_order` params 含正确 `positionSide`；单向模式不携带；探测失败记 warning 并按单向继续（不静默吞）。

#### R-P0-4 最小名义价值校验
- **问题**：`amount * price < 5 USDT` 时交易所 -4164 拒单，导致整个任务失败而非跳过该币种。
- **期望行为**：下单前从 `market.limits.cost.min`（缺省按 5 USDT）校验目标名义价值；不足 → 记 skip 日志、跳过该币种、任务继续。
- **涉及文件**：`logic/exchange_logic_async.py`（`_execute_maker_order_with_retry_async` 或 `process_order_with_sl_tp_async`）。
- **验收标准**：离线测试 —— 价值 3 USDT 的 plan → 不调用 create_order、日志含 skip、任务其余币种正常完成。

#### R-P0-5 WebSocket 鉴权
- **问题**：`/ws` 无鉴权，任何能访问端口的人可接收全部交易日志、持仓与进度推送（信息泄露面）。
- **期望行为**：与 REST 相同的 `app_access_key` 校验：前端连接时带 `?token=`（取自 authStore）；后端 `websocket_endpoint` 握手阶段校验，失败立即 `close(code=4401)` 且不广播；token 缺失时后端日志记 warning（不打 token 内容）。降级策略：启动参数 `ws_auth_disabled`（默认 False，仅本机调试可开）。
- **涉及文件**：`main.py`、`core/websocket_manager.py`、`core/security.py`、`services/websocket.ts`。
- **验收标准**：离线测试 —— TestClient WS 无 token 连接被拒；正确 token 正常收消息；`websocket.ts` 单元路径（或类型检查+手动冒烟说明）。

### P1（性能与限流合规）

#### R-P1-1 交易链路全量接入 RestGuardian（维度④硬性要求）
- **问题**：`logic/*`、`trading_service`、`api/positions`、`api/rebalance` 直调 ccxt REST，绕过限流/熔断；扫描高峰与交易请求叠加时无统一背压。
- **期望行为**：为 ccxt 异步 exchange 增加统一包装层（建议 `core/guarded_exchange.py`：`GuardedExchange` 代理所有 REST 方法经 `RestGuardian.call`，读 LOW / 行情 NORMAL / **下单/撤单/查单 HIGH（绕过熔断）**）；`get_exchange_for_task()`/共享 exchange 返回包装实例，业务代码不改调用形态。**约束**：熔断绕过仅限 HIGH 优先级的关键交易操作；fake exchange 测试路径不受影响（代理透传）。
- **涉及文件**：`core/rest_guardian.py`、新增 `core/guarded_exchange.py`、`core/exchange_manager.py`、`signals/scanner.py`（去掉自管包装）、`api/rebalance.py`（`fetch_klines_async` 一并纳入）。
- **验收标准**：① grep 断言测试：生产代码（排除 fake/测试/代理层本身）无 `exchange.<rest>` 直调；② RestGuardian 测试补充：HIGH 绕过熔断下单仍受限流并发/间隔约束；③ 现有 pytest 全绿。

#### R-P1-2 配置热更新补全 + api_* 入 DEFAULT_CONFIG
- **问题**：`signal_scan_interval_seconds` 改动需重启扫描循环；限流参数 `api_*` 前端改不了（不在 DEFAULT_CONFIG）。
- **期望行为**：扫描循环每轮 sleep 前重新读 settings；`api_max_concurrency/api_min_interval_sec/api_max_retries/...` 加入 DEFAULT_CONFIG（带范围校验）并在设置页暴露；RestGuardian 支持运行中更新参数（或重建实例时热替换）。
- **涉及文件**：`signals/scanner.py`、`core/rest_guardian.py`、`config/config.py`、`api/settings.py`、前端设置页。
- **验收标准**：测试 —— 修改 interval 后下一轮 delay 生效（fake 时钟/事件驱动）；api_* 越界 400；生效无需重启。

#### R-P1-3 策略线程派发合并
- **问题**：每个策略一次 `asyncio.to_thread`（100 币×2 周期×N 策略 ≈ 上千次线程派发），线程池抖动大。
- **期望行为**：按 (symbol, timeframe) 合并：一次 `to_thread` 内顺序跑该组合的全部启用策略，派发次数降到 O(symbol×timeframe)。**不改动策略判定逻辑本身**。
- **涉及文件**：`signals/scanner.py`。
- **验收标准**：测试 —— mock to_thread 计数 ≤ symbol×timeframe；各策略产出与逐个派发结果一致（相同输入）。

#### R-P1-4 Vuetify 按需引入 + manualChunks
- **问题**：`main.ts` 全量引入 Vuetify 组件/指令，CSS ~805KB、字体 3.6MB 是首屏最大开销。
- **期望行为**：接入 vite-plugin-vuetify（components/directives autoImport），移除全量 import；vite `manualChunks` 拆 vuetify/echarts（如有）等大依赖；构建产物体积对比入验收报告。
- **涉及文件**：`frontend/vite.config.ts`、`main.ts`、`package.json`。
- **验收标准**：`npm run build` 成功、`vue-tsc --build --force` 0 错误；主包体积不高于现状且 CSS 总量显著下降；全部页面冒烟无缺失组件。

#### R-P1-5 平仓可成交性兜底（原 P0-3，按本次口径归 P1）
- **问题**：单边急跌时 post-only 平仓连续 `12s×retries` 不成交，反手/批量平仓任务直接失败，敞口滞留。
- **期望行为**：平仓（reduceOnly）单连续 2 轮 0 成交后，价格跟随盘口向可成交方向让价 1 tick 重挂（仍为限价单）；新增配置 `close_price_chase_ticks`（默认 1，0=关闭）。可选 `close_allow_ioc`（默认 False，需产品确认后启用）。**开仓不适用**（保持 post-only 语义）。
- **涉及文件**：`logic/exchange_logic_async.py`（平仓分支）、`config/config.py`。
- **验收标准**：离线测试 —— fake 盘口单边移动 → 平仓单价格按 tick 让价且类型始终 limit；让价开关关闭时行为与现状一致。

### P2（复用与整合）

#### R-P2-1 拆分 protection/engine.py（2108 行）
- **问题**：六类职责混于一个文件，任何改动都要理解全 2108 行；自带第三套配置源。
- **期望行为**：拆为 `protection/{config.py, state.py, stops.py, take_profit.py, exits.py, market_data.py}`（或按现有 runner/risk_model 边界收敛）；配置统一走 `signals/config_store` 同款「DB 优先、文件播种」模式（protection 用独立 key）；纯计算留在 risk_model。**不改变判定/动作语义**（现有 test_protection_v2 全绿为闸门）。
- **验收标准**：拆分后 pytest 全绿；单文件 ≤800 行；`_load_config` 重复实现删除。

#### R-P2-2 拆分前端超大视图
- **问题**：`SignalsView.vue` 1222 行、`ProtectionView.vue` 827 行、`ControlPanel.vue` 630 行，视图/请求/格式化混杂。
- **期望行为**：沿用既有先例（`components/signals/*` 面板 + PageCard）：SignalsView → `composables/useSignalsConfig.ts`（8 处 toggle 的统一读写 + 错误处理）+ 状态卡/表格组件；ProtectionView → `components/protection/{StatusCard,RiskSettingsPanel,ConfigForm}.vue` + `useProtectionConfig.ts`；ControlPanel → 草稿模式 composable（见 R-P2-4）+ 卡片子组件。
- **验收标准**：每个新文件 ≤400 行；`vue-tsc`/eslint 0 错误；页面行为回归（离线冒烟清单）。

#### R-P2-3 前端格式化与 API 路径收敛
- **问题**：`toFixed/toLocaleString` 23 处散落 8 文件（格式不一致：小数位/千分位）；API 路径字符串 15 个路径 41 处引用，改后端路由要全局搜。
- **期望行为**：金额/百分比/方向标签/时间统一走 `utils/format.ts`（扩展缺失函数）；新增 `services/endpoints.ts` 常量 + 强类型 API 函数，组件不得出现裸路径字符串（eslint 自定义规则或 grep 断言测试）。
- **验收标准**：grep 断言：views/components 中无 `'/api/` 字面量、无 `toFixed`/`toLocaleString`（format.ts 内除外）。

#### R-P2-4 写入口整合 + ControlPanel 草稿模式
- **问题**：SignalsView 8 处单字段 post（每个开关一个请求、8 份 try/catch）；ProtectionView 表单直写；ControlPanel 无草稿态（边改边存）、3 个 watcher；CoinPoolsManager 5 个 watcher 有 2 处重复逻辑。
- **期望行为**：`useSignalsConfig.ts`/`useProtectionConfig.ts` 统一 patch 写（仿 settingsStore.patchSettings 的 `{ok, detail}` 语义）；ControlPanel 改 `draft = cloneDeep(settings)` + diff 提交 + `hydrated` 闸门；CoinPoolsManager 重复 watcher 合并为一个 computed 驱动。
- **验收标准**：每个配置域只有一条写路径（grep 断言）；toggle 保存失败统一提示且不落库半套参数。

#### R-P2-5 日志统一与工程卫生
- **问题**：核心链路 30 处 `print`（main/config/database/exchange_manager/open_history/runtime）；`InterruptedError` 覆盖内建语义；config.py import 期建库。
- **期望行为**：`print` → loguru（DI 容器/模块级 logger），`ui_log_sink` 桥接保持 WS 日志抽屉行为；`InterruptedError` → `TaskInterruptedError`（全仓替换，含测试）；`database.init_db()` 移入 lifespan `init_app_storage()`（测试 fixture 同步调整）。
- **验收标准**：grep 断言生产代码无裸 `print(`（main.py 启动横幅等白名单除外，白名单入测试）；pytest 全绿；app import 不触发建库（新增断言）。

#### R-P2-6 重复 IO 收口：fetch_klines_async 并入 MarketDataService
- **问题**：`exchange_logic_async.fetch_klines_async`（rebalance 用）与 `signals/market_data.get_ohlcv` 重复 ≥10 行语义，且绕过限流无缓存。
- **期望行为**：rebalance 改用 MarketDataService（经 RestGuardian + TTL 缓存）；删除 `fetch_klines_async`。
- **验收标准**：rebalance 测试改走 fake market_data 全绿；`fetch_klines_async` 无残留引用。

#### R-P2-7 静态审计口径固化（防护市价单白名单）
- **问题**：protection v2 应急减仓合法使用市价，`test_static_audit.py` 全局断言无 market；两者关系目前靠实现细节偶然兼容，无明确白名单测试口径。
- **期望行为**：静态审计测试显式声明豁免清单（protection exits/reduce 路径，仅 reduceOnly/平仓方向），并断言豁免文件中不存在"开仓方向的市价单"；其余代码维持零市价。
- **验收标准**：`test_static_audit.py` 带白名单注释与断言；故意在豁免外文件加 market 单时测试失败（负向用例）。

---

## 4. 明确约束（本次及后续迭代共同遵守）

1. **不改变交易行为语义**：限价 post-only 开仓（市价开仓为零，条件单除外）；USDC 优先（`STABLECOIN_PREFERENCE = ['USDC','USDT']`）；SL/TP 先判断后撤单的既有顺序。
2. **配色语义不变**：红跌绿涨 → 前端「做多 = 绿、做空 = 红、观望 = 灰」，重构中不得调换（`utils/tone.ts` 为唯一语义色来源）。
3. **重复代码红线**：任何 ≥10 行的重复代码段必须合并复用；优先扩展现有共享组件（PageCard / PositionsTable / AppDockFooter / SmartSelect / MetricCard / EmptyState）而非新建平行实现。
4. **测试全离线**：pytest 不得访问网络/交易所（fake exchange / monkeypatch）；前端不引入需联网安装的运行时新依赖。
5. **默认不实际下单**：所有默认配置保持扫描/自动开仓/protection 关闭；本次开发与验收全程不使用真实下单（允许只读行情核对，需在验收报告中注明）。
6. **不改 `signals/analysis/*` 策略判定逻辑**；`static_audit` 护栏只扩展不删除。
7. **兼容性**：REST API 既有路径/鉴权方式不变（新增字段向后兼容）；SQLite `load_settings/save_settings` 接口不变。

---

## 5. 待确认问题（附建议默认值，不阻塞实施）

| # | 问题 | 建议默认值 |
|---|---|---|
| Q1 | R-P0-2 裸仓回收策略：SL/TP 失败后自动平仓 vs 仅告警？ | **默认 `auto_close`**（无保护敞口的资金风险 > 少一次开仓成本）；设置页可切 `keep_alert` |
| Q2 | R-P1-5 平仓兜底是否允许 IOC 限价？ | **默认关闭**（`close_allow_ioc=False`），先仅用让价 1 tick；观察实盘后再评估 |
| Q3 | Vuetify 按需引入需 `vite-plugin-vuetify`；若本机无网络无法安装怎么办？ | 优先尝试本地已缓存依赖（package-lock 已有该条目）；不可行则本项降级为「manualChunks 拆包 + 字体子集化」，按需引入留待联网迭代 |
| Q4 | WS 鉴权降级开关（本机调试免 token）是否会留下误配置风险？ | 保留但仅支持环境变量 `WS_AUTH_DISABLED=1` 且启动时打 error 级醒目告警；配置文件不支持该项 |
| Q5 | protection v2 的配置是否要并入设置页统一管理（第三套配置源）？ | 本次仅统一到 config_store 模式（DB 优先），**不**并入通用设置页（protection 参数专业性强，保持独立页）；待确认后可在 R-P2-1 顺带做 |
| Q6 | R-P1-1 中下单/撤单是否允许在熔断期间以 HIGH 绕过？ | **允许**（熔断不应阻断止损/平仓），但 HIGH 仍受并发与最小间隔约束，并有测试锁定 |
| Q7 | 验收时是否允许少量只读真实行情请求（校验限流封装在真实端点工作）？ | 允许只读（fetch_tickers/ohlcv 少量），下单类一律 mock；报告注明 |

---

## 6. 验收门槛（汇总）

1. `python -m compileall -q backend` 通过；`pytest backend/tests -q` 全绿（含新增 P0/P1 回归项）。
2. `npx eslint .`、`npx vue-tsc --build --force` 0 错误；`npm run build` 成功（TMP/TEMP 指向项目 `.tmp`，先清 dist）。
3. grep 断言测试通过：无裸 REST 直调（R-P1-1）、无 ≥10 行重复段（抽样）、无前端裸 API 路径、无裸 print（白名单外）。
4. 静态审计（R-P2-7 口径）通过：非豁免代码零市价单。
5. 验收报告：Vuetify 体积对比、线程派发计数对比、P0 各项测试清单。
