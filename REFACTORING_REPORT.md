# 交易 WebApp 缺陷分析与重构方案（含手动多空/反手功能）

> 本文件是本次重构的**唯一契约来源**。后端/前端/验收三方均以本文档为准。
> 项目路径：`E:\python\trading_webapp`（FastAPI + Vue3/Vuetify + ccxt）。所有交易均为 Binance USDⓈ-M 永续合约。

---

## 1. 项目现状概览

| 层 | 技术栈 | 入口 |
|---|---|---|
| 后端 | FastAPI 0.111 / Pydantic 2.7 / ccxt 4.3.35 / pandas / numpy | `backend/app/main.py`、`backend/run.py` |
| 前端 | Vue 3.5 + Vuetify 3.10 + Pinia + Axios + vue-router | `frontend/src/main.ts`、`frontend/src/router.ts` |
| 部署 | Docker 多阶段构建、deploy.sh、start.bat | `Dockerfile`、`deploy.sh`、`start.bat` |

现有能力：自动按币种池开多/开空、批量平仓、同步 SL/TP、多因子再平衡、WebSocket 日志/进度推送、访问密钥鉴权。

---

## 2. 缺陷清单（按严重级别）

### P0 — 影响资金安全或核心功能不可用

- **P0-1 止盈从未下单**：`logic/sl_tp_logic_async.py::set_tp_sl_for_position_async` 只挂止损/移动止盈，`long_take_profit_percentage`/`short_take_profit_percentage` 虽可在前端配置，但后端完全未使用 → 止盈设置形同虚设。需同时挂 `STOP_MARKET`（止损）与 `TAKE_PROFIT_MARKET`（止盈），均为 `reduceOnly` 条件单。
- **P0-2 反手/同币种多合约时止盈止损可能挂错仓位**：`logic/exchange_logic_async.py::process_order_with_sl_tp_async` 用 `p.symbol == base_coin` 查找刚成交的仓位。同一币种若同时存在 USDT 与 USDC 合约（或历史残留仓位），会命中错误仓位。必须优先按 `full_symbol` 精确匹配。
- **P0-3 限价单部分成交后重试会重复下单**：`_execute_maker_order_with_retry_async` 超时撤单后按**原始数量**重新挂单；若首单已部分成交，实际敞口会超过目标。必须记录累计成交量，只对**剩余数量**重试，剩余量低于最小下单量则停止。
- **P0-4 全平仓未复核剩余仓位，反手可能裸开反向仓**：`close_position_async` 只要订单状态 closed 即返回成功；部分成交/交易所延迟会留下残留仓位。反手依赖“先平后开”，残留会导致反向敞口叠加。全平后必须重新拉取持仓确认 `contracts==0`（可重试一次），否则返回失败，禁止继续反向开仓。
- **P0-5 持仓查询吞异常**：`fetch_positions_with_pnl_async` 捕获所有异常返回 `[]`，交易所/网络故障会被误判为“无持仓”，导致平仓失败、反手被跳过或再平衡基准错误。应向上抛出，由全局异常处理/任务日志呈现。
- **P0-6 `cleanup_orphan_sltp_orders_async` 是空函数**：只 `pass`，同步 SL/TP 后的孤儿条件单清理从未生效，会累积废单。实现为：拉取全部挂单，撤销“已无持仓的 symbol”上的条件单；或删除该函数与调用（推荐实现，安全）。**两选一：实现或彻底移除，不允许保留空壳。**
- **P0-7 生产配置含真实 API Key/Secret 且被 Git 跟踪**：`user_settings.json` 已提交到仓库（`git ls-files` 可见）。本次在 `.gitignore` 中忽略该文件，并在报告中提示轮换密钥；禁止在代码/日志/测试里输出密钥。
- **P0-8 默认访问密钥等于公开访问**：`config.py` 默认 `app_access_key='CHANGE_THIS_IN_USER_SETTINGS.JSON'`，且 `security.py` 在 import 时固化。改为每次校验时读取（配置有缓存，开销可忽略），启动时若检测到默认/空密钥打印醒目告警。

