# monitor 项目合并方案（Phase 2）

> 目标：把 `E:\python\trading_webapp\monitor`（独立监控/信号机器人）合并进本交易 WebApp，落地两项能力：
> 1. **API 限流/行情层统一优化**（复用 monitor 的 RestGuardian + 缓存思想）；
> 2. **精确信号扫描 + 信号自动开仓**（复用 monitor 的技术分析策略）。
>
> 本文件是 Phase 2 的契约来源。Phase 1（缺陷重构 + 手动做多/做空/反手）已完成，见 `REFACTORING_REPORT.md` / `VERIFICATION.md`。

---

## 0. 非目标（本阶段不做）

- 不合并 monitor 的 `position_protection_ws.py`（107KB 的 WS 实时仓位保护）、`periodic_reporter`、钉钉/桌面通知、`notification_service`。这些留作 Phase 3。
- 不修改、不删除根目录 `monitor/` 原始项目（它是用户拷入的参考源；其 `.git` 与远程含敏感 token，禁止读取/操作/提交）。
- 不引入需要联网安装的新依赖到运行环境；本地已安装 `loguru / pandas_ta / scikit-learn / scipy / requests`，但**后端 requirements.txt 必须显式声明实际 import 的新依赖**（loguru、pandas-ta），保证 Docker 可复现。
- 不默认开启信号扫描/自动开仓（默认关闭，避免启动即打交易所 API）。

---

## 1. 目录与模块设计（后端）

```
backend/app/
├── core/
│   ├── rest_guardian.py        # 新增：异步 REST 限流器（从 monitor 的 RestGuardian 提取）
│   └── exchange_manager.py     # 修改：新增共享 exchange（读接口复用，避免每次 load_markets）
├── signals/                    # 新增包
│   ├── __init__.py
│   ├── runtime.py              # alerted_states 持久化、cached_top_symbols、emit_signal、时间工具
│   ├── signal_store.py         # 线程安全信号环形缓冲 + 统计
│   ├── market_data.py          # 行情层：tickers/ohlcv/funding 缓存 + RestGuardian + 涨跌幅 TopN
│   ├── scanner.py              # 异步扫描循环 + 手动触发一次扫描
│   ├── auto_trader.py          # 信号过滤器 + 自动开仓调度
│   ├── analysis/               # 从 monitor/app/analysis 复制的纯分析模块
│   │   ├── __init__.py
│   │   ├── channels.py / indicators.py / levels.py / order_blocks.py / strategies.py / trend.py
│   └── __init__.py
├── api/signals.py              # 新增路由 /api/signals
└── models/schemas.py           # 新增 Signal 相关 Pydantic 模型
```

根目录新增 `signal_config.json`：从 `monitor/config/config.json` 提取 `app_settings` / `market_settings` / `strategy_params`（**删除 notification_settings、position_protection、periodic_reports，禁止带入任何密钥**）。扫描时作为策略参数默认值；运行开关/自动开仓参数放 `user_settings.json`（DEFAULT_CONFIG）。

---

## 2. API 限流与行情层（目标 1）

### 2.1 RestGuardian（`core/rest_guardian.py`，异步）

从 `monitor/app/tasks/position_protection_ws.py` 的 `RestGuardian`（约 265-347 行）提取并改造，接口：

```python
class CircuitBreakerException(Exception): ...

class RestGuardian:
    def __init__(self): ...
    async def call(self, func, *args, priority: str = "NORMAL", conf: dict | None = None, **kwargs):
        """统一包装所有 ccxt REST 调用：
        - asyncio.Semaphore(max(1, conf['api_max_concurrency'])) 控制并发
        - 全局最小请求间隔 conf['api_min_interval_sec']（默认 0.08s），跨调用串行节流
        - 429 指数退避 + 随机抖动，418 长冷却
        - 连续失败阈值触发熔断 conf['api_circuit_breaker_cooldown_sec']
        - 优先级 HIGH 可绕过熔断（仅限关键止损/平仓，信号扫描只用 NORMAL/LOW）
        """
```

配置键（从 `signal_config.json['position_protection']` 的 api_* 字段迁移到 `market_settings.api_limit`，并在 user_settings 提供覆盖）：
`api_max_concurrency`(=3)、`api_min_interval_sec`(=0.08)、`api_max_retries`(=3)、`api_failure_threshold`(=5)、`api_circuit_breaker_cooldown_sec`(=30)、`api_429_base_backoff_sec`(=2，指数退避上限 30s)、`api_418_cooldown_sec`(=60)。

