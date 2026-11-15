# tests/test_tp_passive.py
"""止盈被动挂单：单子提前挂在交易所（post-only），引擎全程不吃单。

2026-11-15 第二次改版推翻了两天前的「到价即走（吃单）」：
- 决策层不再产生止盈减仓动作（见 test_breach_depth_tp_limiter / test_protection_v2）；
- 挂单层在 runner._ensure_tp_orders / tp_orders.py，价格到档由交易所撮合。

这里锁住四条硬约束：
1. 挂单价永远落在被动侧（多单 >= 卖一、空单 <= 买一），配合 GTX 就不可能吃单；
2. 挂单参数必须是 reduceOnly + GTX(post-only)；
3. post-only 被拒（价格刚穿过 TP）→ 用最新盘口重挂，绝不打市价；
4. 数量 = 初始仓位×档位比例，且不超过当前剩余的 tp_slice_cap。
"""
from __future__ import annotations

import asyncio
import dataclasses
import dataclasses
import inspect

import pytest

from app.core import database
from app.protection import ledger, risk_model, runner, tp_orders

CONF = dict(risk_model.V2_DEFAULTS)
SYMBOL = "BTC/USDC:USDC"


# ---------------------------------------------------------------------------
# 纯计算：挂单价 / 数量 / 下一档
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "side,tp,bid,ask,expected",
    [
        # 价格还没到 TP：挂在 TP 价（多单在卖一之上排队等涨）
        ("long", 110.0, 99.0, 100.0, 110.0),
        # 价格已经越过 TP：跟到卖一（被动侧），不回落压价
        ("long", 95.0, 99.0, 100.0, 100.0),
        # 没有盘口：退回 TP 价，交给 GTX 兜底（会被拒单，下轮重试）
        ("long", 95.0, 0.0, 0.0, 95.0),
        # 空单对称：未到价挂 TP（买一之下），已越过挂买一
        ("short", 90.0, 100.0, 101.0, 90.0),
        ("short", 105.0, 100.0, 101.0, 100.0),
    ],
)
def test_tp_limit_price_always_stays_passive(side, tp, bid, ask, expected):
    price = risk_model.tp_limit_price(side, tp, bid, ask)
    assert price == pytest.approx(expected)
    if ask > 0:
        # 卖单挂价必须 >= 卖一、买单挂价必须 <= 买一，否则会主动成交（taker）
        if side == "long":
            assert price >= ask
        else:
            assert price <= bid


def test_tp_order_qty_uses_initial_base():
    state = {"base_contracts": 10.0}
    plan = {"tp_ratios": [0.20, 0.25, 0.30]}
    assert risk_model.tp_order_qty(state, plan, 10.0, 0, CONF) == pytest.approx(2.0)
    assert risk_model.tp_order_qty(state, plan, 10.0, 2, CONF) == pytest.approx(3.0)


def test_tp_order_qty_capped_by_remaining():
    """结构减仓砍到只剩 1.0：TP1 标称 2.0，但单档上限 50% → 只卖 0.5。

    这就是 2026-11-15 BTC「标称减 25%、实际砍掉剩余 79%」的护栏：
    分母仍是初始仓位，但任何一档都不能超过「现在还剩多少的一半」。
    """
    state = {"base_contracts": 10.0}
    plan = {"tp_ratios": [0.20, 0.25, 0.30]}
    qty = risk_model.tp_order_qty(state, plan, 1.0, 0, CONF)
    assert qty == pytest.approx(0.5)


def test_tp_slice_cap_is_configurable():
    state = {"base_contracts": 10.0}
    plan = {"tp_ratios": [0.20, 0.25, 0.30]}
    conf = dict(CONF, tp_slice_cap=0.2)
    assert risk_model.tp_order_qty(state, plan, 1.0, 0, conf) == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# 挂单动作：参数必须 post-only，拒单改贴盘口
# ---------------------------------------------------------------------------
class FakeExchange:
    def amount_to_precision(self, symbol, qty):
        return f"{float(qty):.6f}"

    def price_to_precision(self, symbol, price):
        return f"{float(price):.2f}"


def _plan(side="long", entry=100.0, atr=2.0, structure=(97.0, 95.0, 92.0)):
    return risk_model.build_plan(side, entry, atr, structure, CONF)


def _bundle(price=100.0, contracts=10.0, side="long"):
    plan = _plan(side)
    state = risk_model.new_state("c1", side, 100.0, contracts, plan, 0.0)
    snap = risk_model.Snapshot(
        symbol=SYMBOL, side=side, entry=100.0, price=price, last_close=price,
        contracts=contracts, base_contracts=contracts, atr=2.0,
        structure=(97.0, 95.0, 92.0), closed_ts=0, now=1000.0)
    return {"symbol": SYMBOL, "side": side, "state": state, "snap": snap,
            "pos": {"contracts": contracts, "side": side}, "actions": []}