### P1 — 明显缺陷/性能与可维护性问题

- **P1-1 每个子任务新建 ccxt 实例并 `load_markets()`**：自动开仓 55 个币种 = 55 次全量市场加载，接口权重高、易触发限频/超时。同一任务应只创建 **1 个** exchange，worker 共享。
- **P1-2 再平衡参数大量未实现**：前端暴露的布林带宽度过滤（`rebalance_bollinger_*`）、成交量放大过滤（`rebalance_volume_*`）后端未使用；`rebalance_method='foam'` 分支不存在。本次：实现布林带宽度放大与成交量放大过滤；移除前端未实现的 `foam` 选项与 `rebalance_foam_days` 字段；后端对非 `multi_factor_weakest` 的策略明确报错。
- **P1-3 `plan_calculator` 调试输出与边界缺陷**：残留大量 `print` 调试；自定义权重总和为 0 时静默返回空计划；币种未去重/未统一大写。重写为纯函数并加测试。
- **P1-4 `TradePlanRequest` 与 settings 字段重复且包含交易不需要的再平衡字段**：手工维护易漂移。裁剪为交易实际使用的字段；再平衡走独立 `RebalanceCriteria`。
- **P1-5 平仓/再平衡/同步 SLTP 均各自建 exchange**：与 P1-1 同一问题，统一由任务方法持有一个 exchange 上下文。
- **P1-6 部分平仓后原 SL/TP 数量不匹配**：部分平仓后条件单数量仍是原仓位数量，可能导致反向开仓/超量平仓。部分平仓成功后应重挂该仓位的 SL/TP。
- **P1-7 重复/无效的撤单封装**：`_cancel_sl_tp_orders_async` 与 `_force_cancel_all_orders` 两层包装完全相同，后者未使用；`_ensure_no_open_orders_async` 循环 3 次 × 2 接口，无谓放大请求。合并为一个函数，保留 `{'stop': True}` 逻辑。
- **P1-8 `update-coin-pools` 绕过锁直接写文件**：不更新内存全局变量、不与其他写操作互斥。统一到 `config.py` 的 `save_coin_pools()`。
- **P1-9 前端类型检查脚本无效**：`npm run build` 使用 `vue-tsc --noEmit`，但 tsconfig 是 references 结构，不会检查被引用工程；实测有 16 个类型错误仍能构建。改为 `vue-tsc --build --force && vite build`。
- **P1-10 前端类型错误**：`types.ts` 定义 `Log`，`logStore`/`LogDrawer` 却 import `LogEntry`（模块无此导出）；`lodash-es` 无类型声明；Vuetify `useDisplay().application` 不存在（`SettingsView`/`TradingView` 底部栏）；`ControlPanel` 事件参数 `unknown`；`LogDrawer` 虚拟滚动 item 为 unknown。
- **P1-11 重复挂载 `WeightConfigDialog`**：`App.vue` 与 `ControlPanel.vue` 各挂一次，弹窗状态双份。只保留 `App.vue` 一处。
- **P1-12 CORS 配置不合规**：`allow_origins=["*"]` 与 `allow_credentials=True` 同时开启；本应用用请求头鉴权，应关闭 credentials。
- **P1-13 弃用 API/启动健壮性**：`@app.on_event` 已弃用，改 lifespan；Docker 模式静态目录缺失时会抛错而非给出明确日志。

### P2 — 冗余代码与卫生问题