### 2.2 共享 exchange（`core/exchange_manager.py`）

- 新增懒加载单例 `get_shared_exchange()`（`asyncio.Lock` 保护，只 `load_markets()` 一次），供**读接口**复用：
  `/api/positions`、`/api/settings/add-coin`、`/api/trading/resolve-symbols`、`/api/rebalance/plan`。
- `get_exchange_dependency()` 改为 yield 共享实例且**不 close**；新增 `close_shared_exchange()` 在 FastAPI lifespan shutdown 调用。
- 下单类后台任务继续使用 `get_exchange_for_task()`（独立实例、用完 close），避免任务间互相影响。
- 保持依赖可被测试 override：签名与行为不变，测试仍可 `app.dependency_overrides`。

### 2.3 行情缓存（`signals/market_data.py`）

```python
class MarketDataService:
    async def get_tickers(force=False) -> dict          # TTL 缓存（默认 30s），一次 fetch_tickers
    async def get_ohlcv(symbol, timeframe, limit) -> list # 按 (symbol,timeframe) 缓存；in-flight 去重（同 key 只发一次请求）
    async def get_funding_rates(symbols) -> dict         # 批量 fetch_funding_rates，缓存 60s
    async def get_top_symbols_by_volume(top_n, exclude)  # 基于 tickers 计算，USDC/USDT 去重，USDC 优先
```

要求：
- 扫描循环内 **每个 (symbol,timeframe) 只请求一次 K 线**，同一份 df 跑该 timeframe 下所有策略。
- 顶部行情每轮只请求一次 `fetch_tickers`；资金费率用批量接口而不是逐 symbol。
- 所有请求经 RestGuardian；失败/限流不崩溃，记录到扫描状态。
- 缓存 TTL 可配：`signal_ticker_cache_seconds`、`signal_ohlcv_cache_seconds`。

---

## 3. 信号引擎（目标 2 上半）

### 3.1 分析模块复制

从 `monitor/app/analysis/` 复制 6 个文件到 `backend/app/signals/analysis/`，仅做必要改造：
- 导入改为相对导入：`from .indicators import ...`、`from .runtime import ...`（runtime 在上一级：`from ..runtime import ...`）。
- 删除对 `monitor` 的 `app.*` 顶层导入；不要 import `notification_service`。
- 保留 `loguru`（加入 requirements）或替换为 stdlib logging；二选一，保持文件内一致。
- `strategies.py` 的 `_prepare_and_send_notification` 改为：
  - 保留冷却/成交量/趋势过滤逻辑；
  - 生成 title/message 后调用 `emit_signal(...)`（runtime），字段见 3.2；
  - 删除 `send_alert` 调用。
- **为每个策略补充结构化方向元数据**：在每个 `_prepare_and_send_notification` 调用前给 `signal_info` 增加：
  - `'strategy_name'`: 策略 key（ema_cross / ma_breakout / kdj_cross / volatility_breakout / level_breakout / rsi_divergence / trend_channel_breakout / consecutive_candles / ob_luxalgo / ob_fluxcharts / high_funding_rate）
  - `'direction'`: `'long' | 'short' | 'neutral'`，按信号语义严格映射（示例）：
    - level_breakout：BOS 向上 / 突破阻力 → long；BOS 向下 / 跌破支撑 → short；测试阻力/支撑 → neutral
    - order blocks：向上突破阻力区 → long；跌破支撑区 → short；测试区间 → neutral
    - ma_breakout / ema_cross：向上突破 → long；向下跌破 → short
    - kdj_cross：金叉/看涨 → long；死叉/看跌 → short
    - rsi_divergence：底背离 → long；顶背离 → short
    - trend_channel_breakout：突破下降通道 → long；跌破上升通道 → short
    - volatility_breakout / high_funding_rate / 连续K线警示：neutral（不自动开仓）
  - `'price'`: 当前收盘价（由 `_prepare_and_send_notification` 统一从 df 取）
- 允许保留 monitor 的告警文案格式（用于前端展示），但**信号方向/策略/价格必须结构化**，不得依赖标题关键字解析。

