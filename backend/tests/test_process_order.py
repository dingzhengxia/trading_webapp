"""Offline acceptance test: opening a position matches the exact full_symbol (report P0-2).

Same base coin exists on both USDC and USDT markets; the SL/TP orders must be
attached to the freshly opened USDC position, not to a leftover USDT position.
"""
from __future__ import annotations

import asyncio

import pytest

from app.logic.exchange_logic_async import process_order_with_sl_tp_async

USDC_SYMBOL = "BTC/USDC:USDC"
USDT_SYMBOL = "BTC/USDT:USDT"


def _config():
    return {
        "leverage": 10,
        "open_order_fill_timeout_seconds": 5,
        "open_maker_retries": 0,
        "enable_long_sl_tp": True,
        "long_stop_loss_percentage": 10.0,
        "long_take_profit_percentage": 20.0,
        "enable_long_trailing_stop": False,
        "long_trailing_stop_callback_rate": 1.0,
        "enable_short_sl_tp": False,
        "enable_short_trailing_stop": False,
    }


def test_sl_tp_attached_to_newly_opened_full_symbol(
    fake_exchange, async_logger, stop_event, raw_position_factory, fast_sleep,
):
    fake_exchange.markets = {
        USDC_SYMBOL: {"symbol": USDC_SYMBOL, "limits": {"amount": {"min": 0.0001}}},
        USDT_SYMBOL: {"symbol": USDT_SYMBOL, "limits": {"amount": {"min": 0.0001}}},
    }
    fake_exchange._positions = [
        raw_position_factory(USDT_SYMBOL, "long", 5.0, entry_price=90.0, mark_price=90.0, notional=450.0),
        raw_position_factory(USDC_SYMBOL, "long", 1.0, entry_price=100.0, mark_price=100.0, notional=100.0),
    ]
    fake_exchange._order_statuses = {"fake-1": [{"status": "closed", "filled": 1.0}]}

    plan = {"coin": "BTC", "value": 100.0, "side": "buy"}
    ok = asyncio.run(process_order_with_sl_tp_async(
        fake_exchange, plan, _config(), async_logger, stop_event,
    ))

    assert ok is True
    open_calls = [call for call in fake_exchange.create_order_calls if call["type"] == "limit"]
    assert len(open_calls) == 1
    assert open_calls[0]["symbol"] == USDC_SYMBOL, "USDC market must be preferred"

    conditional_calls = [
        call for call in fake_exchange.create_order_calls
        if str(call["type"]).upper() in {"STOP_MARKET", "TAKE_PROFIT_MARKET"}
    ]
    assert conditional_calls, "expected SL/TP orders"
    assert {call["symbol"] for call in conditional_calls} == {USDC_SYMBOL}, (
        "SL/TP attached to the wrong contract (P0-2): %r" % conditional_calls
    )
    for call in conditional_calls:
        assert float(call["amount"]) == pytest.approx(1.0)
