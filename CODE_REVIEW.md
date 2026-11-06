# 代码审计与重构报告（2026-11-06）

> 范围：`backend/app`（约 5.7k 行）+ `backend/tests` + `frontend/src`（约 5.3k 行）+ 工程配置
> 方法：通读 + 两路独立审计（后端/前端）+ 离线测试（`pytest` 147 passed、eslint/vue-tsc 0 错误）
> 结论：整体架构清晰、Phase 1/2 的功能与测试基础良好；本次修复了 **10 项资金安全/可靠性缺陷**，
> 并给出 **按优先级排序的后续改动建议**。未做的项目均为需要产品决策或较大改造，已在第 3 节标注。

---

## 1. 本次已实施（安全优先，全部有测试或构建验证）

| # | 问题 | 位置 | 改动 |
|---|---|---|---|
| 1 | 同步 SL/TP 先撤单再生产判断导致“关闭保护”反被清空 | `logic/sl_tp_logic_async.py` | 改为「先判断是否需要挂单 → 再撤单 → 再挂单」；关闭保护时完全不触碰挂单 |
| 2 | `cancel_all_orders` 永远返回 True，撤单失败后仍继续挂新单 | 同上 | 返回真实结果；撤单失败即中止，避免条件单叠加 |
| 3 | `breakEvenPrice` 返回 `"0"` 时入场价恒为 0，SL/TP 被静默跳过 | `logic/exchange_logic_async.py` | `<=0` 时回退 `entryPrice`（再回退 `info.entryPrice`） |
| 4 | 开仓后仓位匹配按 base coin 降级，可能给旧仓/反向仓挂错 SL/TP | 同上 | 只保留 `full_symbol + 方向` 精确匹配 |
| 5 | SL/TP 下单失败仍打印“完全成功”并返回 True | 同上 | 消费返回值；失败记 error 并返回 False（提示人工处理） |
| 6 | 超时撤单失败/撤单后查不到成交状态仍继续重下 → 双倍敞口 | 同上 | 撤单失败或成交状态未知时立即 `return False` 并记 error |
| 7 | 平仓“无持仓 / 数量为 0 / 精度截断为 0”返回 True，前端乐观删除仓位 | 同上 | 统一返回 False（未实际平仓不得报告成功） |
| 8 | 日志广播同步等待所有 WebSocket，慢客户端可卡住下单/平仓 | `core/websocket_manager.py` | 广播改为后台发送 + 单连接 3s 超时 + 失败摘除；历史日志任务持有引用 |
| 9 | 配置逐键写库，中途失败留下“半套风控参数”；`load_settings` 浅拷贝污染缓存 | `core/database.py`、`config/config.py` | 新增 `set_many` 单事务批量写；`load_settings` 返回深拷贝 |
| 10 | `GET /api/settings` 明文回传交易所 Key；保存失败仍返回 200 | `api/settings.py` | 密钥掩码返回（`abcd****wxyz`）；掩码回写视为“不修改”；失败改 500；新增交易参数范围校验（杠杆 1–125、百分比 0–1000 等，越界 400） |
| 11 | 信号 K 线共享 Future 在 owner 被取消时永不完成，等待者永久挂起 | `signals/market_data.py` | `except BaseException` 传播 `CancelledError` |
| 12 | 任务被拒绝时协程未 await；`schedule_task` 无事件循环时 `_is_running` 永久卡死 | `core/trading_service.py` | 拒绝时关闭协程；create_task 失败回滚锁状态 |
| 13 | 前端密钥校验恒成功（`fetchSettings` 吞异常），无效 Key 被写回 localStorage | `stores/authStore.ts` | 改用 `GET /api/status` 探针，失败即清理 Key 并返回 false |
| 14 | WebSocket 重连后不做对账，断线期间的平仓事件永久丢失 | `services/websocket.ts` | onopen 触发持仓+任务状态全量同步；重连改指数退避 1s→30s |
| 15 | 停止指令无兜底，后端不广播结束状态时按钮永久不可用 | `stores/uiStore.ts` | 15s 未确认则恢复交互并提示重试 |
| 16 | 手动交易页无执行确认、不校验交易对可用性 | `views/ManualTradeView.vue` | 新增执行前汇总确认弹窗（含反手提示）；不可用交易对禁止提交 |
| 17 | 设置页可能把 `''` / `NaN` 原样落库（杠杆、止损百分比变非法值） | `stores/settingsStore.ts` | 保存前过滤空值/NaN；新增 `patchSettings` 增量更新 |
| 18 | `manual_trade_preset` 只写后端不回写 store，会被其它页面整包保存覆盖 | 同上 + `ManualTradeView` | 统一走 `patchSettings`，内存与后端一致 |
| 19 | 全部页面静态 import，首屏单包 693KB | `router.ts` | 路由懒加载，页面拆分为独立 chunk（主包降至 611KB） |
| 20 | 前端日志无上限 | `stores/logStore.ts` | 上限 500 条 |

