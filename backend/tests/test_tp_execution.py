"""止盈执行口径：到价即走（吃单），不挂 maker 死等。

2026-11-15 BTC 实盘：TP1 目标 65,504，价格早已站上去过，但减仓走的是 maker 优先
（GTX 挂在卖一价），行情一回落就不成交，10s 撤单重挂更低的卖一价，最后拖到价格
回落到 65,5xx 才成交 —— 用户看到的就是「才回调一点就减仓」。这里锁住两个行为：
1. skip_maker=True 时第一级 maker 完全不执行，直接吃单（挂 bid）；
2. skip_maker=False 时行为不变（挂 ask + GTX），结构破位减仓继续享受 maker 返佣。
"""
import asyncio

import pytest

from app.protection import exits


class FakeExchange:
    def amount_to_precision(self, symbol, qty):
        return f"{float(qty):.3f}"

    def price_to_precision(self, symbol, price):
        return f"{float(price):.1f}"


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def calls(monkeypatch):
    """替换 REST 与 ticker，记录每一笔下单的价位与参数。"""
    record = {"orders": [], "canceled": []}

    async def fake_rest(exchange, method_name, *args, **kwargs):
        if method_name == "create_limit_order":
            symbol, side, qty, price = args
            record["orders"].append({"side": side, "qty": qty, "price": float(price),
                                     "params": dict(kwargs.get("params") or {})})
            return {"id": f"o{len(record['orders'])}"}
        if method_name == "fetch_order":
            order_id, symbol = args
            # 直接成交，让循环在第一轮就结束
            return {"status": "CLOSED", "filled": 1e9, "id": order_id}
        if method_name == "cancel_order":
            record["canceled"].append(args[0])
            return {}
        raise AssertionError(f"未预期的 REST 调用: {method_name}")

    async def fake_ticker(exchange, symbol, conf, priority="NORMAL", force=False):
        return {"ask": 100.5, "bid": 99.5, "last": 100.0, "close": 100.0}

    async def fake_fresh(exchange, symbol, side, conf, priority="NORMAL"):
        return {"contracts": 0.75, "side": side}

    monkeypatch.setattr(exits, "_rest", fake_rest)
    monkeypatch.setattr(exits, "_fetch_ticker", fake_ticker)
    monkeypatch.setattr(exits, "_position_fresh", fake_fresh)
    return record


def _position():
    return {"contracts": 1.0, "side": "long"}


def _call(**kwargs):
    return exits._limit_reduce_with_maker_retry(
        FakeExchange(), "BTC/USDC:USDC", "long", _position(), 0.25,
        "分批止盈 TP1", {}, 1, {"position_version": 1},
        max_retries=3, check_interval_sec=0.0, timeout_sec=0.5,
        marketable_retries=1, allow_market_fallback=True,
        maker_only=True, **kwargs,
    )


def test_taker_first_skips_maker_and_crosses_spread(calls):
    """skip_maker=True：直接挂 bid 吃单，不带 GTX。"""
    _run(_call(skip_maker=True))

    assert len(calls["orders"]) == 1
    order = calls["orders"][0]
    assert order["price"] == pytest.approx(99.5), "卖单必须挂 bid（对手价）才能立即成交"
    assert "timeInForce" not in order["params"], "吃单不能带 GTX（会被拒）"
    assert order["params"].get("reduceOnly") is True


def test_maker_path_unchanged(calls):
    """默认路径不变：先挂 ask + GTX，成交即结束。"""
    _run(_call(skip_maker=False))

    assert len(calls["orders"]) == 1
    order = calls["orders"][0]
    assert order["price"] == pytest.approx(100.5), "maker 卖单挂在卖一价"
    assert order["params"].get("timeInForce") == "GTX"


def test_tp_target_note_reads_plan():
    from app.protection.runner import _tp_target_note

    state = {"plan": {"tp_prices": [65504.12, 66472.16, 67440.20]}}
    assert _tp_target_note(state, {"tps": [0]}) == "，目标 TP1 65504.1"
    assert _tp_target_note(state, {"tps": [1]}) == "，目标 TP2 66472.2"
    assert _tp_target_note(state, {"tiers": [0]}) == ""
    assert _tp_target_note({"plan": {}}, {"tps": [0]}) == ""


def test_tp_defaults_are_taker_and_relative_to_remaining():
    """默认值护栏：止盈必须吃单、按剩余仓位减，避免回退成「maker 死等 + 一刀清零」。"""
    from app.protection.risk_model import V2_DEFAULTS

    assert V2_DEFAULTS["tp_taker_first"] is True
    assert V2_DEFAULTS["tp_reduce_by_remaining"] is True
