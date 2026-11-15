"""仓位保护 v2 离线测试：风险计划 / 决策 / 账本隔离。

全部离线：不访问交易所，不读写真实 data/app.db。
"""
from __future__ import annotations

import dataclasses

import pytest

from app.core import database
from app.protection import ledger, risk_model, runner


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "USER_SETTINGS_FILE", tmp_path / "user_settings.json")
    monkeypatch.setattr(database, "COIN_LISTS_FILE", tmp_path / "coin_lists.json")
    database.init_db()
    return tmp_path


CONF = dict(risk_model.V2_DEFAULTS)


def _plan(side="long", entry=100.0, atr=2.0, structure=(97.0, 95.0, 92.0)):
    return risk_model.build_plan(side, entry, atr, structure, CONF)


def _state(side="long", entry=100.0, base=10.0, contractsn=None, plan=None):
    state = risk_model.new_state("c1", side, entry, base, plan or _plan(side, entry), 0.0)
    state["contracts"] = base if contractsn is None else contractsn
    return state


def _snap(side="long", price=100.0, entry=100.0, contracts=10.0, atr=2.0, now=1000.0):
    return risk_model.Snapshot(
        symbol="BTC/USDC:USDC", side=side, entry=entry, price=price,
        last_close=price, contracts=contracts, base_contracts=10.0,
        atr=atr, structure=(97.0, 95.0, 92.0), closed_ts=0, now=now,
    )


def _apply(state, result):
    state.update(result.get("patch") or {})
    return result["actions"]


# ---------------------------------------------------------------------------
# 风险计划
# ---------------------------------------------------------------------------
def test_plan_levels_are_strictly_ordered_for_long():
    plan = _plan("long")
    levels = plan["levels"]
    assert levels[0] > levels[1] > levels[2] > levels[3] > 0
    assert levels[0] < 100.0
    assert plan["disaster_stop"] < levels[3]
    assert plan["tp_prices"][0] > 100.0
    assert plan["tp_prices"] == sorted(plan["tp_prices"])
    assert sum(plan["ratios"]) == pytest.approx(1.0)


def test_plan_levels_are_strictly_ordered_for_short():
    plan = _plan("short", structure=(103.0, 105.0, 108.0))
    levels = plan["levels"]
    assert levels[0] < levels[1] < levels[2] < levels[3]
    assert levels[0] > 100.0
    assert plan["disaster_stop"] > levels[3]
    assert plan["tp_prices"] == sorted(plan["tp_prices"], reverse=True)


def test_plan_clamps_too_close_structure_to_min_risk():
    plan = risk_model.build_plan("long", 100.0, 0.5, (99.95, 99.9, 99.8), CONF)
    # 结构位贴着开仓价时，T1 至少退到 risk_min_pct(1.5%)
    assert plan["levels"][0] == pytest.approx(100.0 * (1 - 0.015), rel=1e-9)
    assert plan["risk"] == pytest.approx(1.5, rel=1e-9)


def test_plan_clamps_too_far_structure_to_max_risk():
    plan = risk_model.build_plan("long", 100.0, 5.0, (50.0, 45.0, 40.0), CONF)
    assert plan["risk"] == pytest.approx(100.0 * 0.08, rel=1e-9)


def test_plan_normalizes_ratios_over_100_percent():
    conf = dict(CONF, tier_ratios=[0.5, 0.5, 0.5, 0.5])
    plan = risk_model.build_plan("long", 100.0, 2.0, (97.0, 95.0, 92.0), conf)
    assert sum(plan["ratios"]) == pytest.approx(1.0)
    assert plan["ratios"] == [0.25, 0.25, 0.25, 0.25]


# ---------------------------------------------------------------------------
# 决策：结构减仓
# ---------------------------------------------------------------------------
def test_tier_requires_sustained_confirmation():
    state = _state()
    level = state["plan"]["levels"][0]

    # 刚跌破：只记 pending，不下单（首轮会有一次兜底 STOP，不算减仓）
    actions = _apply(state, risk_model.decide(state, _snap(price=level - 0.1, now=1000.0), CONF))
    assert [a for a in actions if a["type"] == "reduce"] == []
    assert state["pending"]["0"] == 1000.0

    # 持续 31 秒：触发 T1，减 15%
    actions = _apply(state, risk_model.decide(state, _snap(price=level - 0.1, now=1031.0), CONF))
    reduce = [a for a in actions if a["type"] == "reduce"]
    assert len(reduce) == 1
    assert reduce[0]["tiers"] == [0]
    assert reduce[0]["ratio"] == pytest.approx(0.15)


