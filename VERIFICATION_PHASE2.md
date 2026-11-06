# Phase 2 验收报告（monitor 合并 + SQLite 迁移）

> 验收对象：E:\python\trading_webapp
> 契约来源：`MERGE_PLAN.md`（monitor 合并）+ 追加需求「JSON → SQLite」
> 验收时间：2026-11-06
> 验收人：Lead（后端/前端由独立 subagent 实施，本报告为独立复核）

## 1. 结论

**全部通过**。三大目标落地：

1. **缺陷重构 + 手动多空/反手**（Phase 1，当日早前完成）：见 `REFACTORING_REPORT.md` / `VERIFICATION.md`。
2. **monitor 合并**：API 限流（RestGuardian + 共享 exchange + 行情缓存）与精确信号自动开仓（信号扫描引擎 + /api/signals + /signals 前端页）全部实现。
3. **SQLite 迁移**：settings / 币种池 / 信号冷却状态全部改存 `data/app.db`，旧 JSON 保留为一次性迁移来源。

## 2. 验证结果（Lead 独立复核）

| 命令 | 结果 |
|---|---|
| `python -m compileall -q backend` | ✅ exit 0 |
| `python -m pytest backend/tests -q`（C:\Python312） | ✅ **133 passed**（Phase 1 的 68 个无回归 + 新增 65 个，全部离线 fake exchange） |
| `cd backend; python -c "from app.main import app"` | ✅ IMPORT_OK，日志显示「Loaded coin pools from SQLite. Total: 190, Long: 4, Short: 184」 |
| `npx eslint .`（frontend） | ✅ 0 error / 0 warning |
| `npx vue-tsc --build --force` | ✅ 0 类型错误 |
| `npm run build` | ✅ 成功（需 TMP/TEMP 指向项目内 `.tmp`；vite emptyOutDir 与本机 safe-delete shim 冲突时先手动清空 dist） |
| dist 产物检索 | ✅ 含「信号监控」「立即扫描」「清空信号」「自动开仓」 |
| 静态审计 `create_order(...'market')` | ✅ 无 market 开仓（仅 STOP_MARKET / TAKE_PROFIT_MARKET / TRAILING_STOP_MARKET 条件单） |

## 3. 交付内容

### 3.1 SQLite 存储（新需求）
- 新增 `backend/app/core/database.py`：sqlite3 + WAL + RLock + 短连接；表 `settings` / `coin_pools` / `signal_state`。
- `config.py` 的 `load_settings / save_settings / add_coin_to_pool / save_coin_pools / load_coin_lists` 全部改读写 SQLite，**对外签名与行为不变**；`api_key/api_secret` 环境变量覆盖逻辑保留。
- 幂等迁移：首次启动把 `user_settings.json`（32 项）与 `coin_lists.json`（190/4/184）导入 DB，旧 JSON 保留不动；已实测迁移成功、二次启动不重复导入。
- `.gitignore` 新增 `data/`、`*.db*`；Dockerfile 预建 `/app/data`（建议运行时挂载卷持久化）。

### 3.2 monitor 合并（按 MERGE_PLAN.md）
- **限流**：`core/rest_guardian.py`（并发上限/最小间隔/429 指数退避/418 冷却/熔断/HIGH 绕过）；`exchange_manager.py` 新增共享 exchange（读接口复用，只 load_markets 一次）。
- **信号引擎**：`app/signals/`（runtime、signal_store、market_data、scanner、auto_trader、service + analysis 6 个复制文件）；策略判定逻辑未改；每轮每 (symbol,timeframe) 只拉一次 K 线，tickers TTL 缓存，funding 批量接口，全部请求走 RestGuardian。
- **API**：`/api/signals`（GET 列表+状态、POST scan/config/auto-trade/clear），鉴权同其它接口，非法配置 400。
- **自动开仓**：`TradingService.auto_open_from_signal` 复用 `process_order_with_sl_tp_async`——**限价 post-only、不允市价、USDC 优先、开仓后挂 SL/TP**；与全局任务锁互斥；8 级过滤链（开关/方向/策略白名单/时间框架/确认数/冷却/最大持仓/已有持仓），neutral 信号永不开仓。
- **配置**：项目根 `signal_config.json`（仅 app_settings/market_settings/strategy_params，无任何密钥）；16 个 `signal_*` 键入 `DEFAULT_CONFIG`，**默认扫描与自动开仓均关闭**。
- **前端**：`/signals` 页（状态卡、自动开仓配置卡、方向过滤信号表、10s 轮询、风险提示），无新依赖。
- `requirements.txt` 追加 `loguru`、`pandas-ta`。

### 3.3 顺带修复（均有测试守护）
- monitor 复制代码中 3 个阻断性 bug：MA 突破模板 `str.format` 调用方法导致信号永不发射；level_breakout 模板引号键 4 处错误导致 BOS 信号永不发射（该策略在自动开仓白名单内，必须修复）。

## 4. 环境备注
- 本机 Python 为 `C:\Python312`（3.12.3）；`pandas_ta` 的 Windows bug（`alligator.py` `from posix import pread`）已在 site-packages 本地修复（Linux/Docker 不受影响）。
- 本机 safe-delete shim 会导致 vite/pytest 清理目录时报 trash 错误：pytest 已忽略（不影响结果），vite 构建先手动清空 dist。
- Phase 1 遗留的外部动作不变：**请在币安后台轮换 API Key/Secret**；`user_settings.json` 已迁入本地 `data/app.db`（已 gitignore）。

## 5. 使用说明
1. 启动后端后进入「信号监控」页，打开扫描开关并保存配置即可开始扫描（默认关闭，不会在启动时打交易所 API）。
2. 「精确信号自动开仓」：打开自动开仓开关 → 选方向/策略白名单/时间框架 → 调高确认数（如 ≥2）提高精度 → 设置单笔金额与最大持仓数。
3. 所有开仓仍为限价 post-only；有 USDC 合约的币种自动用 USDC 保证金。
