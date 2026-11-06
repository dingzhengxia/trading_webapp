"""Offline acceptance tests for position fetching (report P0-5)."""
from __future__ import annotations

import asyncio

import pytest

from app.logic.exchange_logic_async import fetch_positions_with_pnl_async


def _run(coro):
    return asyncio.run(coro)


def test_exchange_errors_are_not_swallowed(fake_exchange):
    def _boom(_symbols):
        raise RuntimeError("exchange unavailable")

    fake_exchange._positions = _boom
    with pytest.raises(RuntimeError, match="exchange unavailable"):
        _run(fetch_positions_with_pnl_async(fake_exchange, 10))


def test_uses_position_info_fields_without_extra_tickers(fake_exchange, raw_position_factory):
    raw = raw_position_factory(
        "BTC/USDC:USDC", "LONG", 2.0, entry_price=100.0, mark_price=110.0,
        notional=220.0, initial_margin=10.0,
    )
    fake_exchange._positions = [raw]

    positions = _run(fetch_positions_with_pnl_async(fake_exchange, 10))

    assert len(positions) == 1
    position = positions[0]
    assert position.full_symbol == "BTC/USDC:USDC"
    assert position.symbol == "BTC"
    assert position.side == "long", "position side must be normalised to lowercase"
    assert position.mark_price == pytest.approx(110.0)
    assert position.notional == pytest.approx(220.0)
    assert position.pnl == pytest.approx(20.0)
    assert position.pnl_percentage == pytest.approx(200.0)
    assert fake_exchange.fetch_tickers_calls == [], (
        "must not add a fetch_tickers request per position"
    )