### 3.2 runtime（`signals/runtime.py`）

```python
alerted_states: dict[str, datetime]   # 冷却状态
cached_top_symbols: list[str]
def load_alert_states() -> None      # 从 SIGNAL_STATE_FILE 加载（默认项目根 signal_cooldown.json）
def save_alert_states() -> None      # 原子写；文件不存在/损坏时安全降级
def timeframe_to_minutes(tf) -> int
def calculate_cooldown_time(minutes, align_to_period_end=True) -> datetime
def emit_signal(*, symbol, full_symbol, timeframe, strategy, strategy_index, direction,
                price, title, message, dedupe_key) -> None
```

- `emit_signal` 可被任意线程调用：线程安全入队；由 `SignalStore` 的异步消费 task 落库并触发自动开仓。
- `SIGNAL_STATE_FILE` 用项目根（非 /usr/src/app；Windows 与 Docker 都可写）。

### 3.3 SignalStore（`signals/signal_store.py`）

- 线程安全环形缓冲（默认 200 条），字段：
```json
{"id":"uuid","created_at":"ISO8601 UTC","symbol":"BTC","full_symbol":"BTC/USDC:USDC",
 "timeframe":"1h","strategy":"ema_cross","strategy_index":0,
 "direction":"long","price":12345.6,"title":"...","message":"...","dedupe_key":"..."}
```
- 统计：`last_scan_at`、`next_scan_at`、`scanned_symbols`、`emitted_count`、`error_count`、`last_error`、`running`。
- 提供 `recent(limit, direction=None)`、`clear()`、`snapshot()`。

---

## 4. 扫描器（`signals/scanner.py`）

```python
class SignalScanner:
    def __init__(self, settings_loader, store, market_data, auto_trader): ...
    async def start(self): ...     # 创建后台 loop task（enabled 时）
    async def stop(self): ...
    async def scan_once(self) -> dict: ...   # 手动/定时共用；并发保护（同一时刻只跑一轮）
    def status(self) -> dict: ...
    async def _run_loop(self): ...
```

单个扫描周期：
1. `tickers = await market_data.get_tickers()`
2. 目标币种 = `signal_scan_static_symbols` ∪ TopN（`signal_scan_top_n`，按 quoteVolume 降序，排除稳定币/黑名单）；去重同 base 只取一个代表合约（USDC 优先，其次 USDT）。
3. 对每个 (symbol, timeframe)：
   - `df = await market_data.get_ohlcv(symbol, tf, limit)`（limit 取该 tf 下所有启用策略的最大值）
   - 对每个启用策略/参数组：`await asyncio.to_thread(strategy_func, funding_facade, symbol, tf, config, df.copy(), params, idx)`
   - 单个策略异常只记录，不中断整轮。
4. 每轮结束更新 status；异常记录 `last_error`，指数退避后下一轮。
5. 默认 `signal_scan_enabled=False`；间隔 `signal_scan_interval_seconds`（默认 300s，最小 30s）。
6. 时间框架来自 `signal_scan_timeframes`（默认 `['1h','4h']`；`signal_config.json` 中 `market_settings.timeframes` 作为默认）。
7. 扫描使用独立 async ccxt exchange（`initialize_exchange_async`），lifespan 中创建/关闭；不占用交易任务 exchange。

`funding_facade`：每轮提前批量取 `market_data.get_funding_rates(symbols)`，构造只读对象给策略（只实现 `fetch_funding_rate(symbol)`）。

---

## 5. 自动开仓（`signals/auto_trader.py`）

```python
class SignalAutoTrader:
    def __init__(self, settings_loader, position_provider, open_callback): ...
    async def on_signal(self, signal: dict) -> dict:  # 返回 {action:'skip'|'open'|'error', reason}
```

