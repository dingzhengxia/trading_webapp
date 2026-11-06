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


def test_value_mode_recomputes_quantity_after_price_move(fake_exchange, async_logger, stop_event, fast_sleep):
    """比率回归：价值模式重试时必须按「剩余价值 / 当前价」重算数量。

    首轮盘口 bid=100，部分成交后超时撤单；第二轮价格涨到 bid=125。
    目标价值 100 USD：首轮成交 0.4 × 100 = 40 USD；剩余 60 USD 应按新价
    重算为 60/125 = 0.48（而不是沿用旧价算出的 0.6）。
    """
    books = iter([
        {"bids": [[100.0, 10.0]], "asks": [[100.5, 10.0]]},
        {"bids": [[125.0, 10.0]], "asks": [[125.5, 10.0]]},
    ])
    fake_exchange._order_book = lambda symbol: next(books)
    fake_exchange._order_statuses = {
        "fake-1": [{"status": "open", "amount": 1.0, "filled": 0.4, "remaining": 0.6}],
        "fake-2": [{"status": "closed", "amount": 0.48, "filled": 0.48, "remaining": 0.0}],
    }

    ok = _run(_execute_maker_order_with_retry_async(
        fake_exchange, SYMBOL, "buy", {}, 0.05, 2, async_logger, stop_event, value_to_trade=100.0,
    ))

    assert ok is True
    calls = fake_exchange.create_order_calls
    assert len(calls) == 2, calls
    _assert_limit_post_only(calls[0])
    _assert_limit_post_only(calls[1])
    # 首轮：100 USD / 100 = 1.0
    assert float(calls[0]["amount"]) == pytest.approx(1.0)
    assert float(calls[0]["price"]) == pytest.approx(100.0)
    # 重试轮：剩余 60 USD / 新价 125 = 0.48，而不是固定的 0.6
    assert float(calls[1]["amount"]) == pytest.approx(0.48, abs=1e-9), (
        "retry must recompute quantity from remaining value at the new price: %r" % (calls[1],)
    )
    assert float(calls[1]["price"]) == pytest.approx(125.0)


def test_value_mode_final_notional_matches_target_on_fills(fake_exchange, async_logger, stop_event, fast_sleep):
    """价值模式部分成交 + 最低下单量截断后，累计名义价值应贴合目标值。"""
    books = iter([
        {"bids": [[100.0, 10.0]], "asks": [[100.5, 10.0]]},
        {"bids": [[80.0, 10.0]], "asks": [[80.5, 10.0]]},
    ])
    fake_exchange._order_book = lambda symbol: next(books)
    fake_exchange._order_statuses = {
        # 首轮 1.0 只成交 0.9（名义 90 USD），第二轮价格跌到 80 →
        # 剩余 10 USD / 80 = 0.125，全部成交（名义 10 USD）
        "fake-1": [{"status": "open", "amount": 1.0, "filled": 0.9, "remaining": 0.1}],
        "fake-2": [{"status": "closed", "amount": 0.125, "filled": 0.125, "remaining": 0.0}],
    }

    ok = _run(_execute_maker_order_with_retry_async(
        fake_exchange, SYMBOL, "buy", {}, 0.05, 2, async_logger, stop_event, value_to_trade=100.0,
    ))

    assert ok is True
    calls = fake_exchange.create_order_calls
    assert len(calls) == 2
    assert float(calls[1]["amount"]) == pytest.approx(0.125, abs=1e-9), calls
    assert float(calls[1]["price"]) == pytest.approx(80.0)
    # 总名义价值 = 0.9×100 + 0.125×80 = 100.0
    total_notional = 0.9 * 100.0 + 0.125 * 80.0
    assert total_notional == pytest.approx(100.0)
