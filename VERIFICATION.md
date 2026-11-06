# 最终验收报告（VERIFICATION.md）

> 验收对象：E:\python\trading_webapp（FastAPI + Vue3/Vuetify + ccxt）
> 契约来源：REFACTORING_REPORT.md 第 2/4/5/6 节
> 验收人：verifier（独立于 backend-dev / frontend-dev）
> 验收时间：2026-11-06
> 验收范围：backend/app、backend/tests、frontend/src、根目录配置与报告；monitor/ 为无关外部仓库，未读取/修改/执行任何 git 操作，按 Lead 要求忽略。

---

## 1. 结论摘要

**功能与代码质量验收通过**：后端编译、导入、离线测试全绿；前端 eslint 0 错误、vue-tsc --build --force 0 错误、npm run build 成功并产出含 /manual 页面的新 dist；缺陷清单 P0/P1 已按契约逐条落实（P0-7 的仓库卫生为契约要求的 .gitignore + 报告提示，已满足，仍需人工执行密钥轮换与 git rm --cached）；P2 卫生项已清理。

**剩余事项均为外部动作/环境限制，不是代码缺陷**（详见第 9 节）：
1. user_settings.json 仍含真实 Binance API Key/Secret 且仍被 git 跟踪（已加入 .gitignore）→ **必须轮换密钥**并由 Lead 执行 git rm --cached user_settings.json（本报告不输出任何密钥内容）。
2. user_settings.json 中 app_access_key 仍是默认哨兵值 CHANGE_THIS_IN_USER_SETTINGS.JSON（P0-8 已实现启动告警 + 每次请求读取，但配置本身需用户修改）。
3. verifier 子代理会话文件沙箱固定为 workspace-write，无法执行 vite build（子进程 pipe spawn EPERM）；构建由 Lead 在 danger-full-access 会话用工作区 TMP 跑通，本报告以该次结果 + 产物核验为准（第 3.2 节）。
4. frontend/package-lock.json 仍保留已移除的 vue-multiselect / lodash-es 条目（无网络、按要求不改 lock，未执行 install；不影响现有 node_modules 构建）。

---

## 2. 环境

| 项 | 值 |
|---|---|
| OS | Windows（PowerShell 7） |
| Python | 3.12.3 |
| pytest | 8.3.2（无 pytest-asyncio，异步测试用 asyncio.run） |
| FastAPI / Pydantic | 0.111.0 / 2.7.1 |
| Node / npm | v22.19.0 / 10.9.3 |
| Vite / vue-tsc / ESLint | 7.1.5 / 3.x（--build --force 通过）/ 9.x |
| 网络 | 全程离线：测试使用 fake exchange，无 Binance/网络访问 |
| 工作区 | E:\python\trading_webapp |

---

## 3. 验证命令与结果

### 3.1 后端

| 命令 | 结果 |
|---|---|
| python -m compileall -q backend | **exit 0**（无输出） |
| python -m pytest backend/tests -q | **68 passed in 2.69s**，0 failed / 0 skipped |
| python -m pytest backend/tests --collect-only -q | 68 tests collected |
| cd backend; python -c "from app.main import app; print('IMPORT_OK')" | **IMPORT_OK** |

### 3.2 前端

| 命令 | 结果 |
|---|---|
| cd frontend; npx eslint . | **exit 0**，0 error / 0 warning（无输出） |
| cd frontend; npx vue-tsc --build --force | **exit 0**，0 类型错误 |
| cd frontend; npm run build | **exit 0**（由 Lead 在 danger-full-access 会话执行，脚本为 npx vue-tsc --build --force && npx vite build） |