过滤顺序（全部满足才开仓）：
1. `signal_auto_trade_enabled` 为 True；
2. `direction in signal_auto_trade_directions`（默认 long+short，neutral 永不开仓）；
3. `strategy in signal_auto_trade_strategies`（默认仅方向性入场策略白名单：ema_cross, ma_breakout, kdj_cross, level_breakout, rsi_divergence, trend_channel_breakout, ob_luxalgo, ob_fluxcharts）；
4. `timeframe in signal_auto_trade_timeframes`；
5. 确认数：最近 `signal_auto_trade_confirmation_window_seconds` 内同 symbol+同 direction 的不同策略数 ≥ `signal_auto_trade_confirmations`（默认 1，可调高做"精确信号"）；
6. 冷却：同 symbol 距上次自动开仓 < `signal_auto_trade_cooldown_seconds` → skip；
7. 当前持仓数 < `signal_auto_trade_max_positions`；该 symbol 已有持仓（任意方向）默认 skip（不叠加）；
8. 调用 `open_callback(signal)`，成功/失败记录 `last_auto_open` 与日志。

`open_callback` 由 `TradingService.auto_open_from_signal(signal, config)` 实现：
- 金额：`signal_auto_trade_value_usd`（默认 100）；
- 复用 **现有** `process_order_with_sl_tp_async`：限价 post-only、USDC 优先、开仓后按 settings 挂 SL/TP；
- 与用户任务互斥：若 `TradingService._is_running` 为 True → 记 warning 并 skip（不打断用户任务）；
- 通过 `asyncio.create_task` + 现有 `_execute_and_log_task` 流程广播日志/进度（无需 FastAPI BackgroundTasks；可抽 `schedule_task()`）；
- 失败不重试（下一轮信号再判断）。

---

## 6. API 契约（`api/signals.py`，前缀 `/api/signals`，鉴权同其它交易接口）

`GET /api/signals` → 200：
```json
{
  "status": {
    "enabled": false, "running": false, "last_scan_at": null, "next_scan_at": null,
    "scanned_symbols": 0, "emitted_count": 0, "error_count": 0, "last_error": null,
    "auto_trade_enabled": false, "last_auto_open": null
  },
  "signals": [ { "id":"...", "created_at":"...", "symbol":"BTC", "full_symbol":"BTC/USDC:USDC",
                 "timeframe":"1h", "strategy":"ema_cross", "strategy_index":0,
                 "direction":"long", "price":123.4, "title":"...", "message":"..." } ],
  "config": { "signal_scan_enabled": false, "signal_scan_interval_seconds": 300, "...": "..." }
}
```

- `POST /api/signals/scan` → `{"message": "扫描任务已提交"}`；已有扫描在跑 → 409。
- `POST /api/signals/config` body 为 `signal_*` 字段的部分字典 → 校验后写入 settings（`save_settings`）并热应用；返回 `{"config": {...}}`。
- `POST /api/signals/auto-trade` body `{"enabled": true}` → 快捷开关；返回 `{"enabled": true}`。
- `POST /api/signals/clear` → `{"cleared": true, "remaining": 0}`。

配置项全部加入 `config.DEFAULT_CONFIG`（键名 `signal_*`，默认关闭扫描/自动开仓）。API 层用 Pydantic 模型校验，非法值 400。

---

## 7. 前端契约（`/signals` 页面）

新增 `frontend/src/views/SignalsView.vue` + 路由 `/signals`（name `signals`，title「信号监控」，icon `mdi-radar`；App.vue 自动导航）：

1. 顶部状态卡：扫描开关、运行状态、上次/下次扫描时间、已扫描币种数、信号数、错误数；按钮「立即扫描」「清空信号」。
2. 自动开仓卡：启用开关；方向多选（做多/做空）；策略白名单多选；时间框架多选；确认数、冷却秒数、单笔金额、最大持仓数；保存调用 `POST /api/signals/config`。
3. 信号表：时间、币种、方向（做多绿色/做空红色/观望灰色）、策略、周期、价格、标题；可按方向过滤；最多显示 200 条。
4. 执行日志复用现有 WebSocket 日志（后端 log_message 广播）；自动开仓事件也写入日志。
5. 类型定义加入 `models/types.ts`；每 10s 轮询 `GET /api/signals`（页面可见时），或复用现有状态刷新习惯；不引入新依赖。

---

## 8. 验收标准