def _patch_ticker(monkeypatch, book):
    """book: [(bid, ask), ...]，逐次取，用尽后停在最后一组。"""
    calls = {"n": 0}

    async def fake_ticker(exchange, symbol, conf, priority="LOW", force=False):
        idx = min(calls["n"], len(book) - 1)
        calls["n"] += 1
        bid, ask = book[idx]
        return {"bid": bid, "ask": ask, "last": (bid + ask) / 2.0}

    monkeypatch.setattr(runner.engine, "_fetch_ticker", fake_ticker)
    return calls


def _patch_rest(monkeypatch, fail_first=0):
    record = {"orders": [], "canceled": [], "fail": fail_first}

    async def fake_rest(exchange, method_name, *args, priority="NORMAL", conf=None, **kwargs):
        if method_name == "create_limit_order":
            if record["fail"] > 0:
                record["fail"] -= 1
                raise Exception("binance -5022: could not be executed as maker, "
                                "the post only order will be rejected")
            symbol, side, qty, price = args
            record["orders"].append({"side": side, "qty": float(qty),
                                     "price": float(price),
                                     "params": dict(kwargs.get("params") or {})})
            return {"id": f"tp{len(record['orders'])}"}
        if method_name == "fetch_order":
            order_id, symbol = args
            return {"id": order_id, "status": "open", "filled": 0.0, "amount": 2.0}
        if method_name == "cancel_order":
            record["canceled"].append(args[0])
            return {}
        raise AssertionError(f"未预期的 REST 调用: {method_name}")

    monkeypatch.setattr(tp_orders, "_rest", fake_rest)
    return record


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "USER_SETTINGS_FILE", tmp_path / "user_settings.json")
    monkeypatch.setattr(database, "COIN_LISTS_FILE", tmp_path / "coin_lists.json")
    database.init_db()
    monkeypatch.setattr(runner, "send_alert", lambda *a, **k: None)
    return tmp_path


def _run(coro):
    return asyncio.run(coro)


def test_place_order_is_post_only_reduce_only(tmp_db, monkeypatch):
    """挂单参数必须是 reduceOnly + GTX；价格未到 TP 时挂在 TP 价。"""
    _patch_ticker(monkeypatch, [(99.0, 100.0)])
    record = _patch_rest(monkeypatch)
    bundle = _bundle(price=100.0)

    _run(runner._ensure_tp_orders(FakeExchange(), CONF, bundle))

    assert len(record["orders"]) == 1
    order = record["orders"][0]
    assert order["side"] == "sell", "多单止盈是卖单"
    assert order["params"]["reduceOnly"] is True
    assert order["params"]["timeInForce"] == "GTX", "必须是 post-only"
    tp1 = bundle["state"]["plan"]["tp_prices"][0]
    assert order["price"] == pytest.approx(round(tp1, 2))
    assert order["price"] > 100.0, "挂在卖一之上，不会主动成交"
    assert bundle["state"]["tp_order"]["level"] == 0


def test_post_only_reject_reprices_to_passive_side(tmp_db, monkeypatch):
    """价格刚穿过 TP（GTX 会被拒）：改挂卖一继续被动排队，绝不吃单。"""
    # 第一次盘口还在 TP 下方（挂 TP 价，被拒）；第二次盘口已跑上去（改挂卖一）
    _patch_ticker(monkeypatch, [(99.0, 100.0), (120.0, 120.5)])
    record = _patch_rest(monkeypatch, fail_first=1)
    bundle = _bundle(price=125.0)

    _run(runner._ensure_tp_orders(FakeExchange(), CONF, bundle))

    assert len(record["orders"]) == 1
    assert record["orders"][0]["price"] == pytest.approx(120.5)
    assert record["orders"][0]["params"]["timeInForce"] == "GTX"


def test_second_reject_gives_up_for_this_round(tmp_db, monkeypatch):
    """连续被拒：本轮放弃（下一轮再来），不会退化成吃单。"""
    _patch_ticker(monkeypatch, [(120.0, 120.5)])
    record = _patch_rest(monkeypatch, fail_first=2)
    bundle = _bundle(price=125.0)

    _run(runner._ensure_tp_orders(FakeExchange(), CONF, bundle))

    assert record["orders"] == []
    assert "tp_order" not in bundle["state"]


def test_only_one_level_armed_at_a_time(tmp_db, monkeypatch):
    """已有在挂单就不再挂第二档：插针只会卖掉当前这一档。"""
    _patch_ticker(monkeypatch, [(99.0, 100.0)])
    record = _patch_rest(monkeypatch)
    bundle = _bundle(price=100.0)
    bundle["state"]["tp_order"] = {
        "id": "tp1", "level": 0, "price": 120.0, "qty": 2.0,
        "ts": 999.0, "checked_at": 999.0,
    }

    async def fake_fetch(exchange, symbol, order_id, conf):
        return {"id": order_id, "status": "open", "filled": 0.0, "amount": 2.0}

    monkeypatch.setattr(tp_orders, "fetch_tp_order", fake_fetch)

    _run(runner._ensure_tp_orders(FakeExchange(), CONF, bundle))

    assert record["orders"] == [], "已经有一档在挂，不应该再挂"


