"""R-P0-4 最小名义价值校验离线测试。

验收要点（ARCH_REFACTOR_PHASE3 §7 T01）：
- 3 USDT 的 plan → 不调用 create_order、日志含 skip、返回 False（跳过该币种）；
- 显式 limits.cost.min 与缺省 5.0 两条路径；
- reduceOnly 平仓路径不受 minNotional 校验影响（交易所对 reduce-only 豁免）。
"""
from __future__ import annotations

import asyncio

import pytest

from app.logic.exchange_logic_async import (
    _execute_maker_order_with_retry_async,
    _min_notional,
)
from conftest import _market_entry, default_markets

SYMBOL = "BTC/USDC:USDC"


def test_min_notional_default_is_five():
    exchange = type("M", (), {})()  # 无 market 方法的最小对象
    exchange.markets = {}
    assert _min_notional(exchange, SYMBOL) == pytest.approx(5.0)


def test_min_notional_reads_market_limits_cost_min():
    exchange_markets = {SYMBOL: _market_entry(SYMBOL, 0.0001, min_cost=20.0)}
    exchange = type("M", (), {})()
    exchange.markets = exchange_markets
    assert _min_notional(exchange, SYMBOL) == pytest.approx(20.0)


def test_small_open_plan_skipped_without_create_order(
    fake_exchange, async_logger, stop_event, fast_sleep,
):
    """价值 3 USDT 的开仓计划：不触 create_order、日志含 skip、执行器返回 False。"""
    ok = asyncio.run(_execute_maker_order_with_retry_async(
        fake_exchange, SYMBOL, "buy", {}, 1, 2, async_logger, stop_event,
        value_to_trade=3.0,
    ))

    assert ok is False
    assert fake_exchange.create_order_calls == [], "低于最小名义价值的开仓不得触达 create_order"
    levels = [(level, message) for level, message in async_logger.calls]
    assert any("最小名义价值" in message and ("skip" in message or "跳过" in message)
               for _level, message in levels), f"日志必须含 skip 提示: {levels}"


def test_small_plan_with_explicit_market_min_cost_skips(
    fake_exchange, async_logger, stop_event, fast_sleep,
):
    fake_exchange.markets = {SYMBOL: _market_entry(SYMBOL, 0.0001, min_cost=50.0)}
    ok = asyncio.run(_execute_maker_order_with_retry_async(
        fake_exchange, SYMBOL, "buy", {}, 1, 2, async_logger, stop_event,
        value_to_trade=30.0,
    ))
    assert ok is False
    assert fake_exchange.create_order_calls == []


def test_normal_value_plan_still_fills(fake_exchange, async_logger, stop_event, fast_sleep):
    """名义价值达标的开仓不受影响（防回归）。"""
    fake_exchange._order_statuses = {"fake-1": [{"status": "closed", "filled": 1.0}]}
    ok = asyncio.run(_execute_maker_order_with_retry_async(
        fake_exchange, SYMBOL, "buy", {}, 1, 0, async_logger, stop_event,
        value_to_trade=100.0,
    ))
    assert ok is True
    assert len(fake_exchange.create_order_calls) == 1


def test_reduce_only_close_is_exempt_from_min_notional(
    fake_exchange, async_logger, stop_event, fast_sleep,
):
    """reduceOnly 平仓不受 minNotional 校验影响（残留小仓位必须能清干净）。"""
    fake_exchange._order_statuses = {"fake-1": [{"status": "closed", "filled": 0.001}]}
    ok = asyncio.run(_execute_maker_order_with_retry_async(
        fake_exchange, SYMBOL, "sell", {"reduceOnly": True}, 1, 0, async_logger, stop_event,
        contracts_to_trade=0.001,
    ))
    assert ok is True
    assert len(fake_exchange.create_order_calls) == 1
