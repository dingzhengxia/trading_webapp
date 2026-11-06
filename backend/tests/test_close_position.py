"""Offline acceptance tests: full-close verification (report P0-4) and limit closes."""
from __future__ import annotations

import asyncio

import pytest

from app.logic.exchange_logic_async import close_position_async

SYMBOL = "BTC/USDC:USDC"


def _run(coro):
    return asyncio.run(coro)


def test_full_close_requires_zero_remaining_and_cleans_orders(
    fake_exchange, async_logger, stop_event, raw_position_factory, fast_sleep,
):
    state = {"fetches": 0}

    def _positions(_symbols):
        state["fetches"] += 1
        if state["fetches"] == 1:
            return [raw_position_factory(SYMBOL, "long", 1.0, notional=100.0)]
        return []

    fake_exchange._positions = _positions
    fake_exchange._order_statuses = {"fake-1": [{"status": "closed", "filled": 1.0}]}

    ok = _run(close_position_async(fake_exchange, SYMBOL, 1.0, async_logger, stop_event))

    assert ok is True
    calls = fake_exchange.create_order_calls
    assert len(calls) == 1
    assert calls[0]["type"] == "limit"
    assert (calls[0]["params"] or {}).get("postOnly") is True
    assert (calls[0]["params"] or {}).get("reduceOnly") is True
    assert calls[0]["side"] == "sell"
    assert float(calls[0]["amount"]) == pytest.approx(1.0)
    assert state["fetches"] >= 2, "full close must re-fetch positions to confirm contracts == 0"
    assert fake_exchange.cancel_all_orders_calls, "SL/TP orders must be cancelled after a full close"


def test_full_close_with_residual_position_returns_false(
    fake_exchange, async_logger, stop_event, raw_position_factory, fast_sleep,
):
    residual = raw_position_factory(SYMBOL, "long", 0.5, notional=50.0)
    fake_exchange._positions = lambda _symbols: [residual]
    fake_exchange._order_statuses = {
        "fake-1": [{"status": "closed", "filled": 1.0}],
        "fake-2": [{"status": "closed", "filled": 0.5}],
        "fake-3": [{"status": "closed", "filled": 0.5}],
    }

    ok = _run(close_position_async(fake_exchange, SYMBOL, 1.0, async_logger, stop_event))

    assert ok is False, "a residual position after a full close must abort (P0-4)"
    calls = fake_exchange.create_order_calls
    assert len(calls) >= 2, "expected re-close attempts for the residual position"
    for call in calls:
        assert call["type"] == "limit"
        assert (call["params"] or {}).get("postOnly") is True
        assert (call["params"] or {}).get("reduceOnly") is True