def test_fill_marks_level_done_and_arms_next(tmp_db, monkeypatch):
    """TP1 成交：标记 tp_done、清挂单记录，并在同一轮挂出 TP2。"""
    _patch_ticker(monkeypatch, [(130.0, 130.5)])
    record = _patch_rest(monkeypatch)
    bundle = _bundle(price=131.0)
    bundle["state"]["tp_order"] = {
        "id": "tp1", "level": 0, "price": 120.0, "qty": 2.0,
        "ts": 0.0, "checked_at": 0.0,
    }

    async def fake_fetch(exchange, symbol, order_id, conf):
        return {"id": order_id, "status": "closed", "filled": 2.0,
                "amount": 2.0, "average": 120.0}

    monkeypatch.setattr(tp_orders, "fetch_tp_order", fake_fetch)

    _run(runner._ensure_tp_orders(FakeExchange(), CONF, bundle))

    assert bundle["state"]["tp_done"] == [0]
    assert bundle["state"]["tp_order"]["level"] == 1
    assert len(record["orders"]) == 1
    # 价格已在 TP2 之上：新单跟到卖一（130.5），但仍不劣于 TP2 的目标价
    tp2 = bundle["state"]["plan"]["tp_prices"][1]
    assert record["orders"][0]["price"] >= tp2
    assert record["orders"][0]["price"] == pytest.approx(130.5)
    events = ledger.recent_events(limit=20, symbol=SYMBOL)
    assert any(e.get("kind") == "tp_fill" for e in events)


def test_stale_qty_is_cancelled_and_rearmed(tmp_db, monkeypatch):
    """仓位被结构减仓砍小：旧挂单数量不再匹配 → 撤单，并按新仓位重挂。"""
    _patch_ticker(monkeypatch, [(99.0, 100.0)])
    record = _patch_rest(monkeypatch)
    bundle = _bundle(price=100.0, contracts=10.0)
    bundle["snap"] = dataclasses.replace(bundle["snap"], contracts=2.0)
    bundle["state"]["tp_order"] = {
        "id": "tp1", "level": 0, "price": 120.0, "qty": 2.0,
        "ts": 0.0, "checked_at": 0.0,
    }

    _run(runner._ensure_tp_orders(FakeExchange(), CONF, bundle))

    assert record["canceled"] == ["tp1"]
    assert len(record["orders"]) == 1
    # min(10×20%, 2×50%) = 1.0：单档上限保证不会一刀清零
    assert record["orders"][0]["qty"] == pytest.approx(1.0)


def test_new_cycle_sweeps_old_tp_orders(tmp_db, monkeypatch):
    """新周期第一轮：先扫掉交易所上残留的旧止盈单，避免两张单互相抵消。"""
    _patch_ticker(monkeypatch, [(99.0, 100.0)])
    record = _patch_rest(monkeypatch)
    open_orders = [{"id": "old", "clientOrderId": "PM_WS_TP_BTCUSDCUSDC_L0_abcdef",
                    "side": "sell", "type": "limit"}]

    async def fake_rest(exchange, method_name, *args, priority="NORMAL", conf=None, **kwargs):
        if method_name == "fetch_open_orders":
            return open_orders
        if method_name == "cancel_order":
            record["canceled"].append(args[0])
            return {}
        if method_name == "create_limit_order":
            symbol, side, qty, price = args
            record["orders"].append({"qty": float(qty), "price": float(price),
                                     "params": dict(kwargs.get("params") or {})})
            return {"id": "new"}
        raise AssertionError(f"未预期的 REST 调用: {method_name}")

    monkeypatch.setattr(tp_orders, "_rest", fake_rest)
    bundle = _bundle(price=100.0)
    bundle["state"]["tp_sweep_pending"] = True

    _run(runner._ensure_tp_orders(FakeExchange(), CONF, bundle))

    assert record["canceled"] == ["old"]
    assert len(record["orders"]) == 1, "清理完旧单后要挂上当前档"


def test_no_market_order_in_tp_path():
    """静态护栏：止盈链路里不允许出现市价/吃价调用（唯一例外是 exits 的紧急全平）。"""
    for func in (runner._ensure_tp_orders, runner._place_next_tp_order,
                 runner._verify_tp_order, runner._settle_tp_fill):
        src = inspect.getsource(func)
        assert "create_market_order" not in src
        assert "_market_reduce" not in src
        assert "marketable" not in src
    assert "create_market_order" not in inspect.getsource(tp_orders)
