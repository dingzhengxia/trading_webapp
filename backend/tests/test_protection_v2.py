"""仓位保护 v2 离线测试：风险计划 / 决策 / 账本隔离。

全部离线：不访问交易所，不读写真实 data/app.db。
"""
from __future__ import annotations

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
# 决策：止盈与保本
# ---------------------------------------------------------------------------
def test_take_profit_hits_tp1_then_tp2():
    state = _state()
    tp1, tp2, _ = state["plan"]["tp_prices"]

    actions = _apply(state, risk_model.decide(state, _snap(price=tp1 + 0.01, now=1000.0), CONF))
    assert [a["tag"] for a in actions if a["type"] == "reduce"] == ["tp:1"]
    assert actions[0]["ratio"] == pytest.approx(0.25)

    state["tp_done"] = [0]
    actions = _apply(state, risk_model.decide(state, _snap(price=tp2 + 0.01, now=1010.0), CONF))
    tp_actions = [a for a in actions if a["type"] == "reduce"]
    assert tp_actions and tp_actions[0]["tag"] == "tp:2"
    assert tp_actions[0]["ratio"] == pytest.approx(0.30)


def test_take_profit_leaves_keep_ratio_when_gapped():
    state = _state()
    tp3 = state["plan"]["tp_prices"][2]
    actions = _apply(state, risk_model.decide(state, _snap(price=tp3 + 0.01, now=1000.0), CONF))
    reduce = [a for a in actions if a["type"] == "reduce"][0]
    # 三个 TP 合计 85%，剩 15% 留给追踪止损
    assert reduce["ratio"] == pytest.approx(0.85)


def test_breakeven_stop_after_half_r():
    state = _state()
    risk = state["plan"]["risk"]
    actions = _apply(state, risk_model.decide(
        state, _snap(price=100.0 + risk * 0.6, now=1000.0), CONF))
    stops = [a for a in actions if a["type"] == "stop"]
    assert stops, "0.5R 之后必须把止损推到保本"
    assert stops[0]["price"] > 100.0


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
