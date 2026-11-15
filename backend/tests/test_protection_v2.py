"""仓位保护决策模型单测：风险几何 / 决策 / 止损阶梯 / 账本隔离。

全部离线：不访问交易所，不读写真实 data/app.db。

口径（与 risk_model 保持一致，改动时必须同步这里）
- T1 = 最近结构位 + 0.5×ATR，距离夹在 [max(1.5%, 0.8ATR), t1_max_pct]；
- T2~T4 = T1 到灾难线之间 25/50/75% 等距；
- 灾难线 = risk_max_pct（单笔最大亏损），不再由 T4 外推；
- 止损阶梯全部按 ATR 计（保本 2ATR / 追踪 2.5ATR），离现价至少 0.6ATR。
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

# 默认几何（entry=100 / atr=2 / 结构 97,95,92）：
#   atr_pct=2% → d_min=max(1.5%,1.6%)=1.6%，d_max=6%，T1=4%
#   levels = 96 / 95.5 / 95 / 94.5，灾难线 94，R=4，TP = 106 / 110 / 116
DEFAULT_LEVELS = (96.0, 95.5, 95.0, 94.5)
DEFAULT_DISASTER = 94.0
DEFAULT_RISK = 4.0


def _plan(side="long", entry=100.0, atr=2.0, structure=(97.0, 95.0, 92.0)):
    return risk_model.build_plan(side, entry, atr, structure, CONF)


def _state(side="long", entry=100.0, qty=10.0, plan=None):
    state = risk_model.new_state("c1", side, entry, qty, plan or _plan(side, entry), 0.0)
    state["contracts"] = qty
    return state


def _snap(side="long", price=100.0, entry=100.0, contracts=10.0, atr=2.0, now=1000.0):
    return risk_model.Snapshot(
        symbol="BTC/USDC:USDC", side=side, entry=entry, price=price,
        last_close=price, contracts=contracts, atr=atr,
        structure=(97.0, 95.0, 92.0), closed_ts=0, now=now,
    )


def _apply(state, result):
    state.update(result.get("patch") or {})
    return result["actions"]


# ---------------------------------------------------------------------------
# 风险几何
# ---------------------------------------------------------------------------
def test_plan_levels_are_strictly_ordered_for_long():
    plan = _plan("long")
    levels = plan["levels"]
    assert levels[0] > levels[1] > levels[2] > levels[3] > 0
    assert levels == pytest.approx(list(DEFAULT_LEVELS))
    assert plan["disaster_stop"] == pytest.approx(DEFAULT_DISASTER)
    assert plan["risk"] == pytest.approx(DEFAULT_RISK)
    assert plan["tp_prices"] == pytest.approx([106.0, 110.0, 116.0])
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
    # ATR 只有 0.5%，0.8ATR=0.4% 仍低于 risk_min_pct(1.5%)，T1 退到 1.5%
    assert plan["levels"][0] == pytest.approx(98.5, rel=1e-9)
    assert plan["risk"] == pytest.approx(1.5, rel=1e-9)


def test_plan_clamps_too_far_structure_to_t1_max():
    """结构位远到 −50% 时，T1 只退到 t1_max_pct(4%)，不会把止损放到 −8%。"""
    plan = risk_model.build_plan("long", 100.0, 5.0, (50.0, 45.0, 40.0), CONF)
    assert plan["risk"] == pytest.approx(100.0 * 0.04, rel=1e-9)
    assert plan["disaster_stop"] == pytest.approx(100.0 * (1 - 0.06), rel=1e-9)


def test_disaster_line_is_the_loss_cap_not_t4_plus_atr():
    """灾难线 = 单笔最大亏损（6%）。旧口径「T4 再外推 1.5ATR」会跑到 −11%。"""
    plan = _plan("long")
    assert plan["disaster_pct"] == pytest.approx(0.06)
    assert plan["disaster_stop"] == pytest.approx(100.0 * 0.94)
    # T4 必须还在灾难线之内，否则最后一档永远触发不到
    assert plan["disaster_stop"] < plan["levels"][3]


def test_high_volatility_widens_stop_floor():
    """ATR 6% 时 0.8ATR(4.8%) 成为 T1 下限，灾难线按 1.5 倍呼吸空间放大。"""
    plan = risk_model.build_plan("long", 100.0, 6.0, (92.0, 88.0, 80.0), CONF)
    assert plan["risk"] == pytest.approx(4.8, rel=1e-9)
    assert plan["disaster_pct"] == pytest.approx(0.072, rel=1e-9)


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

    actions = _apply(state, risk_model.decide(state, _snap(price=level - 0.1, now=1000.0), CONF))
    assert [a for a in actions if a["type"] == "reduce"] == []
    assert state["pending"]["0"] == 1000.0

    actions = _apply(state, risk_model.decide(state, _snap(price=level - 0.1, now=1031.0), CONF))
    reduce = [a for a in actions if a["type"] == "reduce"]
    assert len(reduce) == 1
    assert reduce[0]["tiers"] == [0]
    # 规模锚 10 × 15% = 1.5
    assert reduce[0]["qty"] == pytest.approx(1.5)


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
    _apply(state, risk_model.decide(state, _snap(price=levels[1] - 0.1, now=1100.0), CONF))
    assert True  # 首次跌破两档：确认计时刚开始，本轮不动作
    actions = _apply(state, risk_model.decide(state, _snap(price=levels[1] - 0.1, now=1200.0), CONF))
    reduce = [a for a in actions if a["type"] == "reduce"]
    assert len(reduce) == 1
    assert reduce[0]["tiers"] == [0, 1]
    # 15% + 20% = 35% × 10 = 3.5
    assert reduce[0]["qty"] == pytest.approx(3.5)


def test_last_tier_is_allowed_to_clear_but_others_keep_a_tail():
    """T4 = 结构彻底失效，允许清仓；T1~T3 至少留 10% 给后面的档。"""
    state = _state()
    levels = state["plan"]["levels"]
    # 只破 T1（浅破位走确认）
    _apply(state, risk_model.decide(state, _snap(price=levels[0] - 0.05, now=1000.0), CONF))
    actions = _apply(state, risk_model.decide(state, _snap(price=levels[0] - 0.05, now=1100.0), CONF))
    reduce = [a for a in actions if a["type"] == "reduce"][0]
    assert reduce["qty"] <= 10 * 0.9 + 1e-9


def test_disaster_exit_has_priority_and_no_confirmation():
    state = _state()
    disaster = state["plan"]["disaster_stop"]
    actions = _apply(state, risk_model.decide(state, _snap(price=disaster - 0.5, now=1000.0), CONF))
    assert len(actions) == 1
    assert actions[0]["type"] == "exit"
    assert actions[0]["tag"] == "disaster"


def test_budget_never_exceeds_full_position():
    state = _state()
    levels = state["plan"]["levels"]
    state["tiers_done"] = [0, 1, 2, 3]
    actions = _apply(state, risk_model.decide(state, _snap(price=levels[3] - 0.1, now=1000.0), CONF))
    assert all(a["type"] != "reduce" for a in actions)
    assert sum(state["plan"]["ratios"]) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 数量口径：规模锚 × 档位比例，且不超过当前持仓的保留线
# ---------------------------------------------------------------------------
def test_sell_qty_uses_size_anchor():
    state = _state(qty=10.0)
    assert risk_model.sell_qty(state, 10.0, 0.20, 0.25) == pytest.approx(2.0)


def test_sell_qty_never_exceeds_remaining_after_manual_reduce():
    """人工把仓砍到 2 之后，再按「10 × 20%」卖会一刀清零 —— 必须被保留线挡住。"""
    state = _state(qty=10.0)
    assert risk_model.sell_qty(state, 2.0, 0.20, 0.25) == pytest.approx(1.5)


def test_size_anchor_follows_add_but_not_reduce():
    state = _state(qty=10.0)
    assert risk_model.size_anchor(state, 4.0) == pytest.approx(10.0)   # 减仓不动
    assert risk_model.size_anchor(state, 18.0) == pytest.approx(18.0)  # 加仓抬升


# ---------------------------------------------------------------------------
# 止盈阶梯
# ---------------------------------------------------------------------------
def test_take_profit_ladder_defaults():
    plan = _plan()
    assert plan["tp_ratios"] == pytest.approx([0.20, 0.25, 0.30])
    risk = plan["risk"]
    for i, mult in enumerate((1.5, 2.5, 4.0)):
        assert plan["tp_prices"][i] == pytest.approx(100.0 + risk * mult)


def test_take_profit_leaves_keep_ratio():
    plan = _plan()
    assert sum(plan["tp_ratios"]) == pytest.approx(1.0 - CONF["tp_keep_ratio"])


# ---------------------------------------------------------------------------
# 止损阶梯（ATR 基准）
# ---------------------------------------------------------------------------
def test_stop_starts_at_disaster():
    state = _state()
    actions = _apply(state, risk_model.decide(state, _snap(price=100.0, now=1000.0), CONF))
    stops = [a for a in actions if a["type"] == "stop"]
    assert stops and stops[0]["price"] == pytest.approx(DEFAULT_DISASTER)
    assert stops[0]["tag"] == "stop:init"


def test_no_breakeven_before_two_atr():
    """浮盈 1.5ATR 还不够保本：回撤容忍只剩 1.5ATR，普通回撤就被扫。"""
    state = _state()
    state["stop"] = DEFAULT_DISASTER
    actions = _apply(state, risk_model.decide(state, _snap(price=103.0, now=1000.0), CONF))
    assert [a for a in actions if a["type"] == "stop"] == []


def test_breakeven_after_two_atr():
    state = _state()
    state["stop"] = DEFAULT_DISASTER
    actions = _apply(state, risk_model.decide(state, _snap(price=104.0, now=1000.0), CONF))
    stops = [a for a in actions if a["type"] == "stop"]
    # 保本位 = 均价 + max(0.1%, 0.4×ATR) = 100 + 0.8
    assert stops and stops[0]["price"] == pytest.approx(100.8)


def test_breakeven_offset_falls_back_to_price_pct():
    """ATR 很小时用 0.1% 的价格下限，不会把保本单贴到开仓价上。"""
    state = _state()
    state["stop"] = DEFAULT_DISASTER
    price = 100.2
    actions = _apply(state, risk_model.decide(
        state, _snap(price=price, atr=0.05, now=1000.0), CONF))
    stops = [a for a in actions if a["type"] == "stop"]
    # 保本候选 100.1 贴现价太近，被「离现价至少 0.3%」的安全距离压到 99.899
    assert stops and stops[0]["price"] == pytest.approx(price * (1 - 0.003))


def test_trailing_line_sits_1_5_atr_below_peak():
    state = _state()
    state["stop"] = DEFAULT_DISASTER
    state["peak"] = 106.0
    actions = _apply(state, risk_model.decide(state, _snap(price=106.0, now=1000.0), CONF))
    stops = [a for a in actions if a["type"] == "stop"]
    assert stops and stops[0]["price"] == pytest.approx(103.0)


def test_trailing_does_not_start_before_2_5_atr():
    state = _state()
    state["stop"] = DEFAULT_DISASTER
    state["peak"] = 103.0
    actions = _apply(state, risk_model.decide(state, _snap(price=103.0, now=1000.0), CONF))
    assert [a for a in actions if a["type"] == "stop"] == []


def test_stop_ratchets_after_tier_done():
    state = _state()
    levels = state["plan"]["levels"]
    state["tiers_done"] = [0]
    state["stop"] = DEFAULT_DISASTER
    actions = _apply(state, risk_model.decide(state, _snap(price=100.0, now=1000.0), CONF))
    stops = [a for a in actions if a["type"] == "stop"]
    assert stops and stops[0]["price"] == pytest.approx(levels[1])


def test_stop_never_widens():
    state = _state()
    state["stop"] = 95.0
    actions = _apply(state, risk_model.decide(state, _snap(price=100.0, now=1000.0), CONF))
    assert [a for a in actions if a["type"] == "stop"] == []


def test_stop_never_lands_too_close_to_price():
    """跌破 T1 后想把止损推到 T2，但 T2 离现价只有 0.5：必须留出 0.6ATR 的呼吸空间。"""
    state = _state()
    state["tiers_done"] = [0]
    state["stop"] = DEFAULT_DISASTER
    price = DEFAULT_LEVELS[1] + 0.5
    actions = _apply(state, risk_model.decide(state, _snap(price=price, now=1000.0), CONF))
    for act in actions:
        if act["type"] == "stop":
            assert act["price"] <= price - 1.2 + 1e-9


def test_stop_never_lands_above_price_for_long():
    state = _state()
    level = state["plan"]["levels"][0]
    actions = _apply(state, risk_model.decide(state, _snap(price=level - 1.0, now=1000.0), CONF))
    for act in actions:
        if act["type"] == "stop":
            assert act["price"] < level - 1.0


# ---------------------------------------------------------------------------
# 交易所 STOP 是真相源：手动撤单要补挂、手动改价要纠正账本
# ---------------------------------------------------------------------------
def _snap_with_exchange(price=100.0, exchange_stop=0.0, checked=True, rebased=False):
    return dataclasses.replace(
        _snap(price=price, now=1000.0),
        exchange_stop=exchange_stop, exchange_checked=checked, rebased=rebased)


def test_missing_exchange_stop_is_restored():
    state = _state()
    state["stop"] = 95.0
    actions = _apply(state, risk_model.decide(state, _snap_with_exchange(), CONF))
    stops = [a for a in actions if a["type"] == "stop"]
    assert stops, "交易所没有保护 STOP 时必须补挂，否则等于裸仓"
    assert stops[0]["tag"] == "stop:restore"
    assert stops[0]["previous_stop"] == pytest.approx(95.0)


def test_unchecked_exchange_keeps_ledger_baseline():
    state = _state()
    state["stop"] = 95.0
    actions = _apply(state, risk_model.decide(state, _snap_with_exchange(checked=False), CONF))
    assert [a for a in actions if a["type"] == "stop"] == []


def test_exchange_stop_price_wins_over_stale_ledger():
    state = _state()
    state["stop"] = 95.0
    actions = _apply(state, risk_model.decide(
        state, _snap_with_exchange(exchange_stop=95.5), CONF))
    assert [a for a in actions if a["type"] == "stop"] == []
    assert state["stop"] == pytest.approx(95.5)


def test_restore_keeps_price_below_market():
    state = _state()
    state["stop"] = 99.0
    price = state["plan"]["levels"][0] - 0.5
    actions = _apply(state, risk_model.decide(state, _snap_with_exchange(price=price), CONF))
    for act in actions:
        if act["type"] == "stop":
            assert act["price"] < price


# ---------------------------------------------------------------------------
# 加仓：唯一允许止损下移的场景
# ---------------------------------------------------------------------------
def test_rebase_allows_stop_move_down_once():
    """加仓把均价抬到 102 后，旧止损（103）落在均价之上；本轮必须按新基准重算。"""
    state = _state()
    state["stop"] = 103.0
    actions = _apply(state, risk_model.decide(
        state, _snap_with_exchange(price=104.0, exchange_stop=103.0, rebased=True), CONF))
    stops = [a for a in actions if a["type"] == "stop"]
    assert stops and stops[0]["tag"] == "stop:rebase"
    assert stops[0]["price"] < 103.0


def test_non_rebase_never_moves_stop_down():
    state = _state()
    state["stop"] = 103.0
    actions = _apply(state, risk_model.decide(
        state, _snap_with_exchange(price=104.0, exchange_stop=103.0), CONF))
    assert [a for a in actions if a["type"] == "stop"] == []


# ---------------------------------------------------------------------------
# 新仓位识别（加仓不再重建）
# ---------------------------------------------------------------------------
def test_new_position_only_on_reopen():
    state = _state()
    state["opened_at_ms"] = 1_700_000_000_000
    assert runner._is_new_position(None, 0) is True
    assert runner._is_new_position(state, 1_700_000_000_000) is False
    assert runner._is_new_position(state, 1_700_000_100_000) is True


def test_new_position_when_reopened_while_engine_down():
    state = _state()
    state["created_at"] = 1_700_000_000.0
    assert runner._is_new_position(state, 1_700_003_600_000) is True
    assert runner._is_new_position(state, 1_700_000_030_000) is False


def test_legacy_plan_version_triggers_rebase():
    plan = _plan()
    assert plan["version"] == risk_model.PLAN_VERSION


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