### 后端
1. `python -m compileall -q backend`、`cd backend; python -c "from app.main import app"` 通过；`pytest backend/tests -q` 全绿（新增测试离线）。
2. `signal_config.json` 存在且不含任何密钥/通知配置；`backend/requirements.txt` 增加 `loguru`、`pandas-ta`（与本地版本一致或 `>=`）。
3. 默认 `signal_scan_enabled=false`、`signal_auto_trade_enabled=false`；启动不发起扫描请求。
4. RestGuardian 测试：并发上限、最小间隔、429 指数退避、熔断、HIGH 绕过熔断。
5. MarketDataService 测试：ticker/OHLCV 缓存命中不重复请求；同 key in-flight 去重；TopN 选择与 USDC 优先。
6. 信号测试：fake 行情 + fake 策略产出 → 结构化 SignalRecord（direction/strategy/price）；冷却去重生效；auto_trader 过滤（方向/策略/时间框架/确认数/冷却/最大持仓/已有持仓）全部覆盖；neutral 永不自动开仓。
7. 自动开仓路径复用 `process_order_with_sl_tp_async`，静态审计无 `'market'` 开仓；USDC 优先逻辑有测试。
8. API 测试：无 key 403；`POST /api/signals/config` 非法值 400；`GET /api/signals` 结构正确（TestClient，不连交易所/不启动扫描）。

### 前端
1. `npx eslint .` 0 error；`npx vue-tsc --build --force` 0 error；`npm run build` 成功（命令见第 9 节）。
2. `/signals` 路由存在、导航可见；页面能渲染 status/signals/config 三种数据；扫描/保存/清空按钮调用正确接口；无信号时显示空态。

### 端到端冒烟
- `GET /api/signals` 带正确 key 返回 200 且 `enabled=false`；`POST /api/signals/scan` 在 disabled 时返回 409/400（明确提示先启用）或允许手动扫描（二选一，必须文档化）；TestClient 不连真实交易所。
- `dist` 构建产物包含「信号监控」。

---

## 9. 本机验证命令（Windows PowerShell）

```powershell
python -m compileall -q backend
python -m pytest backend/tests -q
cd backend; python -c "from app.main import app; print('IMPORT_OK')"; cd ..

cd frontend
npx eslint .
npx vue-tsc --build --force
$env:TMP='E:\python\trading_webapp\.tmp'; $env:TEMP=$env:TMP; npm run build
cd ..
```

> 前端构建必须先重定向 TMP/TEMP 到项目内 `.tmp`（esbuild 在系统临时目录删文件会被 Windows ACL 拒绝；不是代码问题）。

---

## 10. 交付文件地图（Phase 2）

### 后端（backend-dev）
- 新增：`app/core/rest_guardian.py`、`app/signals/{__init__,runtime,signal_store,market_data,scanner,auto_trader}.py`、`app/signals/analysis/*`（6 个复制文件）、`app/api/signals.py`、`signal_config.json`
- 修改：`app/main.py`（lifespan 启动/停止 scanner、close shared exchange、include router）、`app/core/exchange_manager.py`、`app/core/trading_service.py`（auto_open_from_signal + schedule_task）、`app/models/schemas.py`、`app/config/config.py`（signal_* 默认值 + signal 文件路径）、`app/api/positions.py`/`settings.py`/`trading.py`/`rebalance.py`（如改用共享 exchange）、`backend/requirements.txt`
- 不改：Phase 1 的限价单/反手/SL-TP 核心行为。

### 前端（frontend-dev）
- 新增：`src/views/SignalsView.vue`
- 修改：`src/router.ts`、`src/models/types.ts`（信号相关类型）、必要时 `src/stores/settingsStore.ts`（signal_* 默认值）

### Lead
- `Dockerfile`（复制 `signal_config.json`）、`.gitignore`（`.tmp/`、`signal_cooldown.json`）、Phase 2 集成审查与最终验证。

### 验收（verifier）
- `backend/tests/test_signals_*.py`、`backend/tests/test_rest_guardian.py`、`backend/tests/test_market_data.py`
- `VERIFICATION_PHASE2.md`

---

## 11. 风险与约束

- 策略文件来自 monitor（含中文文案与 loguru），复制后**不得改变原策略判定逻辑**，只允许改导入、通知钩子与方向元数据。
- 扫描/自动开仓默认关闭；任何真实 Binance 请求只发生在用户显式启用后。
- 自动开仓必须与现有全局任务锁互斥，禁止与用户手动任务并发下单。
- monitor 原始目录只读；其 `.git/config` 含远程 token，禁止读取、复制、提交。
- 扫描信号是"技术指标信号"，不构成收益保证；前端需展示风险提示。
