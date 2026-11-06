"""Offline acceptance tests: maker (limit/post-only) execution with partial-fill retry.

Contract: report 2 (P0-3), 3.2 and 5.3.
"""
from __future__ import annotations

import asyncio

import pytest

from app.logic.exchange_logic_async import _execute_maker_order_with_retry_async

SYMBOL = "BTC/USDC:USDC"


def _run(coro):
    return asyncio.run(coro)


def _assert_limit_post_only(call):
    assert call["type"] == "limit", "only limit orders may be submitted: %r" % (call,)
    assert (call["params"] or {}).get("postOnly") is True, "limit orders must be post-only: %r" % (call,)


def test_buy_uses_best_bid_price_and_limit_post_only(fake_exchange, async_logger, stop_event, fast_sleep):
    fake_exchange._order_statuses = {"fake-1": [{"status": "closed", "filled": 1.0}]}

    ok = _run(_execute_maker_order_with_retry_async(
        fake_exchange, SYMBOL, "buy", {}, 5, 0, async_logger, stop_event, value_to_trade=100.0,
    ))

    assert ok is True
    assert len(fake_exchange.create_order_calls) == 1
    call = fake_exchange.create_order_calls[0]
    _assert_limit_post_only(call)
    assert call["side"] == "buy"
    assert float(call["price"]) == pytest.approx(100.0)  # bids[0][0]
    assert float(call["amount"]) == pytest.approx(1.0)  # 100 USD / 100


def test_sell_uses_best_ask_price_and_limit_post_only(fake_exchange, async_logger, stop_event, fast_sleep):
    fake_exchange._order_statuses = {"fake-1": [{"status": "closed", "filled": 1.0}]}

    ok = _run(_execute_maker_order_with_retry_async(
        fake_exchange, SYMBOL, "sell", {}, 5, 0, async_logger, stop_event, value_to_trade=100.5,
    ))

    assert ok is True
    call = fake_exchange.create_order_calls[0]
    _assert_limit_post_only(call)
    assert call["side"] == "sell"
    assert float(call["price"]) == pytest.approx(100.5)  # asks[0][0]


def test_partial_fill_retry_only_submits_remaining_quantity(fake_exchange, async_logger, stop_event, fast_sleep):
    fake_exchange._order_statuses = {
        "fake-1": [{"status": "open", "amount": 1.0, "filled": 0.4, "remaining": 0.6}],
        "fake-2": [{"status": "closed", "amount": 0.6, "filled": 0.6, "remaining": 0.0}],
    }

    ok = _run(_execute_maker_order_with_retry_async(
        fake_exchange, SYMBOL, "buy", {}, 0.05, 1, async_logger, stop_event, contracts_to_trade=1.0,
    ))

    assert ok is True
    calls = fake_exchange.create_order_calls
    assert len(calls) >= 2, "expected a retry after the partial fill: %r" % (calls,)
    for call in calls:
        _assert_limit_post_only(call)
    assert float(calls[0]["amount"]) == pytest.approx(1.0)
    assert float(calls[1]["amount"]) == pytest.approx(0.6, abs=1e-6), (
        "retry must only submit the unfilled remainder, got %r" % (calls[1],)
    )
    assert len(fake_exchange.cancel_order_calls) >= 1, "timed-out order must be cancelled"


def test_retry_stops_when_remaining_quantity_is_below_market_minimum(
    fake_exchange, async_logger, stop_event, fast_sleep,
):
    fake_exchange.markets[SYMBOL] = {"symbol": SYMBOL, "limits": {"amount": {"min": 0.01}}}
    fake_exchange._order_statuses = {
        "fake-1": [{"status": "open", "amount": 1.0, "filled": 0.999, "remaining": 0.001}],
    }

    _run(_execute_maker_order_with_retry_async(
        fake_exchange, SYMBOL, "buy", {}, 0.05, 3, async_logger, stop_event, contracts_to_trade=1.0,
    ))

    assert len(fake_exchange.create_order_calls) == 1, (
        "must not submit a second order below the market minimum (over-exposure risk)"
    )


def test_reduce_only_params_are_preserved_and_post_only_added(fake_exchange, async_logger, stop_event, fast_sleep):
    fake_exchange._order_statuses = {"fake-1": [{"status": "closed", "filled": 1.0}]}

    ok = _run(_execute_maker_order_with_retry_async(
        fake_exchange, SYMBOL, "sell", {"reduceOnly": True}, 5, 0, async_logger, stop_event,
        contracts_to_trade=1.0,
    ))

    assert ok is True
    params = fake_exchange.create_order_calls[0]["params"]
    assert params.get("reduceOnly") is True
    assert params.get("postOnly") is True


def test_no_market_order_is_ever_submitted(fake_exchange, async_logger, stop_event, fast_sleep):
    fake_exchange._order_statuses = {"fake-1": [{"status": "closed", "filled": 1.0}]}
    _run(_execute_maker_order_with_retry_async(
        fake_exchange, SYMBOL, "buy", {}, 5, 0, async_logger, stop_event, value_to_trade=50.0,
    ))
    order_types = [call["type"] for call in fake_exchange.create_order_calls]
    assert order_types, "expected at least one order"
    assert all(order_type == "limit" for order_type in order_types), order_types