- `config/i18n.py` 只剩 4 个常量，注释却描述已删除的 Tkinter GUI；重命名为 `config/constants.py` 并删除误导注释。
- 未使用导入：`sl_tp_logic_async`（`Dict/Any/List` 等）、`api/rebalance.py`、`trading_service.py`、`api/positions.py` 等。
- 未使用依赖：前端 `vue-multiselect`（无引用）；`lodash-es` 仅用 `debounce`，且缺类型。用本地 `debounce` 工具替换并移除两个依赖（**无网络环境：只改 package.json，不执行 npm install**）。
- 未使用 action：`settingsStore.saveSelectedCoinLists`。
- 空目录 `frontend/src/router/`（`router.ts` 已足够）。
- `frontend/README.md` 为脚手架默认内容，可保留但不必改。
- 无任何自动化测试/CI；无 `.gitignore` 对 `user_settings.json` 的忽略。

---

## 3. 重构总原则

1. 不改变现有“自动开仓 / 平仓 / 同步 SL/TP / 再平衡”的行为语义（除上述明确修复项）。
2. 所有开仓、加仓、反手开仓一律走 **限价 post-only 单**（`create_order(type='limit', params={'postOnly': True})`），**禁止市价单**。止损/止盈/移动止盈属于条件单，保持不变。
3. 报价币种选择：**USDC 优先，其次 USDT**（`STABLECOIN_PREFERENCE = ['USDC','USDT']`），并记录最终交易对日志。
4. 每次后台任务只创建一个 ccxt exchange 实例，worker 共享。
5. 纯逻辑（计划计算、手动交易任务构建）与交易所 IO 分离，便于离线单元测试。
6. 测试不得访问网络/交易所，一律使用 fake exchange。

---

## 4. 新功能：手动做多 / 做空 / 反手

### 4.1 需求转译

用户选中若干币种后，可对每个币种指定：

| 动作 | 语义 | 下单 |
|---|---|---|
| `long` | 开多（或加多） | 限价 buy post-only，数量 = 目标 USD 价值 / 成交价 |
| `short` | 开空（或加空） | 限价 sell post-only |
| `reverse` | 反手 | 先按当前持仓方向**全平**（限价 reduce-only），确认无残留后，再按限价单开**反向**仓位 |

- 开仓后与现有自动开仓完全一致：设置杠杆 → 限价开仓 → 拉取实际仓位 → 挂 SL/TP（含移动止盈）。
- 交易对解析：`resolve_full_symbol(base)` 依次尝试 `BASE/USDC`、`BASE/USDC:USDC`、`BASE/USDT`、`BASE/USDT:USDT`；**有 USDC 合约就用 USDC**。
- 若 `reverse` 时该币种无持仓 → 跳过该币种并 `warning` 日志，**不得**凭空开反向仓。
- 若同一币种同时存在多/空仓（对冲模式）→ 跳过并 `error` 日志，避免歧义。
- 同一请求内币种去重；重复币种在 API 层直接 400。

### 4.2 后端 API 契约

#### GET `/api/trading/resolve-symbols?symbols=BTC,ETH,SOL`

响应：
```json
{
  "symbols": [
    {"symbol": "BTC", "full_symbol": "BTC/USDC:USDC", "quote": "USDC", "available": true},
    {"symbol": "ETH", "full_symbol": "ETH/USDT:USDT", "quote": "USDT", "available": true},
    {"symbol": "XXX", "full_symbol": null, "quote": null, "available": false}
  ]
}
```

#### POST `/api/trading/manual`

请求：
```json
{
  "request_id": "req-1720000000000-123456",
  "default_value": 100.0,
  "items": [
    {"symbol": "BTC", "action": "long",  "value": 100.0},
    {"symbol": "ETH", "action": "short"},
    {"symbol": "SOL", "action": "reverse", "value": 80.0}
  ]
}
```

字段规则：
- `items` 必填且非空；`symbol` 去空白转大写；`action ∈ {long, short, reverse}`；`value` 可省略，省略时依次回落：`default_value` → 配置中对应方向总价值按同方向币种数均分 → 反手用当前持仓名义价值。
- `value` 若提供必须 > 0。
- 请求内重复 `symbol` → HTTP 400，详情说明重复币种。
- 返回与其它任务接口一致：`{"message": "任务 '手动交易' 已成功提交到后台。"}`。