**构建证据（verifier 独立核验 dist 产物）**
- frontend/dist/index.html 与全部 frontend/dist/assets/* 修改时间均为 **2026-11-06 10:10:22**（非旧产物），index.html 引用新文件名 /assets/index-DAJaS-iE.js、/assets/index-CL8CFigB.css。
- dist/assets/index-DAJaS-iE.js 中可检索到：/manual、手动交易、mdi-hand-coin-outline、resolve-symbols、全部反手 → 新页面已进入构建产物。
- Lead 使用的稳定构建命令（环境限制绕过方式，记录备查）：
    cd frontend
    $env:TMP='E:\python\trading_webapp\.tmp'; $env:TEMP=$env:TMP; npm run build
  说明：该工作区 TMP 用于规避本机 esbuild 在系统临时目录的权限问题（Access denied）。verifier 的固定 workspace-write 沙箱仍会因子进程 pipe 报 spawn EPERM（esbuild service），这是本会话权限边界，不是代码/配置问题；因此以 Lead 的成功结果 + dist 产物作为构建证据。

### 3.3 TestClient 冒烟（不连交易所）

仅调用不依赖成功 exchange 的分支；resolve-symbols 只验证鉴权短路（router 依赖先于 exchange 依赖，403 时不会创建 exchange）。

| 请求 | 期望 | 实测 |
|---|---|---|
| GET /api/status 无 X-API-KEY | 403 | 403 |
| GET /api/status 带有效 key | 200 | 200 |
| GET /api/settings 带有效 key | 200 | 200 |
| POST /api/trading/manual 无 key | 403 | 403 |
| POST /api/trading/manual 重复币种（BTC + btc） | 400 | 400 |
| POST /api/trading/manual 空 items | 4xx | 400 |
| POST /api/trading/manual 非法 action（hold） | 4xx | 422（Pydantic 枚举校验） |
| GET /api/trading/resolve-symbols 无 key | 403 | 403 |

> 结果：SMOKE_OK (no exchange constructed)。有效 payload 的完整任务提交未测试（会创建真实 exchange），符合 task-4“不连交易所”约束；Pydantic/Service 校验分支已全覆盖。

### 3.4 静态审计（AST + grep）

| 检查项 | 结果 |
|---|---|
| backend/app/** 中 create_order(type='market') | **0 处**（AST 遍历 25 个 py 文件；条件单 STOP_MARKET/TAKE_PROFIT_MARKET/TRAILING_STOP_MARKET 除外） |
| 函数体仅 pass 的空壳 | **0 处**（AST 扫描） |
| config/i18n.py 残留 / i18n import 残留 | **0**（已重命名为 config/constants.py） |
| @app.on_event 弃用 API | **0**（已改 lifespan） |
| 后端未使用 import | **0**（AST unused-import 审计） |
| rebalance_foam_days / foam 业务残留 | **0**（仅验收测试中显式断言 foam 被拒绝） |
| DEBUG/TODO/FIXME/XXX 标记 | **0** |
| 前端 lodash-es / vue-multiselect 引用 | **0**（package.json 依赖与 src 引用均已移除） |
| 前端显式 any | **0**（frontend/src/** 全量 grep） |
| /manual 路由 | 存在：frontend/src/router.ts:32-35（name='manual'、title='手动交易'、icon='mdi-hand-coin-outline'） |
| WeightConfigDialog 重复挂载 | 仅 frontend/src/App.vue:61 一处 |
| useDisplay().application 误用 | 已改 useLayout().mainRect.value.left（SettingsView.vue:119-127、TradingView.vue:78-90） |
| Snackbar.vue 重命名 | 已删除旧文件，新增 AppSnackbar.vue，App.vue:64,84 引用 |
| 空目录 frontend/src/router/ | 已不存在 |

### 3.5 Git 越界检查（只读命令）

- git status --porcelain（已忽略 monitor/）：修改/新增均落在契约允许范围：
  - 修改：.gitignore、backend/app/**、frontend/eslint.config.ts、frontend/package.json、frontend/src/**
  - 删除：backend/app/config/i18n.py、frontend/src/components/Snackbar.vue、frontend/package.json 中两个依赖
  - 新增：backend/app/config/constants.py、backend/app/logic/manual_trade_logic.py、backend/tests/**、frontend/src/components/AppSnackbar.vue、frontend/src/utils/**、frontend/src/views/ManualTradeView.vue、REFACTORING_REPORT.md、本报告
- **未修改**：user_settings.json、coin_lists.json、frontend/package-lock.json、backend/requirements.txt（git status/文件 mtime 均未变）。
- 未跟踪项说明：monitor/（Lead 已说明为无关外部仓库，忽略）、.tmp/（构建 TMP 工作目录，建议交付前删除）、MERGE_PLAN.md（Lead 协调文档）。
- verifier 未执行任何写操作类 git 命令（无 commit/push/rm），仅使用 status/diff/ls-files/rev-parse 只读检查。

---

## 4. 离线验收测试套件（backend/tests）

**运行：python -m pytest backend/tests -q → 68 passed，完全离线。**
实现方式：conftest.py 注入 backend 到 sys.path；FakeExchange 记录 create_order/cancel_order/cancel_all_orders/fetch_order/fetch_positions/fetch_open_orders/set_leverage 等调用，支持订单状态序列、部分成交、异常注入；异步代码统一 asyncio.run()；fast_sleep 夹具压缩重试/清理循环；无 pytest-asyncio、无网络。

| 测试文件 | 覆盖点 |
|---|---|
| test_resolve_symbols.py | USDC 优先（USDC+USDT/仅 USDT/无匹配/大小写/空 markets） |
| test_manual_trade_logic.py | validate 空/重复/非法 action/value<=0；build long/short/reverse、default_value、配置总值按同方向均分、反手 close_full_symbols+notional 求和、无持仓/多空并存 skip、纯函数无 IO |
| test_limit_orders.py | limit+postOnly、买用 bids[0]/卖用 asks[0]、部分成交重试只下剩余量、低于最小量停止、reduceOnly 保留、无 market |
| test_sl_tp.py | STOP_MARKET+TAKE_PROFIT_MARKET（reduceOnly/workingType=MARK_PRICE/方向/trigger 杠杆公式）、禁用不挂单、trailing 仅 TRAILING_STOP_MARKET、孤儿条件单清理非空壳且生效 |
| test_plan_calculator.py | BTC/ETH 40/30+其余均分、纯卫星均分、权重归一、全 0 回退、空列表 ({}, {})、大小写/去重、无 print |
| test_fetch_positions.py | P0-5 交易所异常向上抛、优先 position.info、无额外 fetch_tickers、side 小写、PnL/保证金百分比 |
| test_process_order.py | P0-2 同币种 USDC/USDT 双持仓时开仓走 USDC，SL/TP 精确挂到刚开的 USDC full_symbol |
| test_close_position.py | P0-4 全平后复核 contracts==0 并清理条件单；有残留时返回 False 禁止反手裸开 |
| test_rebalance_filters.py | P1-2 布林带宽度放大/成交量放大过滤生效、空数据安全、非 multi_factor_weakest 明确 ValueError |
| test_api_security.py | TestClient 离线鉴权 403/200、/manual 400/422 校验分支 |
| test_static_audit.py | 无 market 开仓、无 pass 空壳、i18n 已删除、main 用 lifespan |

---

## 5. 缺陷清单逐条对照（REFACTORING_REPORT.md 第 2 节）

### P0（全部修复）

| 编号 | 状态 | 证据 |
|---|---|---|
| P0-1 止盈从未下单 | **已修复** | sl_tp_logic_async.py:181-207：固定模式同时挂 STOP_MARKET + TAKE_PROFIT_MARKET，reduceOnly=True、workingType=MARK_PRICE（_place_conditional_order_async:101-127）；trigger=entry*(1∓pct/100/leverage)。测试 test_sl_tp.py（long/short 触发价断言）通过 |
| P0-2 止盈止损挂错仓位 | **已修复** | exchange_logic_async.py:453-475：优先按 full_symbol + side 精确匹配，再退 full_symbol、最后 base；test_process_order.py 在 USDC+USDT 双持仓下断言条件单只挂 USDC 且数量=新仓位 |
| P0-3 部分成交重试重复下单 | **已修复** | exchange_logic_async.py:270-405：累计 total_filled（288/329-340/358），每次只下 target-total_filled（307），剩余<最小量停止（313-320）；test_limit_orders.py 断言 0.4 成交后重试仅 0.6、最小量不足不再下单、全部 limit+postOnly |
| P0-4 全平未复核→反手裸开 | **已修复** | exchange_logic_async.py:211-249：ratio==1 成交后重新拉持仓复核 contracts==0，最多 2 轮补平，仍有残留返回 False；test_close_position.py 覆盖成功/残留两分支；trading_service.py:229-247 反手只有在每次全平成功后才开反向仓 |
| P0-5 持仓查询吞异常 | **已修复** | exchange_logic_async.py:82 直接 await fetch_positions，无 try/except 吞错；test_fetch_positions.py 注入交易所异常断言向上抛 |
| P0-6 cleanup_orphan 空函数 | **已修复（实现而非删除）** | sl_tp_logic_async.py:211-240：fetch_open_orders → 撤销 symbol 不在 active 集合的条件单；trading_service.py:191-193 在同步 SL/TP 后调用；test_sl_tp.py 断言孤儿单被撤、活跃单不撤；AST 无 pass 空壳 |
| P0-7 真实 Key/Secret 被 Git 跟踪 | **已按契约修复（需人工收尾）** | .gitignore 已新增 user_settings.json（第 8 行）；user_settings.json 含真实 API Key/Secret（未在报告中输出），且仍被 git 跟踪（git ls-files 可见）。**需 Lead 执行 git rm --cached user_settings.json 并轮换密钥、按需清理历史**（详见第 9 节） |
| P0-8 默认访问密钥=公开访问 | **已修复（配置仍为默认值，运行时风险提示）** | security.py:16-22,43-55 每次请求读取配置 + secrets.compare_digest；security.py:25-33 + main.py:24-27 启动告警。实测 user_settings 的 app_access_key 仍为默认哨兵值 → 接口当前用默认 key 可访问，**强烈建议立即改为强随机值** |

### P1（全部修复）

| 编号 | 状态 | 证据 |
|---|---|---|
| P1-1 每子任务新建 exchange | **已修复** | trading_service.py:151-156 自动开仓、164-176 平仓、184-193 同步 SL/TP、220-249 手动、260-289 再平衡：均一个 async with get_exchange_for_task() 包住整个任务，worker 共享 |
| P1-2 再平衡参数未实现 / foam 分支 | **已修复** | rebalance_logic.py:15-20 仅支持 multi_factor_weakest（其余 ValueError，api/rebalance.py:131-135 转 400）；116-138 布林带宽度与成交量放大指标；159-189 实际过滤；schemas/config/frontend 已移除 rebalance_foam_days/foam；test_rebalance_filters.py 通过 |
| P1-3 plan_calculator 调试 print/边界 | **已修复** | plan_calculator.py:114-137 纯函数：去重/大写/过滤非法权重、权重总和 0 回退默认分配、BTC/ETH 40/30 保留、无 print；test_plan_calculator.py（含 capsys 无输出断言）通过 |
| P1-4 TradePlanRequest 冗余字段 | **已修复** | schemas.py:41-66 仅保留交易执行字段；再平衡独立 RebalanceCriteria（141-160） |
| P1-5 平仓/再平衡/SLTP 各自建 exchange | **已修复** | 同 P1-1，见 trading_service 上述行号 |
| P1-6 部分平仓后 SL/TP 数量不匹配 | **已修复** | exchange_logic_async.py:250-259 部分平仓成功后按剩余仓位重新 set_tp_sl_for_position_async |
| P1-7 重复撤单封装 | **已修复** | 仅保留 sl_tp_logic_async.py:27-42 单一 cancel_all_orders_async（普通单 + {'stop': True} 各一次，无 3 次循环）；旧 _cancel_sl_tp_orders_async/_force_cancel_all_orders/_ensure_no_open_orders_async 已不存在 |
| P1-8 update-coin-pools 绕过锁 | **已修复** | config.py:197-226 线程安全 save_coin_pools()（锁内写文件 + 刷新内存）；api/settings.py:40-47 改为调用它 |
| P1-9 前端类型检查脚本无效 | **已修复** | frontend/package.json build = npx vue-tsc --build --force && npx vite build；实测 vue-tsc --build --force 0 错误 |
| P1-10 前端类型错误 | **已修复** | types.ts:14 LogEntry；本地 utils/debounce.ts（带 cancel/flush）；SettingsView.vue:119-127、TradingView.vue:78-90 用 useLayout().mainRect；ControlPanel.vue:5 v-model 事件；LogDrawer.vue:28-31 unknown→LogEntry；PositionsTable.vue slot 修饰符由 eslint.config.ts:26-27 allowModifiers 支持；src 全量 0 个显式 any；AppSnackbar.vue 重命名完成 |
| P1-11 WeightConfigDialog 重复挂载 | **已修复** | 仅 App.vue:61 挂载一次，ControlPanel 无引用 |
| P1-12 CORS 不合规 | **已修复** | main.py:96-105 allow_credentials=False（保留 headers 鉴权） |
| P1-13 弃用 API/启动健壮性 | **已修复** | main.py:20-35 lifespan；74-84 Docker 静态目录缺失仅明确日志、有条件挂载，不崩溃 |

### P2（卫生项）

| 项 | 状态 | 证据 |
|---|---|---|
| config/i18n.py 重命名 + 删误导注释 | **已修复** | 旧文件已删除，新增 config/constants.py（仅 4 类业务常量，19 行）；全仓无 i18n import；引用改为 from ..config import constants |
| 未使用导入（sl_tp/api/rebalance/trading_service/api/positions 等） | **已修复** | AST 未使用 import 审计 0 命中；eslint 前端 0 error |
| 未使用依赖 vue-multiselect / lodash-es | **已修复（lock 未动）** | package.json 中两依赖已移除，src 无引用；package-lock.json 按要求未改（其中仍保留条目，见风险） |
| 未使用 action settingsStore.saveSelectedCoinLists | **已修复** | 已删除（grep 0 命中） |
| 空目录 frontend/src/router/ | **已修复** | 目录不存在 |
| 无自动化测试/CI、.gitignore 忽略 user_settings | **已修复（测试）** | 新增 68 个离线测试；.gitignore 已加 user_settings.json（CI 未新增，无 CI 环境要求） |

---

## 6. 新功能验收（REFACTORING_REPORT.md 第 4 节）

### 6.1 后端 API / 逻辑

| 项 | 证据 |
|---|---|
| POST /api/trading/manual | api/trading.py:35-38；鉴权 403、重复/空/非法 value 4xx 已冒烟；同步校验在 trading_service.py:196-212，失败 HTTPException(400) 且不创建 exchange |
| GET /api/trading/resolve-symbols?symbols=...（quote/available） | api/trading.py:41-68，依赖 resolve_symbol_details（utils.py:18-48，USDC 优先→USDT，支持去重/大写/完整交易对降级） |
| ManualTradeAction/Item/Request/ResolvedSymbol/ResolveSymbolsResponse | schemas.py:113-138；CloseBySideRequest.side 用 Literal（90-92） |
| manual_trade_logic 纯函数 | manual_trade_logic.py:89-133 validate（空/重复/非法 action/value<=0→ValueError）；147-210 build（long→buy/short→sell；reverse 先校验无持仓/多空并存→skip，close_full_symbols=全部持仓 full_symbol、value 缺省=notional 之和；同方向缺省按配置总值均分）；dataclass ManualTradeTask（17-24） |
| 手动任务执行流程 | trading_service.py:214-249：1 个 exchange → 持仓快照 → build → _run_task_loop；skip 记 warning；反手逐个 close_position_async(...,1.0) 必须成功并 broadcast position_closed，再 process_order_with_sl_tp_async 反向开仓；错误立即取消反手（return False） |
| 开仓日志交易对/报价币种 | exchange_logic_async.py:431-434：✅ BTC 交易对: BTC/USDC:USDC (USDC 优先)，成功日志含 full_symbol/leverage（482-483） |
| 限价 post-only、无市价开仓 | exchange_logic_async.py:326-327；静态审计 0 处 market；测试断言 postOnly |
| 单次请求币种上限 100 | manual_trade_logic.py:12,101-102 |
| TestClient：鉴权 + 4xx 边界 | 第 3.3 节；test_api_security.py |

### 6.2 前端

| 项 | 证据 |
|---|---|
| 路由 /manual | router.ts:32-35（name 'manual'、title '手动交易'、icon 'mdi-hand-coin-outline'）；App.vue 自动由 router.getRoutes() 生成导航（App.vue:87） |
| 币种多选/搜索/chips | ManualTradeView.vue:23-53（multiple/chips/clearable + prepend 搜索框），可用币种优先总池、空则合并 long/short（299-311） |
| 批量 全部做多/做空/反手 + 默认价值 | 73-114 三个批量按钮 + 默认价值输入（56-70） |
| 行表格：币种/持仓/动作/价值/报价 | 116-199（持仓来自 positionStore，报价来自 resolve-symbols，USDC/USDT 标签颜色） |
| 风险提示 | 13-19（限价 post-only；反手=先全平再反向；无持仓跳过） |
| 执行调用 | 397-410 uiStore.launchTask('/api/trading/manual', {items, default_value?}, '手动交易', items.length)；任务结束 watch isRunning 自动刷新持仓（437-445） |
| 下方复用 PnlSummary + 两个 PositionsTable | 225-253 |
| 禁用条件 | 325-327（无选择/非法价值/运行中禁用） |
| 类型 | types.ts:47-65 ManualTradeAction/ManualTradeItem/ResolvedSymbol/ResolveSymbolsResponse |
| 构建产物 | dist 中已含 /manual、手动交易、mdi-hand-coin-outline、resolve-symbols、全部反手（第 3.2 节） |

---

## 7. 验收标准对照（REFACTORING_REPORT.md 第 5 节）

**后端**
1. compileall / import：**通过**（第 3.1 节）。
2. python -m pytest backend/tests -q：**68 passed，离线**。
3. 必测覆盖：USDC 优先 ✅、manual 校验/任务构建 ✅、限价+postOnly+无 market ✅、部分成交剩余量 ✅、SL/TP reduceOnly 条件单 ✅、plan_calculator 权重/边界 ✅。
4. 生产代码无 market 开仓/平仓（条件单除外）：**0 命中**（AST + grep 双重）。
5. POST /api/trading/manual 无鉴权 403、合法 payload 400（重复/空/非法）分支：**通过**；返回任务提交信息的成功分支需真实 exchange，按 task-4 约束未触发（代码路径 trading_service.py:211-212）。

**前端**
1. vue-tsc --build --force：**0 错误**。
2. eslint .：**0 error / 0 warning**。
3. npm run build：**成功**（Lead 执行，dist 新产物已核验；脚本已为先 type-check 后 vite build）。
4. /manual 路由存在、导航可见、页面包含动作/价值/报价/执行：**通过**（6.2 节）。
5. 现有页面不回归：lint/typecheck/build 全绿 + 代码审查未发现行为语义变化（自动开仓/平仓/同步/再平衡路径不变，仅修复项）。

**端到端/冒烟**
1. 后端可启动（TestClient 导入/请求）：/api/status、/api/settings 带 key 200，无 key 403：**通过**（第 3.3 节）。
2. 前端 dist 构建产物包含新页面 chunk：**通过**（第 3.2 节）。
3. WebSocket 进度事件复用 progress_update：手动交易走 _run_task_loop（trading_service.py:249），内部 broadcast_progress_details（websocket_manager.py:56-67）→ **通过（代码路径）**。

---

## 8. 验收执行方式与独立性

- verifier 只写入 backend/tests/** 与根目录 VERIFICATION.md；未修改 backend/app/**、frontend/**、user_settings.json、coin_lists.json、任何配置，未执行 git 写操作。
- 测试完全离线：FakeExchange/monkeypatch，无 Binance/HTTP；TestClient 只走不创建 exchange 的分支。
- 首轮（后端并行开发中）曾出现收集错误/失败，属实现未就绪的中间态；后端交付后复跑全绿。测试侧另行修正过 3 处自身夹具/断言问题（未放松契约），并在最终验收新增 P0-4/P1-2 测试后复跑 68 passed。

---

## 9. 剩余风险与建议（按优先级）

1. **【高】密钥轮换与 Git 历史清理（P0-7 收尾）**：user_settings.json 含真实 Binance API Key/Secret 且仍被跟踪。建议 Lead：① 立即在 Binance 轮换 API Key/Secret；② git rm --cached user_settings.json 并从历史中清除（如 git filter-repo/BFG）；③ 确认远端仓库权限与访问记录。本报告/代码/日志均未输出任何密钥。
2. **【高】修改默认 app_access_key（P0-8 收尾）**：当前仍为 CHANGE_THIS_IN_USER_SETTINGS.JSON，等于公开访问；启动会告警但不拒绝。建议改为强随机值并重启后端。
3. **【中】构建环境限制**：本机子代理会话（workspace-write）无法运行 vite/esbuild（子进程 pipe spawn EPERM）；本次构建证据来自 Lead 的 danger-full-access 会话（工作区 TMP 绕过系统临时目录权限问题）。建议在 CI/交付环境固定使用工作区 TMP 或放开相应权限，避免“本地构建不可复现”。
4. **【中】package-lock 与 package.json 不一致**：vue-multiselect/lodash-es 仍在 frontend/package-lock.json（无网络未 install）。建议联网后执行 npm install（或 npm install --package-lock-only）刷新 lock，再验证 npm ci && npm run build。
5. **【低】临时/未跟踪文件**：.tmp/（构建 TMP 工作目录）、MERGE_PLAN.md、REFACTORING_REPORT.md 未跟踪；monitor/ 为无关外部仓库（按 Lead 指示忽略）。交付前建议删除 .tmp/，按需决定 MERGE_PLAN 去留。
6. **【低】前端类型/日志小项**：uiStore.launchTask(payload: object) 已去除 any，但可进一步收紧为 Record<string, unknown>；uiStore.ts:98 仍有 console.log('API call successful')（非阻断，eslint 通过）。
7. **【低】后端运维日志仍用 print**：config.py/exchange_manager.py/main.py 中为启动/错误提示（非 DEBUG 调试输出），建议后续统一到 logging，但不影响本次验收。
8. **【说明】WebSocket 手动任务进度**：复用现有 progress_update 机制（代码路径已核验），未做浏览器端人工点检（无浏览器自动化环境）。

---

## 10. 证据文件索引（关键行）

- 后端新功能：backend/app/api/trading.py:35-68、backend/app/core/trading_service.py:196-249、backend/app/logic/manual_trade_logic.py、backend/app/models/schemas.py:113-138
- 交易安全修复：backend/app/logic/exchange_logic_async.py:75-143, 161-267, 270-405, 427-484、backend/app/logic/sl_tp_logic_async.py:27-240、backend/app/logic/utils.py:18-48
- 配置/安全/启动：backend/app/config/config.py:197-226、backend/app/config/constants.py、backend/app/core/security.py:16-55、backend/app/main.py:20-105
- 再平衡/计划：backend/app/logic/rebalance_logic.py:15-228、backend/app/logic/plan_calculator.py:114-137、backend/app/api/rebalance.py:26-199
- 前端：frontend/src/router.ts:32-35、frontend/src/views/ManualTradeView.vue、frontend/src/models/types.ts:47-65、frontend/src/utils/debounce.ts、frontend/src/App.vue:61,64,84,87、frontend/eslint.config.ts:26-27、frontend/package.json
- 测试：backend/tests/conftest.py + 11 个 test_*.py（68 tests）
