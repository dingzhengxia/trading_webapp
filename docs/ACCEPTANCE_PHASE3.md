# Phase 3 增量重构 — T14 集成验收报告（独立 QA 复核）

- 验收人：QA Engineer（Edward），独立视角，不依赖工程师自报结论
- 日期：2026-11-13
- 范围：T01–T13 全量未提交工作区（85 个变更文件）+ 契约文档 ARCH_REFACTOR_PHASE3 / PRD_REFACTOR_PHASE3
- 结论：**PASS**（Round 1 全部通过，无源码 Bug，无需路由返工）

---

## 1. 全量命令验证结果

| # | 命令 | 结果 | 备注 |
|---|------|------|------|
| 1 | `python -m compileall -q backend` | ✅ PASS | 无编译错误 |
| 2 | `python -m pytest tests -q`（backend/） | ✅ **357 passed**（46.6s，120 warnings 均为 pandas_ta 三方弃用告警） | 与预期 357 完全一致；async 测试以 asyncio.run 驱动，无 pytest-asyncio 依赖 |
| 3 | `python -c "from app.main import app"` | ✅ PASS | import 后全仓无 `*.db`/`*.sqlite*` 产生 —— 建库确已收口进 lifespan（main.py `init_app_storage`），另有子进程级测试 `test_import_app_does_not_create_db` 锁定 |
| 4 | `npx eslint .`（frontend/） | ✅ PASS | 0 error / 0 warning |
| 5 | `npx vue-tsc --build --force` | ✅ PASS | 类型检查 0 错误 |
| 6 | `TMP/TEMP=.tmp npm run build` | ✅ PASS（14.3s） | dist 已确认可清空后重建；产物完整 |

## 2. 体积对比（vite 输出口径，与基线同源）

| 指标 | 基线 | 当前 | 变化 |
|------|------|------|------|
| CSS 总量 | 797.7 kB | **≈433.1 kB**（index 382.89 + 14 个分片） | **−45.7%** |
| JS 总量 | 773.7 kB | **≈646.1 kB**（19 个 chunk） | **−16.5%** |
| 主包 index JS | 620.3 kB | **205.0 kB**（65.74 kB gzip） | **−66.9%** |
| mdi 样式 | ≈408 kB（全量 css） | **≈5 kB**（75 图标子集，脚本自动生成） | −98.8% |

- Vuetify 已按需引入，vendor 独立 chunk（102.7 kB）、vuetify chunk（59.2 kB）、路由级分片齐全。
- T12 验收口径达成：build/vue-tsc 0 错误、CSS 显著下降、主包不高于现状。

## 3. 资金安全 P0 抽查（逐条读码核实，非仅测试名）

### T01 下单幂等（R-P0-1）— ✅ 落实
- `logic/order_id.py`：coid = `{prefix}{base36(ms)}{coin}{seq}`，字符集全部落在 Binance `^[\.A-Za-z0-9_-]{1,36}$`，`[:36]` 截断兜底；模块级 `itertools.count` 单调 seq 保证单进程同毫秒唯一；非法 prefix 直接 `ValueError`（防不可追溯单号进交易所）。
- `logic/exchange_logic_async.py:676-706`：`create_order` 抛 `RequestTimeout/NetworkError/ExchangeNotAvailable` 且 `order_id is None` 时，**先** `recover_order_by_client_id_async` 反查（先扫挂单簿、再 `origClientOrderId` 查询，最多 2 请求）；命中 → 接管原单继续等待成交（不重下）；未命中 → 新 coid 重下。反查实现对 `OrderNotFound`/fake 兼容性（TypeError 降级）均处理。
- 测试 `test_order_idempotency.py` 为真实行为断言：断言 `create_order_calls == 1`（不重下）、`fetch_open_orders_calls` 非空（走了反查），含挂单簿未命中但历史单命中的接管分支。

### T02 裸仓回收（R-P0-2）— ✅ 落实
- `logic/exchange_logic_async.py:843-891` `_handle_unprotected_position_async`：
  1. `protection.service.protection_active_for` 已接管 → **跳过自动平仓**（error 级强提示，单一处置权归 protection）；
  2. 未接管 + `auto_close` → 复用 `close_position_async`（reduceOnly 限价 post-only + 全平复核）；
  3. `keep_alert` → 不触碰仓位，任务标记失败（D1：`auto_closed` 区分台账）。
  查询接管状态失败按"未接管"兜底（fail-safe 方向正确）。
- `protection/exits.py` 市价减仓统一 `reduceOnly: True` + 平仓方向表达式（`"sell" if side == "long" else "buy"`），`_full_exit_with_revalidation` 全平前重取仓位并校验 `position_version`。

### T03 WS 鉴权（R-P0-5）— ✅ 落实
- `main.py` 握手校验 `?token=`，失败 → accept 后立即 `close(4401)`，不进广播循环；日志不含 token 内容。
- `core/security.py`：空密钥一律拒绝、`secrets.compare_digest` 常数时间比较；`WS_AUTH_DISABLED` 仅认环境变量 `=1`（配置文件不可关，防误配永久关鉴权），开启时打 error 告警。
- 前端 `services/websocket.ts:28-31` 握手 URL 带 `?token=`（未认证不带，由 4401 拒绝）。测试覆盖无 token/错 token/正确 token/降级开关四路径。