### 4.3 后端执行流程

新增 `backend/app/logic/manual_trade_logic.py`（**纯函数，禁止 IO/ccxt**）：

```python
@dataclass(frozen=True)
class ManualTradeTask:
    coin: str                 # 基础币种，大写
    action: str               # long / short / reverse
    side: str | None          # buy / sell（反手为平仓后的反向 side）
    value: float | None       # 目标 USD 名义价值
    close_full_symbols: tuple[str, ...] = ()  # 反手需要先全平的交易对
    skip_reason: str | None = None            # 无持仓/混合持仓/价值无效等，worker 只记日志
```

- `validate_manual_items(items)`：空列表、重复币种、非法 action、value<=0 → `ValueError`（API 层转 400）。
- `build_manual_trade_tasks(items, positions, config, default_value=None)`：返回任务列表；不访问交易所。
  - `long` → side=`buy`；`short` → side=`sell`。
  - `reverse` → 从 `positions` 中筛 `p.symbol.upper()==coin`：
    - 无持仓 → `skip_reason="无持仓，无法反手"`
    - `side` 集合既含 long 又含 short → `skip_reason="多空持仓并存，无法反手"`
    - 否则 side = 反向（long→sell，short→buy），`close_full_symbols` = 该币种所有持仓 full_symbol；value 缺省用这些持仓 notional 之和。
  - 价值仍无效（<=0）→ `skip_reason="下单价值无效"`。

`TradingService.manual_trade()`：
1. 同步校验（失败抛 `HTTPException(400)`）。
2. `_start_task("手动交易", self._manual_trade_task(payload), background_tasks)`。
3. `_manual_trade_task` 内：
   ```python
   config = load_settings()
   async with get_exchange_for_task() as exchange:
       positions = await fetch_positions_with_pnl_async(exchange, config.get('leverage', 1))
       tasks = build_manual_trade_tasks(...)
       async def worker(task):
           if task.skip_reason:
               await log_message(f"⚠️ {task.coin}: {task.skip_reason}", "warning")
               return False
           if task.close_full_symbols:
               for fs in task.close_full_symbols:
                   ok = await close_position_async(exchange, fs, 1.0, log_message, self._stop_event)
                   if not ok:
                       return False
                   await ws_manager.broadcast({"type": "position_closed",
                                               "payload": {"full_symbol": fs, "ratio": 1.0}})
                   if self._stop_event.is_set():
                       raise InterruptedError()
           plan = {"coin": task.coin, "value": task.value, "side": task.side}
           return await process_order_with_sl_tp_async(exchange, plan, config,
                                                       log_message, self._stop_event)
       await self._run_task_loop(tasks, worker, self.CONCURRENT_OPEN_TASKS, "手动交易")
   ```
4. `process_order_with_sl_tp_async` 日志必须包含最终交易对与报价币种，例如：
   `✅ BTC 交易对: BTC/USDC:USDC (USDC 优先)`。

### 4.4 前端交互（新增页面）

新增路由 `/manual`（导航名“手动交易”，icon `mdi-hand-coin-outline`），页面 `frontend/src/views/ManualTradeView.vue`：

1. **币种选择**：多选（来自 `settingsStore.availableCoins`，空则合并 long/short 池），支持搜索、chips。
2. **批量快捷**：`全部做多` / `全部做空` / `全部反手` 按钮；全局“默认每币种价值 (USD)”输入。
3. **每币种行**：币种、当前持仓（方向 + 名义价值 + 未持仓）、动作下拉（做多/做空/反手）、价值输入、报价币种标签（USDC/USDT，来自 `resolve-symbols`）。
4. **风险提示**：说明“所有开仓均为限价 post-only 单；反手=先全平再反向开仓；无持仓时反手会跳过”。
5. **执行**：`uiStore.launchTask('/api/trading/manual', {default_value, items}, '手动交易', items.length)`；任务结束后自动刷新持仓。
6. **下方复用** `PnlSummary` 与两个 `PositionsTable`，便于操作后核对。
7. 无选择、存在非法价值、`uiStore.isRunning` 时禁用执行按钮。