def test_pending_clears_when_price_recovers():
    state = _state()
    level = state["plan"]["levels"][0]
    _apply(state, risk_model.decide(state, _snap(price=level - 0.1, now=1000.0), CONF))
    assert "0" in state["pending"]
    _apply(state, risk_model.decide(state, _snap(price=level + 5, now=1010.0), CONF))
    assert "0" not in state["pending"]


def test_gap_through_two_tiers_sums_ratio_in_one_action():
    state = _state()
    levels = state["plan"]["levels"]
    actions = _apply(state, risk_model.decide(state, _snap(price=levels[1] - 0.1, now=1100.0), CONF))
    # 首次跌破两档：确认计时刚开始，本轮不动作
    assert [a for a in actions if a["type"] == "reduce"] == []
    actions = _apply(state, risk_model.decide(state, _snap(price=levels[1] - 0.1, now=1200.0), CONF))
    reduce = [a for a in actions if a["type"] == "reduce"]
    assert len(reduce) == 1
    assert reduce[0]["tiers"] == [0, 1]
    assert reduce[0]["ratio"] == pytest.approx(0.35)


def test_disaster_exit_has_priority_and_no_confirmation():
    state = _state()
    disaster = state["plan"]["disaster_stop"]
    actions = _apply(state, risk_model.decide(state, _snap(price=disaster - 0.5, now=1000.0), CONF))
    assert len(actions) == 1
    assert actions[0]["type"] == "exit"
    assert actions[0]["tag"] == "disaster"


def test_budget_never_exceeds_one():
    state = _state()
    levels = state["plan"]["levels"]
    ratios = state["plan"]["ratios"]
    state["tiers_done"] = [0, 1, 2, 3]
    # 四档都执行过：再跌破只可能是全平，不能再减
    actions = _apply(state, risk_model.decide(state, _snap(price=levels[3] - 0.1, now=1000.0), CONF))
    assert all(a["type"] != "reduce" for a in actions)
    assert sum(ratios) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 止盈：决策层已不产出动作，改由交易所预挂 post-only 单
# ---------------------------------------------------------------------------
def test_take_profit_ladder_defaults():
    """默认阶梯 1.5R / 2.5R / 4R，减 20%/25%/30%，留 25% 给追踪。"""
    plan = _plan()
    assert plan["tp_ratios"] == pytest.approx([0.20, 0.25, 0.30])
    risk = plan["risk"]
    for i, mult in enumerate((1.5, 2.5, 4.0)):
        assert plan["tp_prices"][i] == pytest.approx(100.0 + risk * mult)


def test_take_profit_leaves_keep_ratio():
    """三档合计 75%，剩 25% 不挂止盈单（keep_ratio 默认 0.25）。"""
    conf = CONF
    assert conf["tp_keep_ratio"] == pytest.approx(0.25)
    plan = _plan()
    assert sum(plan["tp_ratios"]) == pytest.approx(1.0 - conf["tp_keep_ratio"])


def test_take_profit_still_raises_stop_after_tp1():
    """TP1 成交后止损推到保本：止盈执行方式变了，保护链不能断。"""
    state = _state()
    state["tp_done"] = [0]
    actions = _apply(state, risk_model.decide(state, _snap(price=101.0, now=1000.0), CONF))
    stops = [a for a in actions if a["type"] == "stop"]
    assert stops and stops[0]["price"] > 100.0


def test_next_tp_level_skips_done():
    """挂单层只挂「下一个未完成档」，已完成档不再重复挂。"""
    state = _state()
    plan = state["plan"]
    assert risk_model.next_tp_level(state, plan) == 0
    state["tp_done"] = [0, 1]
    assert risk_model.next_tp_level(state, plan) == 2
    state["tp_done"] = [0, 1, 2]
    assert risk_model.next_tp_level(state, plan) is None


def test_breakeven_stop_after_half_r():
    state = _state()
    risk = state["plan"]["risk"]
    actions = _apply(state, risk_model.decide(
        state, _snap(price=100.0 + risk * 0.6, now=1000.0), CONF))
    stops = [a for a in actions if a["type"] == "stop"]
    assert stops, "0.5R 之后必须把止损推到保本"
    assert stops[0]["price"] > 100.0