新增回归测试：`backend/tests/test_safety_regressions.py`（14 项，覆盖入场价回退、SL/TP 不误撤单、平仓返回值语义、配置校验、密钥掩码）。

---

## 2. 项目整体评估

### 做得好的地方
- 限价 post-only 全链路（开仓/平仓/反手）有静态审计测试守护，市价开仓为零；
- USDC 优先、部分成交按剩余量重试、全平后复核残留，这些资金安全细节已落地；
- 测试完全离线（147 项），fake exchange 覆盖度高，重构有安全网；
- 信号/交易分层清晰：纯逻辑（plan/manual_trade）与 IO 分离，可单测；
- SQLite 迁移保持了 `load_settings/save_settings` 接口不变，前端零感知。

### 主要结构性问题
1. **日志体系双轨**：核心链路 28 处 `print`，signals 用 loguru，Docker 下难以按级别过滤。
2. **配置来源三套**：请求体（TradePlanRequest）、`load_settings()`、`signal_config.json`，同名参数定义重复，容易出现“改了不生效”。
3. **超大文件**：`SignalsView.vue` 924 行、`ControlPanel.vue` 627 行、`ManualTradeView.vue` 556 行、`exchange_logic_async.py` 498 行，视图/数据处理/请求混杂。
4. **写入口分散**：`/api/settings` 被 3 处前端直接写，`signal_auto_trade_enabled` 有两个接口可写，缓存一致性靠人工保证。
5. **前端重复实现**：币种多选控件 4 份、数字格式化 6 份、固定底栏 4 份。
6. **工程化缺口**：eslint 未启用 type-checked 规则（查不出 floating promise）、无前端单测、lock 与新依赖不一致。

---

## 3. 后续改动建议（按优先级，未实施）

### P0 — 建议下一迭代优先做（资金安全）
| # | 建议 | 位置 | 工作量 | 说明 |
|---|---|---|---|---|
| 1 | **下单幂等**：每题带确定性 `newClientOrderId`，`create_order` 超时后按 clientOrderId 反查，查到则接管，查不到才重下 | `exchange_logic_async.py:326` | M | 当前超时可能“服务端已接单”，重试即双倍仓位，是最典型的真实事故路径 |
| 2 | **裸仓回收**：开仓成功但 SL/TP 失败时，按配置自动全平（或至少把任务置为“危险”并强提示） | `exchange_logic_async.py:480` | M | 需产品确认“无保护不开仓”策略；当前只返回 False，仓位仍裸露 |
| 3 | **平仓可成交性兜底**：平仓失败升级策略（跟随盘口下调 1 tick / 可选 IOC 限价，仍非市价） | `_execute_maker_order...` | M | 单边急跌时 post-only 可能连续 12s×4 轮不成交，反手任务直接失败 |
| 4 | **持仓模式检测**：启动时 `fetch_position_mode`，双向持仓账户需补 `positionSide` | `initialize_exchange_async` | M | 双向模式下 `reduceOnly` 全被拒（-1106），当前无探测 |
| 5 | **最小名义价值校验**：`amount * price < 5 USDT` 时明确跳过并记 skip | 下单前 | S | 小额/高价币会被交易所 -4164 拒绝，任务整体失败 |
| 6 | **WS 鉴权**：`/ws?token=` 与 `app_access_key` 比对 | `main.py`、`websocket.ts` | S | 当前任何能访问端口的人都能收到全部交易日志/持仓信息 |

### P1 — 可靠性与体验
1. **RestGuardian 接入交易链路**（`fetch_positions/create_order/fetch_order/cancel_order`），下单用 HIGH 绕过熔断。目前它只包了 3 个行情接口，验收文档“全部请求走限流”与实际不符。
2. **配置热更新补全**：`signal_scan_interval_seconds` 改动需重启循环才生效；`signal_ticker/ohlcv_cache_seconds` 只在首次创建读取；`api_*` 未进 `DEFAULT_CONFIG`（前端改不了）；`signal_config.json` 里 `app_settings/market_settings.timeframes/dynamic_scan` 无人读取。
3. **`high_funding_rate` 策略未注册**却出现在自动开仓白名单 —— 勾选后永不触发，属静默失效（删除或实现）。
4. **扫描性能**：K 线串行拉取（100 币×2 周期）→ `asyncio.gather + Semaphore(8)`；策略按 (symbol,timeframe) 合并一次 `to_thread`，线程派发从 1600 次降到 200 次。
5. **`fetchSettings` 失败语义**：改为抛错或返回成功标志，供调用方决定提示（authStore 已不再依赖它）。
6. **ControlPanel 改草稿模式**：`draft = cloneDeep(settings)` + diff 提交 + `hydrated` 闸门 + 卸载 flush；排序改 computed；合并 CoinPoolsManager 两处重复 watcher。
7. **再平衡计划由后端重算**：滑块调整后调 `POST /api/rebalance/plan`，前端本地重算仅作预览，避免用旧持仓下单。
8. **Vuetify 按需引入**（vite-plugin-vuetify autoImport）+ `manualChunks`：CSS 805KB、字体 3.6MB 是当前最大体积来源。
9. **业务 `ValueError` 映射为 400**：再平衡的“池为空/无币种通过筛选”等应为用户可读错误，而非 500。
10. **前端写入口收敛**：新增 `signalStore`/`coinPoolStore`，`/api/settings` 只经 store 写入；自动开仓开关只保留一个端点。