类型补充（`frontend/src/models/types.ts`）：
```ts
export type ManualTradeAction = 'long' | 'short' | 'reverse'
export interface ManualTradeItem { symbol: string; action: ManualTradeAction; value: number }
export interface ResolvedSymbol { symbol: string; full_symbol: string | null; quote: string | null; available: boolean }
```

### 4.5 安全与边界

- 手动交易接口与其他交易接口一样走 `X-API-KEY` 鉴权。
- 不与现有全局任务锁冲突：`_start_task` 已有“同时只允许一个任务”，前端 `launchTask` 也会拦截。
- 反手必须串行“平→确认→开”，不得并行。
- 单次请求币种数量上限建议 100（API 层校验），避免误操作提交上千任务。
- 日志/前端不得展示 API Key。

---

## 5. 验收标准

### 后端

1. `python -m compileall -q backend` 通过；`cd backend; python -c "from app.main import app"` 通过。
2. `python -m pytest backend/tests -q` 全绿（离线，无网络）。
3. 新增测试至少覆盖：
   - USDC 优先解析（fake markets：USDC+USDT 都存在时选 USDC；仅 USDT 时选 USDT）。
   - `validate_manual_items` / `build_manual_trade_tasks`：long/short/reverse、缺省价值、无持仓跳过、混合持仓跳过、重复拒绝。
   - 限价单：fake exchange 断言 `create_order` 的 type 为 `limit`、`params.postOnly is True`，且不存在 `market` 开仓调用。
   - 部分成交重试只下剩余数量。
   - SL/TP：enable 时可观察到 `STOP_MARKET` 与 `TAKE_PROFIT_MARKET`（`reduceOnly=True`）。
   - `calculate_trade_plan` 自定义权重/缺省/边界。
4. 全仓 grep：后端生产代码中不存在以 `'market'` 类型创建的开仓/平仓订单（条件单 `STOP_MARKET`/`TAKE_PROFIT_MARKET`/`TRAILING_STOP_MARKET` 除外）。
5. `POST /api/trading/manual` 在无鉴权时 403；合法 payload 返回任务提交信息（TestClient，可 mock exchange 或仅验证 400/403 分支）。

### 前端

1. `npx vue-tsc --build --force` 0 错误。
2. `npm run lint` 0 error（允许 0 warning）。
3. `npm run build` 成功（脚本已改为先 type-check 后 vite build）。
4. 路由 `/manual` 存在且导航可见；页面包含动作选择/价值/报价标签/执行按钮。
5. 现有页面类型与行为不回归（Dashboard/Trading/Settings）。

### 端到端/冒烟

1. 后端可启动（`python -m uvicorn app.main:app` 或 TestClient lifespan），`/api/status`、`/api/settings` 带正确 key 返回 200。
2. 前端 `dist` 构建产物包含新页面 chunk。
3. WebSocket 进度事件对“手动交易”任务复用现有 `progress_update`。

---

## 6. 验证命令（Windows PowerShell）

```powershell
# 后端
python -m compileall -q backend
python -m pytest backend/tests -q
cd backend; python -c "from app.main import app; print('IMPORT_OK')"; cd ..

# 前端
cd frontend
npx eslint .
npx vue-tsc --build --force
npm run build
cd ..

# 静态检查
rg -n "create_order\([^\n]*'market'|create_order\([^\n]*\"market\"" backend/app
```

> 环境说明：本机**无外网**，不得执行 `npm install` / `pip install`；已有 `node_modules` 与 pytest 8.3.2 可用。测试禁止访问 Binance，必须使用 fake exchange / monkeypatch。

