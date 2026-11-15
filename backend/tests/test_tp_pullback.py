"""止盈触发口径：程序每轮判断「先突破、再回落」，不往交易所预挂卖单。

用户口径（2026-11-15）：
「比如 100，要超过 100 以后，跌回 100 才止盈，而不是直接挂在 100 啊」
「要不然需要程序每三秒执行一次干什么？」

所以决策层必须区分两种「碰到 TP」：
- 只是触碰（插针到 100 / 从下方上来第一根摸到）：不许卖，继续等；
- 真突破（≥ TP×(1+缓冲)）之后又回到 100：这一档才卖。
"""
from __future__ import annotations

import pytest

from app.protection import risk_model

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


def _run(state, price, now=1000.0, side="long", conf=None):
    result = risk_model.decide(state, _snap(side=side, price=price, now=now), conf or CONF)
    state.update(result.get("patch") or {})
    return [a for a in result["actions"] if a.get("tps")]


def test_touch_without_breakout_does_not_sell():
    """价格只是「够到」TP1（等于 TP 价）：不算突破，不卖。"""
    state = _state()
    tp1 = state["plan"]["tp_prices"][0]
    assert _run(state, tp1) == []
    assert state.get("tp_armed") in (None, []), "触碰不算突破，不该登记"


def test_breakout_only_arms_and_sells_on_pullback():
    """先越过 TP1+缓冲 → 只登记；价格回到 TP1 才卖 TP1。"""
    state = _state()
    tp1 = state["plan"]["tp_prices"][0]
    confirm = risk_model.tp_breakout_price(tp1, "long", CONF)
    assert confirm > tp1

    acts = _run(state, confirm + 0.01, now=1000.0)
    assert acts == [], "刚突破那一轮只登记，不立刻卖"
    assert state["tp_armed"] == [0]

    acts = _run(state, confirm + 0.5, now=1003.0)
    assert acts == [], "还在高位，不卖"

    acts = _run(state, tp1, now=1006.0)
    assert len(acts) == 1
    assert acts[0]["tps"] == [0]
    assert acts[0]["ratio"] == pytest.approx(state["plan"]["tp_ratios"][0])
    assert "回落" in acts[0]["reason"]


def test_pullback_below_tp_still_sells():
    """回落穿过 TP1 才被这一轮看到（价格已低于 TP1）：同样触发，不能漏。"""
    state = _state()
    tp1 = state["plan"]["tp_prices"][0]
    _run(state, tp1 * 1.02, now=1000.0)
    acts = _run(state, tp1 * 0.995, now=1003.0)
    assert acts and acts[0]["tps"] == [0]


def test_breakout_is_sticky_after_price_falls_back_without_fill():
    """突破过就记住（tp_armed），下一轮仍在 TP 下方时继续按回落处理。"""
    state = _state()
    tp1 = state["plan"]["tp_prices"][0]
    _run(state, tp1 * 1.02, now=1000.0)
    assert state["tp_armed"] == [0]
    # 模拟「这一轮减仓没成交」：tp_done 没变，armed 必须保留
    assert _run(state, tp1 * 0.99, now=1003.0)[0]["tps"] == [0]
    assert state["tp_armed"] == [0]


def test_only_one_level_per_round_and_highest_first():
    """一口气越过三档后跌穿：一轮只卖一档，且先卖离价格最近的高档。

    先卖 TP1 等于「价格已经低于 TP2/TP3 了还按 TP1 处理」，等于把高位那两档贱卖。
    """
    state = _state()
    tp3 = state["plan"]["tp_prices"][2]
    _run(state, tp3 * 1.01, now=1000.0)
    assert state["tp_armed"] == [0, 1, 2]
    acts = _run(state, state["plan"]["tp_prices"][0], now=1003.0)
    assert len(acts) == 1
    assert acts[0]["tps"] == [2]


def test_ladder_progresses_level_by_level():
    """TP1 完成后，TP2 必须自己重新「突破 → 回落」，不继承上一档的状态。"""
    state = _state()
    prices = state["plan"]["tp_prices"]
    _run(state, prices[0] * 1.02, now=1000.0)
    state["tp_done"] = [0]
    # TP2 还没突破：价格即使已经低于 TP2 也不该卖
    assert _run(state, prices[1] * 0.98, now=1003.0) == []
    _run(state, prices[1] * 1.02, now=1006.0)
    acts = _run(state, prices[1] * 0.999, now=1009.0)
    assert acts and acts[0]["tps"] == [1]


def test_short_side_mirrors_long():
    """空单：先跌破 TP（含缓冲）算突破，涨回 TP 才止盈。"""
    plan = _plan("short", structure=(103.0, 105.0, 108.0))
    state = _state(side="short", plan=plan)
    tp1 = plan["tp_prices"][0]
    assert _run(state, tp1, side="short") == []
    _run(state, tp1 * 0.98, now=1000.0, side="short")
    acts = _run(state, tp1, now=1003.0, side="short")
    assert acts and acts[0]["tps"] == [0]


def test_breakout_buffer_is_configurable():
    """缓冲调大 → 同样的价格不再算突破。"""
    state = _state()
    tp1 = state["plan"]["tp_prices"][0]
    conf = dict(CONF, tp_breakout_confirm_pct=0.02)
    assert _run(state, tp1 * 1.005, conf=conf) == []
    assert not state.get("tp_armed")


def test_no_tp_action_when_structure_breach_pending():
    """同一轮既有结构破位又有止盈回落：只出结构动作，避免一轮两刀。"""
    state = _state()
    tp1 = state["plan"]["tp_prices"][0]
    _run(state, tp1 * 1.02, now=1000.0)
    t1 = state["plan"]["levels"][0]
    # 结构破位确认秒数很高时不会立即触发；直接把 T1 标记为已确认路径
    state["pending"] = {str(0): 0.0}
    conf = dict(CONF)
    conf["tier_confirm_sec"] = [0, 0, 0, 0]
    result = risk_model.decide(state, _snap(price=t1 - 0.5, now=1010.0), conf)
    acts = result["actions"]
    tiers = [a for a in acts if a.get("tiers")]
    tps = [a for a in acts if a.get("tps")]
    assert tiers and not tps, "结构破位优先，止盈下一轮再说"
