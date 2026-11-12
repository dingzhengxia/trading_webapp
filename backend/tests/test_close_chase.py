"""R-P1-5 平仓让价兜底（close_price_chase_ticks）离线测试。

验收要点（ARCH_REFACTOR_PHASE3 §7 T07）：
- fake 盘口单边移动 → 连续 2 轮 0 成交后价格按 tick 让价重挂且始终 limit；
- chase 单仅出现在 reduceOnly 平仓路径；开仓路径不受影响（始终 postOnly）；
- chase=0 行为与现状一致。
"""
from __future__ import annotations

import asyncio
import types

import pytest

from app.logic.exchange_logic_async import _execute_maker_order_with_retry_async

SYMBOL = "BTC/USDC:USDC"


def _market():
    return {
        "symbol": SYMBOL,
        "limits": {"amount": {"min": 0.0001}},
        "precision": {"price": 0.5},
    }


def _chase_exchange(fill_after_rounds: int):
    """盘口单边可成交但 post-only 挂单永远不成交；第 N 张 chase 单立刻成交。

    - fetch_order_book 每次ask/bid 相同（chase 让价后可立即吃单成交）；
    - postOnly 单（首挂）永远 open；chase 单（无 postOnly 标记）按规则 closed。
    """
    exchange = types.SimpleNamespace()
    exchange.markets = {SYMBOL: _market()}
    exchange.calls = []
    exchange.amount_to_precision = lambda symbol, amount: str(round(float(amount), 8))
    exchange.price_to_precision = lambda symbol, price: str(round(float(price), 8))
    exchange.market = lambda symbol: exchange.markets.get(symbol, _market())
    exchange._counter = 0

    async def fetch_order_book(symbol, limit=5):
        exchange.calls.append(("book",))
        return {"bids": [[100.0, 10.0]], "asks": [[100.5, 10.0]]}

    async def create_order(symbol, type=None, side=None, amount=None, price=None,
                           params=None, **kwargs):
        exchange._counter += 1
        order_id = "ch-%d" % exchange._counter
        is_post_only = bool((params or {}).get("postOnly"))
        is_chase = not is_post_only
        exchange.calls.append(("create", order_id, float(price), is_chase, type))
        filled = 1.0 if (is_chase and exchange._counter > fill_after_rounds) else 0.0
        status = "closed" if filled >= 1.0 else "open"
        return {"id": order_id, "status": status, "filled": filled,
                "params": dict(params or {})}

    async def fetch_order(order_id, symbol=None, params=None):
        entry = next((c for c in exchange.calls if c[0] == "create" and c[1] == order_id), None)
        is_chase = entry[3] if entry else False
        filled = 1.0 if (is_chase and exchange._counter > fill_after_rounds) else 0.0
        return {"id": order_id, "status": "closed" if filled >= 1.0 else "open",
                "filled": filled}

    async def cancel_order(order_id, symbol=None):
        exchange.calls.append(("cancel", order_id))
        return {"id": order_id}

    exchange.fetch_order_book = fetch_order_book
    exchange.create_order = create_order
    exchange.fetch_order = fetch_order
    exchange.cancel_order = cancel_order
    return exchange


def test_close_chase_reprices_after_two_zero_fill_rounds(stop_event, async_logger, fast_sleep):
    """连续 2 轮 0 成交 → 撤单后按 tick 让价重挂；chase 单成交 → 任务成功。"""
    exchange = _chase_exchange(fill_after_rounds=1)

    ok = asyncio.run(_execute_maker_order_with_retry_async(
        exchange, SYMBOL, "sell", {"reduceOnly": True}, 1, 0, async_logger, stop_event,
        contracts_to_trade=1.0, price_chase_ticks=1,
    ))

    assert ok is True
    creates = [c for c in exchange.calls if c[0] == "create"]
    assert len(creates) >= 2, "chase 必须触发重挂"
    # 全部为 limit 且首挂 postOnly、chase 单不带 postOnly
    assert all(c[4] == "limit" for c in creates)
    assert creates[0][3] is False, "首挂保持 post-only"
    assert any(c[3] is True for c in creates), "chase 重挂单不带 postOnly"
    # 让价方向：sell 平仓首挂在 ask（100.5），向下让 1 tick → 100.0（向 bid 靠拢）
    chase_prices = [c[2] for c in creates if c[3] is True]
    assert chase_prices[0] == pytest.approx(100.0), f"sell 平仓必须向下让价: {chase_prices}"


