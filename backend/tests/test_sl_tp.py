"""Offline acceptance tests: fixed SL/TP and trailing-stop condition orders.

Contract: report 2 (P0-1), 3.2, 5.3.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

import app.logic.sl_tp_logic_async as sl_tp_module
from app.logic.sl_tp_logic_async import set_tp_sl_for_position_async

CONFIG = {
    "leverage": 20,
    "enable_long_sl_tp": True,
    "long_stop_loss_percentage": 50.0,
    "long_take_profit_percentage": 100.0,
    "enable_long_trailing_stop": False,
    "long_trailing_stop_callback_rate": 1.0,
    "enable_short_sl_tp": True,
    "short_stop_loss_percentage": 80.0,
    "short_take_profit_percentage": 150.0,
    "enable_short_trailing_stop": False,
    "short_trailing_stop_callback_rate": 1.0,
}


def _run(coro):
    return asyncio.run(coro)


def _trigger_price(call):
    params = call.get("params") or {}
    for key in ("stopPrice", "takeProfitPrice", "triggerPrice"):
        value = params.get(key)
        if value is not None:
            return float(value)
    if call.get("price") is not None:
        return float(call["price"])
    return None


def _calls_of_type(calls, order_type):
    return [call for call in calls if str(call.get("type", "")).upper() == order_type]


def test_fixed_mode_places_stop_and_take_profit_for_long(
    fake_exchange, async_logger, stop_event, position_factory, fast_sleep,
):
    position = position_factory("BTC", "BTC/USDC:USDC", "long", contracts=1.0, entry_price=100.0)

    _run(set_tp_sl_for_position_async(fake_exchange, position, CONFIG, async_logger, stop_event))

    calls = fake_exchange.create_order_calls
    stop_calls = _calls_of_type(calls, "STOP_MARKET")
    tp_calls = _calls_of_type(calls, "TAKE_PROFIT_MARKET")
    assert stop_calls, "missing STOP_MARKET: %r" % (calls,)
    assert tp_calls, "missing TAKE_PROFIT_MARKET (P0-1: take-profit was never submitted): %r" % (calls,)

    for call in stop_calls + tp_calls:
        assert (call["params"] or {}).get("reduceOnly") is True
        assert (call["params"] or {}).get("workingType") == "MARK_PRICE"
        assert str(call["side"]).lower() == "sell"
        assert float(call["amount"]) == pytest.approx(1.0)

    # entry=100, leverage=20, sl=50% -> 100*(1-0.5/20)=97.5 ; tp=100% -> 100*(1+1.0/20)=105.0
    assert _trigger_price(stop_calls[0]) == pytest.approx(97.5, rel=1e-6)
    assert _trigger_price(tp_calls[0]) == pytest.approx(105.0, rel=1e-6)


def test_fixed_mode_places_stop_and_take_profit_for_short(
    fake_exchange, async_logger, stop_event, position_factory, fast_sleep,
):
    position = position_factory("ETH", "ETH/USDT:USDT", "short", contracts=2.0, entry_price=100.0)

    _run(set_tp_sl_for_position_async(fake_exchange, position, CONFIG, async_logger, stop_event))

    calls = fake_exchange.create_order_calls
    stop_calls = _calls_of_type(calls, "STOP_MARKET")
    tp_calls = _calls_of_type(calls, "TAKE_PROFIT_MARKET")
    assert stop_calls and tp_calls

    for call in stop_calls + tp_calls:
        assert (call["params"] or {}).get("reduceOnly") is True
        assert str(call["side"]).lower() == "buy"
        assert float(call["amount"]) == pytest.approx(2.0)

    # entry=100, leverage=20, sl=80% -> 100*(1+0.8/20)=104.0 ; tp=150% -> 100*(1-1.5/20)=92.5
    assert _trigger_price(stop_calls[0]) == pytest.approx(104.0, rel=1e-6)
    assert _trigger_price(tp_calls[0]) == pytest.approx(92.5, rel=1e-6)


def test_no_condition_orders_when_sl_tp_disabled(
    fake_exchange, async_logger, stop_event, position_factory, fast_sleep,
):
    config = dict(CONFIG, enable_long_sl_tp=False, enable_long_trailing_stop=False)
    position = position_factory("BTC", "BTC/USDC:USDC", "long", contracts=1.0, entry_price=100.0)

    _run(set_tp_sl_for_position_async(fake_exchange, position, config, async_logger, stop_event))

    assert fake_exchange.create_order_calls == []


def test_trailing_mode_places_trailing_stop_only(
    fake_exchange, async_logger, stop_event, position_factory, fast_sleep,
):
    config = dict(CONFIG, enable_long_trailing_stop=True, long_trailing_stop_callback_rate=1.0)
    position = position_factory("BTC", "BTC/USDC:USDC", "long", contracts=1.0, entry_price=100.0)

    _run(set_tp_sl_for_position_async(fake_exchange, position, config, async_logger, stop_event))

    calls = fake_exchange.create_order_calls
    trailing_calls = [call for call in calls if "TRAILING" in str(call.get("type", "")).upper()]
    assert trailing_calls, "expected TRAILING_STOP_MARKET: %r" % (calls,)
    for call in trailing_calls:
        assert (call["params"] or {}).get("reduceOnly") is True
        assert str(call["side"]).lower() == "sell"
        assert "callbackRate" in (call["params"] or {})
    assert not _calls_of_type(calls, "STOP_MARKET")
    assert not _calls_of_type(calls, "TAKE_PROFIT_MARKET")


def test_orphan_cleanup_is_implemented_or_removed():
    """P0-6: no 'pass' shell allowed; if present it must have a real body."""
    if not hasattr(sl_tp_module, "cleanup_orphan_sltp_orders_async"):
        return  # allowed alternative: the function and its call-site were removed
    import ast

    source = inspect.getsource(sl_tp_module.cleanup_orphan_sltp_orders_async)
    tree = ast.parse(source.strip().lstrip("@"))
    function = tree.body[0]
    body_nodes = [node for node in function.body if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))]
    assert not (len(body_nodes) == 1 and isinstance(body_nodes[0], ast.Pass)), (
        "cleanup_orphan_sltp_orders_async is still an empty 'pass' shell (P0-6)"
    )


def test_orphan_cleanup_cancels_orders_for_symbols_without_positions(
    fake_exchange, async_logger, stop_event, fast_sleep,
):
    if not hasattr(sl_tp_module, "cleanup_orphan_sltp_orders_async"):
        return  # allowed alternative: removed together with its call-site
    fake_exchange._open_orders = [
        {"id": "orphan-1", "symbol": "DOGE/USDT:USDT", "type": "STOP_MARKET"},
        {"id": "active-1", "symbol": "BTC/USDC:USDC", "type": "TAKE_PROFIT_MARKET"},
    ]

    _run(sl_tp_module.cleanup_orphan_sltp_orders_async(
        fake_exchange, {"BTC/USDC:USDC"}, async_logger,
    ))

    cancelled_ids = {call[0] for call in fake_exchange.cancel_order_calls}
    cancel_all_symbols = {call[0] for call in fake_exchange.cancel_all_orders_calls}
    assert "orphan-1" in cancelled_ids or "DOGE/USDT:USDT" in cancel_all_symbols, (
        "orphan conditional order for a symbol without positions was not cancelled: "
        "cancelled=%r cancel_all=%r" % (cancelled_ids, cancel_all_symbols)
    )
    assert "active-1" not in cancelled_ids, "must not cancel orders of an active position"