### T04 GuardedExchange（R-P1-1）— ✅ 落实
- `core/guarded_exchange.py`：静态映射 `REST_PRIORITY` 优先级正确 —— 下单/撤单/查单/持仓/余额等交易决策类 **HIGH**（绕熔断仍受并发/最小间隔），行情/元数据 **NORMAL**，`fetch_ohlcv` **LOW**；未登记属性原样透传；`__setattr__` 委托 underlying（`_twa_hedge_mode` 等缓存落真实实例）。
- **唯一包装点**核实：`exchange_manager.get_exchange_with_timeout` 内 `wrap_exchange(exchange, shared_guardian())`；全仓 `RestGuardian(` 实例化仅 `rest_guardian.py`（shared 单例 + 工厂），signals/market_data 已放弃自建 guardian；`.underlying` 仅 `raw_rest_method` 辅助入口访问，protection 经其解包避免双重限流。
- `test_guarded_exchange.py` 真实可执行：计数 guardian 断言优先级传递、MiniExchange 验证透传/setattr/委托；静态审计三规则（白名单外禁市价单、白名单内必须 reduceOnly+平仓方向、负向用例）为 AST 级可执行断言（`test_static_audit.py` 含 5 组负向/对照用例）。

### 行为语义抽查 — ✅ 未变
- 限价 post-only 开仓：`exchange_logic_async.py` 开仓路径仍 `'postOnly': True` 且仅限价单，每轮带确定性 coid；非 chase 的平仓为 reduceOnly 路径。
- USDC 优先：`logic/utils.py` `STABLECOIN_PREFERENCE（USDC 优先，其次 USDT）` 收口于 `resolve_*` 系列函数，scanner/market_data 复用。
- 做多绿/做空红：`utils/tone.ts` 为唯一判色入口（directionTone/pnlTone/positionSideTone），红绿通道分离 + 箭头图标 + 文案三重编码；grep 全 src 无硬编码 `#4CAF50/#F44336` 等散落色值，组件统一 import tone。

## 4. 审计类 grep 复核

| 检查项 | 结果 |
|--------|------|
| 后端裸 print | ✅ 仅 `main.py` lifespan 启动横幅（白名单入测试 `test_engineering_hygiene.py`，AST 级断言横幅外零 print） |
| 前端裸 `/api/` | ✅ 仅 `services/endpoints.ts`（ENDPOINTS 常量单一来源），组件/views 零散落 |
| toFixed 越界 | ✅ `toFixed` 仅存于 `utils/format.ts`（`formatFixed` 对非法值返回 `(0).toFixed(digits)` 即 0，语义正确）；组件层被 eslint no-restricted-syntax 禁止直接调用 |
| ccxt 实例构造点 | ✅ 唯一：`exchange_manager.initialize_exchange_async` 构造后立即 `wrap_exchange`；类型注解 `ccxt.binanceusdm` 仅为注解非构造 |
| InterruptedError 残留 | ✅ 零残留（AST 级测试 `test_interrupted_error_renamed_everywhere` 锁定，业务异常统一 `TaskInterruptedError`） |
| T05 配置热更新 | ✅ `api/settings.py:122-128` 保存后 `shared_guardian().configure(api_conf)` 即时生效；scanner 每轮重读 interval |
| T06 策略派发合并 / T07 平仓让价 / T09 fetch_klines 收口 | ✅ 对应测试存在且通过（test_scanner / test_close_chase / test_rebalance_filters） |

## 5. 重复代码复查（≥10 行窗口，跨文件精确匹配）

- `backend/app/protection/`（14 文件，3694 行，最大单文件 engine.py 767 行 < 800 上限）：**0** 个跨文件重复 10 行块。
- `frontend/src/composables/`（5 文件，1236 行，均 < 400 行上限）：**0** 个跨文件重复块。
- T08 拆分边界清晰：config/state/market_data/stops/take_profit/exits 职责互斥，engine.py 为 facade 编排层。

## 6. 遗留问题与待办池

**无源码 Bug（Round 1 全绿，无需路由返工）。** 以下为非阻塞改进项，建议入待办池：

| # | 级别 | 事项 | 说明 / 建议 |
|---|------|------|-------------|
| 1 | P3 优化 | MDI 仅做了 CSS 子集，字体文件仍全量入包 | `dist/assets/materialdesignicons-webfont.woff2` 403 kB + `.ttf` 1.3 MB 仍随构建发布，浏览器仍会下载整个字体。`generate-mdi-subset.mjs` 自述为"D3 降级路径"符合契约，但后续可用 `pyftsubset`/`fonttools` 按 75 个 codepoint 做字形级子集（预期 <20 kB），并删掉 ttf 回退（现代浏览器 woff2 覆盖率近 100%）。 |
| 2 | P4 备注 | `make_client_order_id` 的 `[:36]` 截断为理论边界 | prefix(≤2)+base36 ms(≈8)+coin(实际≤10)+seq，现实币种下不会触到 36 上限；若未来出现超长基础币名，截断可能吃掉 seq 后缀，届时应改为"压缩 coin 名"而不是尾截。仅备忘，不需现在处理。 |
| 3 | P4 备注 | `test_ws_auth.py` 依赖本机已配置 `app_access_key` | fixture 在 key 为空时 assert 失败——属有意设计（无 key 无法测正路径），但换环境跑测试需先配 key，README/CI 文档宜注明。 |
| 4 | P4 备注 | pytest 120 条 pandas_ta 弃用告警 | 三方库（Pandas4Warning），与本次重构无关；待 pandas_ta 升级后消解。 |
| 5 | 待办池 | D5（vitest / eslint type-checked） | 契约中明确留待后续迭代，未在本期范围。 |

## 7. 结论

- 全量命令 6/6 通过；357 测试与预期完全一致。
- 6 条资金安全 P0（幂等/裸仓回收/WS 鉴权/GuardedExchange/post-only/USDC/判色）逐条读码核实真实落地。
- 审计类 grep 6 项全部干净；重复代码零命中。
- 体积目标全面达成（CSS −45.7%、主包 −66.9%）。
- **验收结论：PASS**。未执行任何 git commit/push，工作区保持原状。