def test_breakeven_stop_uses_atr_buffer():
    """保本位 = 开仓价 + max(0.2%, 0.3×ATR)。ATR=2（占价 2%）时应落在 100.6，不是 100.2。

    旧口径的 +0.2% 死数让保本单离现价只有半个 ATR 以内，1h 的普通回撤就能扫到
    （2026-11-15：0.5R 保本 → 立刻被扫 → 行情继续走，吃不到大增幅）。
    """
    state = _state()
    risk = state["plan"]["risk"]
    actions = _apply(state, risk_model.decide(
        state, _snap(price=100.0 + risk * 0.6, now=1000.0), CONF))
    stops = [a for a in actions if a["type"] == "stop"]
    assert stops and stops[0]["price"] == pytest.approx(100.6)


def test_breakeven_keeps_price_pct_floor_when_atr_is_small():
    """ATR 很小时退回价格比例下限 0.2%，不会把保本单贴到开仓价上。"""
    state = _state()
    risk = state["plan"]["risk"]
    actions = _apply(state, risk_model.decide(
        state, _snap(price=100.0 + risk * 0.6, atr=0.05, now=1000.0), CONF))
    stops = [a for a in actions if a["type"] == "stop"]
    assert stops and stops[0]["price"] == pytest.approx(100.2)


def test_trailing_line_sits_1_5_atr_below_peak():
    """浮盈 4R、峰值 106、ATR 2：止损 = 106 − 1.5×2 = 103。

    旧口径 2.5 ATR 只会给到 101；这也是「0.5R~1.8R 完全没跟随」的同一处参数。
    """
    state = _state()
    state["peak"] = 106.0
    actions = _apply(state, risk_model.decide(state, _snap(price=106.0, now=1000.0), CONF))
    stops = [a for a in actions if a["type"] == "stop"]
    assert stops and stops[0]["price"] == pytest.approx(103.0)


def test_trailing_line_below_breakeven_does_not_loosen_stop():
    """浮盈刚过 0.5R（102.4）：peak−1.5ATR 还在保本下方 → 仍取保本位，绝不倒退。"""
    state = _state()
    risk = state["plan"]["risk"]
    price = 100.0 + risk * 0.6
    state["peak"] = price
    actions = _apply(state, risk_model.decide(state, _snap(price=price, now=1000.0), CONF))
    stops = [a for a in actions if a["type"] == "stop"]
    assert stops and stops[0]["price"] == pytest.approx(100.6)


def test_legacy_trailing_defaults_are_upgraded(monkeypatch):
    """老配置把旧默认值（2.5 ATR / 1R 起点）原样存了下来，升级后必须跟随新默认；
    用户真改过的值（0.8R 保本）不能被覆盖。"""
    monkeypatch.setattr(runner, 'load_protection_config', lambda: {
        'position_protection': {
            'trailing_atr_mult': 2.5, 'trailing_start_r': 1.0, 'breakeven_trigger_r': 0.8,
        },
    })
    conf = runner.load_config()
    assert conf['trailing_atr_mult'] == pytest.approx(1.5)
    assert conf['trailing_start_r'] == pytest.approx(0.5)
    assert conf['breakeven_trigger_r'] == pytest.approx(0.8)


def test_stop_never_widens():
    state = _state()
    state["stop"] = 95.0
    actions = _apply(state, risk_model.decide(state, _snap(price=100.0, now=1000.0), CONF))
    stops = [a for a in actions if a["type"] == "stop"]
    assert stops == []


def test_stop_ratchets_after_tier_done():
    state = _state()
    levels = state["plan"]["levels"]
    state["tiers_done"] = [0]
    state["stop"] = state["plan"]["disaster_stop"]
    actions = _apply(state, risk_model.decide(state, _snap(price=levels[1] + 0.5, now=1000.0), CONF))
    stops = [a for a in actions if a["type"] == "stop"]
    assert stops and stops[0]["price"] == pytest.approx(levels[1])


def test_stop_never_lands_above_price_for_long():
    state = _state()
    # 价格已经跌破 T1：任何候选止损都必须在价格下方
    level = state["plan"]["levels"][0]
    actions = _apply(state, risk_model.decide(state, _snap(price=level - 1.0, now=1000.0), CONF))
    for act in actions:
        if act["type"] == "stop":
            assert act["price"] < level - 1.0


# ---------------------------------------------------------------------------
# 交易所 STOP 是真相源：手动撤单要补挂、手动改价要纠正账本
# ---------------------------------------------------------------------------
def _snap_with_exchange(price=100.0, exchange_stop=0.0, checked=True):
    # Snapshot 是 frozen dataclass：只能 replace，不能原地赋值
    return dataclasses.replace(
        _snap(price=price, now=1000.0),
        exchange_stop=exchange_stop, exchange_checked=checked)


