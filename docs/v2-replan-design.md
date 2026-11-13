# v2 结构位/灾难线重估（Re-plan）设计稿 v1

> 状态：**已实施（2026-11-13）**。评审结论：未触发档位**维持只外移**（原方案），
> 拒绝双向重估——内移会在重算瞬间造成"价格已在线外"的假破位，等于自动在回调低点触发减仓。
> 实现：`risk_model.replan_plan`（纯函数，全部约束在内）+ `runner._maybe_replan`（触发器）；
> 测试 `tests/test_protection_replan.py`（16 例）。
> 背景：`build_plan` 目前只在开仓时执行一次（`atr_at_plan` 固定）。持仓跨 2-3 天后
> 结构位漂移、ATR 变化，四档线与灾难线不再贴合市场；波动率放大时灾难线可能过近。

## 一、触发时机（三选一先到先触发）

| 触发器 | 条件 | 理由 |
|---|---|---|
| T1 周期触发 | 距 `plan.built_at` ≥ `replan_interval_sec`（默认 24h） | 结构位是 2h 级别概念，24h 重估一次足够 |
| T2 波动率剧变 | `当前 ATR14(2h) / plan.atr_at_plan` ≥ 1.5 或 ≤ 0.6 | 波动率腰斩/暴涨时旧线全部失真 |
| T3 加仓重建 | 已有逻辑（base_contracts 增大换周期） | 不变，重估不与换周期混淆 |

防抖：重估后 60 分钟内不再次重估（`replan_cooldown_sec`）。

## 二、重算范围与硬约束（安全边界，逐条可单测）

重算：结构位（7/26/83）、四档线 `levels`、灾难线 `disaster_stop`、`atr_at_plan`。
**不重算**：`entry`、`risk`（R 锚定原计划）、`tp_prices`（R 已锁死，改了会与已触发 TP 状态矛盾）、
`tp_ratios`、`tier_ratios`、`base_contracts`、`cycle_id`、`version`（version 只随实际减仓递增）。

1. **已触发档位冻结**：`tiers_done` 里的档不参与重算（done 的档位线仅保留记录用途）。
2. **未触发档位只许外移**（long：新线 ≤ 旧线；short：新线 ≥ 旧线）：档位外移 = 减仓更晚触发 = 不改变已发生的风险轨迹。内移会"追认"一次从未发生的减仓，语义混乱。
   - 例外：若外移后与更深的未触发档间距 < `tier_min_gap_atr`，压缩到间距下限。
3. **灾难线只许远离现价**：新灾难线与当前价的距离 ≥ `disaster_atr_buffer × 当前 ATR`（long：新线 ≤ 现价 − 距离；short 对称）。防止重估把灾难线拉到现价附近造成误杀全平。
   - 同时灾难线必须仍在 T4 之外（long：≤ levels[3] − buffer）。
4. **risk_min/max 钳制保持**：重算后的 T1 仍被 `[risk_min_pct, risk_max_pct]` 钳制（相对原 entry）。
5. **pending 计时器保留**：档位线移动后，`pending` 里同档的首次破位时间戳不清零——
   如果新线让价格"看起来仍在破位"，确认计时继续；如果新线在线内，自然清零（现有逻辑已处理）。
6. **重估不发交易动作**：重估本身只 patch plan + 落账本事件（`replan`），绝不顺带减仓/挂单；
   动作留给之后的正常决策轮。

## 三、状态与账本

`plan` 新增字段：`replanned_at`（时间戳）、`replan_count`（次数，上限 30 防异常刷写）、
`replan_reason`（'scheduled' | 'atr_jump' | 'atr_drop'）。
账本事件：`ledger.log_event(symbol, side, 'replan', f'重估#{n}({reason}): T1 旧→新 ... 灾难线 旧→新')`。

## 四、配置项（新增，全部有默认值）

```
'replan_enabled': True,
'replan_interval_sec': 86400.0,     # T1 周期触发
'replan_atr_up_ratio': 1.5,         # T2 波动率放大阈值
'replan_atr_down_ratio': 0.6,       # T2 波动率萎缩阈值
'replan_cooldown_sec': 3600.0,      # 防抖
```

`dry_run=True` 时：重估照常计算并记事件，但不落 plan（便于先观察重算结果是否合理）。

## 五、实现位置

- `risk_model.py`：新增纯函数 `replan_plan(plan, structure, atr, current_price, conf, now, tiers_done) -> Optional[dict]`
  （返回 plan patch 或 None=无需/不安全重估），约束 1-5 全部在该纯函数内实现，可离线回放验证。
- `runner.py`：`_prepare` 里新周期判断之后、决策之前调用；触发条件检查 + cooldown + dry_run 处理。
- `api/protection.py`：4 个新配置项校验（布尔/数值范围）。

## 六、验证计划

1. 纯函数单测：约束逐条断言（外移、冻结、灾难线钳制、gap 压缩、pending 保留）。
2. 历史回放（复用 `tools/sl_calibration/` 数据）：对比重估开/关两组，统计灾难线误杀率与档位触发时点变化。
3. dry_run 观察 1-2 天后再放开实盘。

## 七、已知取舍（评审重点）

- **未触发档位只外移**是保守选择：代价是结构上移（long 减仓线本可以上收）时不收紧敞口。
  备选方案"双向重估 + 已持仓部分按新线补动作"复杂度高、易引入自激，不建议第一版做。
- R/TP 不重估：R 锚定的是开仓时刻的结构，重估后 R 语义会漂移；维持"一个周期一个 R"。
- 30 次 `replan_count` 上限只是异常熔断，正常 24h 一次用不到。