def test_close_chase_disabled_keeps_current_behavior(stop_event, async_logger):
    """chase=0 → 与现状一致：单张 post-only 单超时撤单重试，不让价。"""
    exchange = _chase_exchange(fill_after_rounds=99)

    ok = asyncio.run(_execute_maker_order_with_retry_async(
        exchange, SYMBOL, "sell", {"reduceOnly": True}, 1, 0, async_logger, stop_event,
        contracts_to_trade=1.0, price_chase_ticks=0,
    ))

    creates = [c for c in exchange.calls if c[0] == "create"]
    assert all(c[3] is False for c in creates), "chase=0 时不得出现非 postOnly 单"
    assert ok is False, "retries=0 且永不成交 → 执行失败（与现状一致）"


def test_open_path_never_chases(stop_event, async_logger):
    """开仓路径（非 reduceOnly）不受 chase 影响：始终 postOnly。"""
    exchange = _chase_exchange(fill_after_rounds=99)

    ok = asyncio.run(_execute_maker_order_with_retry_async(
        exchange, SYMBOL, "buy", {}, 1, 0, async_logger, stop_event,
        value_to_trade=100.0, price_chase_ticks=3,
    ))

    creates = [c for c in exchange.calls if c[0] == "create"]
    assert all(c[3] is False for c in creates), "开仓一律 post-only（禁止吃单）"
    assert ok is False


def test_chase_covers_short_close_direction(stop_event, async_logger, fast_sleep):
    """平空（buy）向上让价。"""
    exchange = _chase_exchange(fill_after_rounds=1)

    ok = asyncio.run(_execute_maker_order_with_retry_async(
        exchange, SYMBOL, "buy", {"reduceOnly": True}, 1, 0, async_logger, stop_event,
        contracts_to_trade=1.0, price_chase_ticks=2,
    ))

    assert ok is True
    chase_prices = [c[2] for c in exchange.calls if c[0] == "create" and c[3] is True]
    # buy 平仓首挂在 bid（100.0），向上让 2 tick → 101.0（向 ask 靠拢）
    assert chase_prices[0] == pytest.approx(101.0), f"buy 平仓必须向上让价 2 tick: {chase_prices}"


def test_close_position_uses_chase_from_config(
    fake_exchange, async_logger, stop_event, raw_position_factory, monkeypatch,
):
    """close_position_async 从配置读取 close_price_chase_ticks 并传给执行器。"""
    captured: dict = {}
    from app.logic import exchange_logic_async as ex

    original = ex._execute_maker_order_with_retry_async

    async def spy(exchange, symbol, side, params, timeout, retries, logger, stop_event, **kwargs):
        captured.update(kwargs)
        captured["params"] = params
        return await original(exchange, symbol, side, params, timeout, retries, logger,
                              stop_event, **kwargs)

    monkeypatch.setattr(ex, "_execute_maker_order_with_retry_async", spy)

    from app.config.config import load_settings as real_load

    config = dict(real_load())
    config["close_price_chase_ticks"] = 2
    monkeypatch.setattr(ex, "load_settings", lambda: config)

    state = {"fetches": 0}

    def _positions(_symbols):
        state["fetches"] += 1
        if state["fetches"] == 1:
            return [raw_position_factory(SYMBOL, "long", 1.0, notional=100.0)]
        return []

    fake_exchange._positions = _positions
    fake_exchange._order_statuses = {"fake-1": [{"status": "closed", "filled": 1.0}]}

    ok = asyncio.run(ex.close_position_async(fake_exchange, SYMBOL, 1.0, async_logger, stop_event))
    assert ok is True
    assert captured.get("price_chase_ticks") == 2
    assert captured.get("params") == {"reduceOnly": True}