def test_missing_exchange_stop_is_restored():
    """用户在币安 App 里撤掉兜底 STOP：账本还记着旧价，也必须补挂。"""
    state = _state()
    state["stop"] = 95.0  # 账本以为还有一张 95 的 STOP
    actions = _apply(state, risk_model.decide(state, _snap_with_exchange(), CONF))
    stops = [a for a in actions if a["type"] == "stop"]
    assert stops, "交易所没有保护 STOP 时必须补挂，否则等于裸仓"
    assert stops[0]["tag"] == "stop:restore"
    assert stops[0]["price"] > 0
    assert stops[0]["previous_stop"] == pytest.approx(95.0)


def test_unchecked_exchange_keeps_ledger_baseline():
    """没到核对窗口（exchange_checked=False）时行为不变，不能每轮重复挂单。"""
    state = _state()
    state["stop"] = 95.0
    actions = _apply(state, risk_model.decide(state, _snap_with_exchange(checked=False), CONF))
    assert [a for a in actions if a["type"] == "stop"] == []


def test_exchange_stop_price_wins_over_stale_ledger():
    """交易所在 96.9（比账本的 95 更优）：按交易所算推进，并把账本纠正回来。"""
    state = _state()
    state["stop"] = 95.0
    actions = _apply(state, risk_model.decide(
        state, _snap_with_exchange(exchange_stop=96.9), CONF))
    assert [a for a in actions if a["type"] == "stop"] == []
    assert state["stop"] == pytest.approx(96.9)


def test_restore_keeps_price_below_market():
    """补挂的 STOP 必须还在价格正确一侧，否则会变成立即成交的市价单。"""
    state = _state()
    state["stop"] = 99.0
    price = state["plan"]["levels"][0] - 0.5  # 已经跌破 T1
    actions = _apply(state, risk_model.decide(
        state, _snap_with_exchange(price=price), CONF))
    for act in actions:
        if act["type"] == "stop":
            assert act["price"] < price


# ---------------------------------------------------------------------------
# 周期识别
# ---------------------------------------------------------------------------
def test_new_cycle_only_on_add_not_on_reduce():
    state = _state(base=10.0, contractsn=10.0)
    assert runner._is_new_cycle(state, "long", 100.0, 8.0, 0) is False  # 减仓
    assert runner._is_new_cycle(state, "long", 100.0, 10.0, 0) is False  # 不变
    assert runner._is_new_cycle(state, "long", 100.0, 10.5, 0) is True   # 加仓


def test_new_cycle_detected_by_open_time_change():
    state = _state()
    state["opened_at_ms"] = 1_700_000_000_000
    assert runner._is_new_cycle(state, "long", 100.0, 10.0, 1_700_000_100_000) is True


# ---------------------------------------------------------------------------
# 账本：一仓一行，互不覆盖
# ---------------------------------------------------------------------------
def test_ledger_writes_are_isolated_per_position(tmp_db):
    ledger.save("BTC/USDC:USDC", "long", {"marker": "btc"})
    ledger.save("ETH/USDC:USDC", "long", {"marker": "eth"})
    ledger.save("BTC/USDC:USDC", "short", {"marker": "btc-short"})

    assert ledger.load("BTC/USDC:USDC", "long")["marker"] == "btc"
    assert ledger.load("ETH/USDC:USDC", "long")["marker"] == "eth"
    assert ledger.load("BTC/USDC:USDC", "short")["marker"] == "btc-short"

    ledger.delete("ETH/USDC:USDC", "long")
    assert ledger.load("ETH/USDC:USDC", "long") is None
    assert ledger.load("BTC/USDC:USDC", "long")["marker"] == "btc"


def test_ledger_events_are_recent_first(tmp_db):
    ledger.log_event("BTC/USDC:USDC", "long", "tier", "T1 减仓 15%", level="warning")
    ledger.log_event("ETH/USDC:USDC", "long", "tp", "TP1 止盈", level="success")
    events = ledger.recent_events(10)
    assert len(events) == 2
    assert events[0]["ts"] >= events[1]["ts"]

    only_btc = ledger.recent_events(10, symbol="BTC/USDC:USDC")
    assert len(only_btc) == 1 and only_btc[0]["kind"] == "tier"


def test_new_cycle_detected_when_reopened_while_engine_down():
    """引擎停机期间平仓又重开：开仓时间晚于账本建立时间 -> 必须换周期。"""
    state = _state()
    state["created_at"] = 1_700_000_000.0
    assert runner._is_new_cycle(state, "long", 100.0, 10.0, 1_700_003_600_000) is True
    # 账本建立后 30 秒内开仓（正常初始化路径）不换周期
    assert runner._is_new_cycle(state, "long", 100.0, 10.0, 1_700_000_030_000) is False