---

## 7. 文件变更地图

### 后端
- 新增：`app/logic/manual_trade_logic.py`、`app/config/constants.py`（替代 i18n.py）、`tests/`（验收测试）
- 修改：`app/main.py`、`app/config/config.py`、`app/core/trading_service.py`、`app/core/security.py`、`app/core/exchange_manager.py`、`app/logic/exchange_logic_async.py`、`app/logic/sl_tp_logic_async.py`、`app/logic/plan_calculator.py`、`app/logic/rebalance_logic.py`、`app/logic/utils.py`、`app/api/trading.py`、`app/api/rebalance.py`、`app/api/settings.py`、`app/api/positions.py`、`app/models/schemas.py`
- 删除：`app/config/i18n.py`

### 前端
- 新增：`src/views/ManualTradeView.vue`、`src/utils/debounce.ts`
- 修改：`src/router.ts`、`src/models/types.ts`、`src/stores/logStore.ts`、`src/stores/settingsStore.ts`、`src/stores/uiStore.ts`、`src/components/ControlPanel.vue`、`src/components/CoinPoolsManager.vue`、`src/components/LogDrawer.vue`、`src/components/PositionsTable.vue`、`src/components/CloseDialog.vue`、`src/components/Snackbar.vue`（重命名 AppSnackbar.vue）、`src/views/SettingsView.vue`、`src/views/TradingView.vue`、`src/App.vue`、`package.json`、`eslint.config.ts`
- 删除：无引用依赖 `vue-multiselect`、`lodash-es`（改用本地 debounce）

### 根目录
- 修改：`.gitignore`（忽略 `user_settings.json`）
- 新增：本报告 `REFACTORING_REPORT.md`、验收报告 `VERIFICATION.md`

---

## 8. 明确的非目标

- 不改动 Binance 实盘账户/密钥，不实际下单，不做回测。
- 不引入新的第三方依赖（无网络）。
- 不改 Docker 构建流程/部署脚本（除必要兼容外）。
- 不重构 Vue 状态管理架构、不升级 Vuetify 版本。

---

## 9. 实施状态（Phase 1 已完成，2026-11-06）

- 后端/前端实现与独立验收已完成，详见 `VERIFICATION.md`：
  - `python -m pytest backend/tests -q` → **68 passed**（离线、无网络、无真实交易所）
  - `python -m compileall -q backend` / `cd backend; python -c "from app.main import app"` → 通过
  - `npx eslint .` → 0 error / 0 warning；`npx vue-tsc --build --force` → 0 error
  - `npm run build` → 成功（本机需 `TMP/TEMP` 指向项目内 `.tmp`，见 VERIFICATION.md 3.2）
  - 静态审计：无 `market` 开仓、无 pass 空壳、无 i18n 残留、无前端显式 any、/manual 已进入 dist
- 新功能 `POST /api/trading/manual` + `GET /api/trading/resolve-symbols` + 前端 `/manual` 页面：手动做多/做空/反手，限价 post-only、不允市价、USDC 优先；反手先全平并复核无残留再反向开仓。
- 安全收尾（Lead 执行）：
  - `user_settings.json` 已 `git rm --cached`（本地文件保留，不再被提交；含真实 Binance Key，**请在币安后台轮换 API Key/Secret**，必要时清理 Git 历史）。
  - `app_access_key` 已从默认占位符轮换为强随机值（见本地 `user_settings.json`；旧访问密钥立即失效，前端会重新弹出输入框）。
  - `.gitignore` 已忽略 `user_settings.json`、`.tmp/`、`signal_cooldown.json`、`monitor/`（用户拷入的独立仓库，含嵌套 .git 与远程 token，禁止提交）。
- 已知环境事项：`frontend/package-lock.json` 仍保留已移除的 `vue-multiselect`/`lodash-es` 条目（无网络未 install；联网后执行一次 `npm install` 即可同步）。