### P2 — 可维护性
1. **拆分超大文件**（建议方案）：
   - `SignalsView` → `models/signals.ts`（纯函数）+ `composables/useSignalsData.ts` + `useSignalConfig.ts` + `components/signals/{StatusCard,AutoTradeConfigCard,SignalTable}.vue`；
   - `ControlPanel` → `common/CoinMultiSelect.vue` + `trading/{LongSettingsCard,ShortSettingsCard,ExecutionParamsCard,RebalanceSettings}.vue` + `composables/useSettingsDraft.ts`；
   - `ManualTradeView` → `manual/{Toolbar,Row,ConfirmDialog}.vue` + `composables/useManualTradeRows|Preset|ResolvedSymbols.ts`。
2. **抽公共工具**：`utils/format.ts`（金额/百分比/方向标签，统一 6 处不一致的 `toFixed`/`toLocaleString`）；`services/endpoints.ts` + 强类型 API 函数（当前 23 处路径字符串散落）。
3. **日志统一**：核心链路 `print` → loguru/logging，WS 日志按 level 过滤（DEBUG 不广播）。
4. **死代码清理**：`signals/scanner.py` 未使用的 `check_high_funding_rate` 导入、`rest_guardian` 未用的 `Awaitable`、`signal_store` 未用的 datetime、`levels/order_blocks` 未用的 pandas、`_generic_task_loop` 永远返回 False 的分支。
5. **命名**：自定义 `InterruptedError` 覆盖内建异常语义，建议改 `TaskInterruptedError`。
6. **前端质量门禁**：eslint 升级 `recommendedTypeChecked`（可捕获未 await 的 Promise）；拆 `lint` / `lint:fix`；引入 vitest 覆盖 `format`、signals normalizer、preset sanitize。
7. **依赖清理**：移除未使用的 `npm-run-all2`，执行一次 `npm install` 对齐 lock（仍有 `lodash-es`/`vue-multiselect` 幽灵条目）。
8. **a11y/i18n**：`<html lang="zh-CN">`、图标按钮 `aria-label`（停止按钮尤其重要）、文案收敛到一个常量表。
9. **`import` 期副作用**：`config.py` 导入即建库/读币种池，建议改为 `init_app_storage()` 由 lifespan 调用（需同步调整测试 fixture）。

### 不建议改动
- **`signals/analysis/*` 策略判定逻辑**（外部项目原样引入，重写等于重新验证策略有效性）；
- **SL/TP 百分比按杠杆折算公式**（产品既定语义，已有测试锁定）；
- **默认权重分配（BTC 40%/ETH 30%）与再平衡评分权重**（产品/策略参数，应通过配置暴露而非改常量）；
- **`static_audit` 的三条 AST 断言**（唯一防止“偷偷加市价单”的护栏，建议扩展而非删除）。

---

## 4. 验证结果

| 项 | 结果 |
|---|---|
| `python -m compileall -q backend` | 通过 |
| `python -m pytest backend/tests -q` | **147 passed**（原 133 + 新增 14） |
| `cd backend && python -c "from app.main import app"` | IMPORT_OK |
| `npx eslint .` | 0 error / 0 warning |
| `npx vue-tsc --build --force` | 0 错误 |
| `npm run build` | 成功；主包 693KB → 611KB，5 个页面拆为独立 chunk |
| 静态审计 | 无市价开仓（仅条件单） |

## 5. 环境备注
- 本机 Python：`C:\Python312`；`pandas_ta` 的 Windows posix bug 已在 site-packages 本地修复。
- 前端构建需 `TMP/TEMP` 指向 `.tmp`，且先手动清空 `dist`（safe-delete shim 与 vite emptyOutDir 冲突）。
- `data/app.db` 已含迁移后的配置（含密钥），已 gitignore；**仍建议轮换币安 API Key**。
