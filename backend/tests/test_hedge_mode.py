"""R-P0-3 持仓模式（Hedge Mode）离线测试。

验收要点（ARCH_REFACTOR_PHASE3 §7 T02）：
- hedge → 开仓/平仓/SL/TP 单全部带正确 positionSide；
- 单向 → 一律不携带 positionSide 字段；
- 探测失败 → warning + 按单向继续。
"""
from __future__ import annotations

import asyncio

import pytest

from app.logic.exchange_logic_async import (
    close_position_async,
    detect_position_mode_async,
    position_side_for,
    process_order_with_sl_tp_async,
)

SYMBOL = "BTC/USDC:USDC"


def _config():
    return {
        "leverage": 10,
        "open_order_fill_timeout_seconds": 5,
        "open_maker_retries": 0,
        "close_maker_retries": 0,
        "close_order_fill_timeout_seconds": 5,
        "enable_long_sl_tp": True,
        "long_stop_loss_percentage": 10.0,
        "long_take_profit_percentage": 20.0,
        "enable_long_trailing_stop": False,
        "enable_short_sl_tp": False,
        "enable_short_trailing_stop": False,
    }


def _position_entry(fake_exchange):
    fake_exchange._positions = [
        {
            "symbol": SYMBOL, "side": "long", "contracts": 1.0, "contractSize": 1.0,
            "entryPrice": 100.0, "markPrice": 100.0, "notional": 100.0, "initialMargin": 10.0,
            "info": {"symbol": SYMBOL, "positionAmt": "1.0", "markPrice": "100.0",
                     "breakEvenPrice": "100.0", "unRealizedProfit": "0.0",
                     "notional": "100.0", "initialMargin": "10.0"},
        }
    ]


def _conditional_calls(fake_exchange):
    return [call for call in fake_exchange.create_order_calls
            if str(call["type"]).upper() in {"STOP_MARKET", "TAKE_PROFIT_MARKET"}]


def test_position_side_for_mapping(fake_exchange):
    fake_exchange._twa_hedge_mode = True
    assert position_side_for(fake_exchange, "buy") == "LONG"
    assert position_side_for(fake_exchange, "sell") == "SHORT"
    fake_exchange._twa_hedge_mode = False
    assert position_side_for(fake_exchange, "buy") is None
    assert position_side_for(fake_exchange, "sell") is None


def test_detect_position_mode_hedged(fake_exchange, async_logger):
    fake_exchange.hedge_mode = True
    hedged = asyncio.run(detect_position_mode_async(fake_exchange, async_logger))
    assert hedged is True
    assert fake_exchange._twa_hedge_mode is True


def test_detect_position_mode_failure_falls_back_to_one_way(
    fake_exchange, async_logger,
):
    async def _fail():
        raise RuntimeError("rpc unavailable")

    fake_exchange.fetch_position_mode = _fail
    hedged = asyncio.run(detect_position_mode_async(fake_exchange, async_logger))
    assert hedged is False, "探测失败按单向模式继续"
    assert fake_exchange._twa_hedge_mode is False
    levels = [level for level, _msg in async_logger.calls]
    assert "warning" in levels, "探测失败必须记 warning（不静默吞）"


def test_hedge_mode_all_orders_carry_position_side(
    fake_exchange, async_logger, stop_event, fast_sleep,
):
    fake_exchange.hedge_mode = True
    assert asyncio.run(detect_position_mode_async(fake_exchange, async_logger)) is True
    _position_entry(fake_exchange)
    fake_exchange._order_statuses = {"fake-1": [{"status": "closed", "filled": 1.0}]}

    plan = {"coin": "BTC", "value": 100.0, "side": "buy"}
    ok = asyncio.run(process_order_with_sl_tp_async(
        fake_exchange, plan, _config(), async_logger, stop_event,
    ))

    assert ok is True
    open_calls = [call for call in fake_exchange.create_order_calls if call["type"] == "limit"]
    assert open_calls and all(
        (call["params"] or {}).get("positionSide") == "LONG" for call in open_calls)
    conditional = _conditional_calls(fake_exchange)
    assert conditional and all(
        (call["params"] or {}).get("positionSide") == "LONG" for call in conditional), (
        "SL/TP 单的 positionSide 必须跟随持仓方向（LONG 仓=LONG）"
    )


def test_one_way_mode_omits_position_side(
    fake_exchange, async_logger, stop_event, fast_sleep,
):
    _position_entry(fake_exchange)
    fake_exchange._order_statuses = {"fake-1": [{"status": "closed", "filled": 1.0}]}

    plan = {"coin": "BTC", "value": 100.0, "side": "buy"}
    ok = asyncio.run(process_order_with_sl_tp_async(
        fake_exchange, plan, _config(), async_logger, stop_event,
    ))

    assert ok is True
    for call in fake_exchange.create_order_calls:
        assert "positionSide" not in (call["params"] or {}), (
            "单向模式一律不携带 positionSide（-4061 风险，宁缺勿错）"
        )


def test_hedge_mode_close_order_carries_position_side(
    fake_exchange, async_logger, stop_event, fast_sleep,
):
    fake_exchange._twa_hedge_mode = True
    state = {"fetches": 0}

    def _positions(_symbols):
        state["fetches"] += 1
        if state["fetches"] == 1:
            return [{
                "symbol": SYMBOL, "side": "long", "contracts": 1.0, "contractSize": 1.0,
                "entryPrice": 100.0, "markPrice": 100.0, "notional": 100.0,
                "initialMargin": 10.0,
                "info": {"symbol": SYMBOL, "positionAmt": "1.0", "markPrice": "100.0",
                         "breakEvenPrice": "100.0", "unRealizedProfit": "0.0",
                         "notional": "100.0", "initialMargin": "10.0"},
            }]
        return []

    fake_exchange._positions = _positions
    fake_exchange._order_statuses = {"fake-1": [{"status": "closed", "filled": 1.0}]}

    ok = asyncio.run(close_position_async(fake_exchange, SYMBOL, 1.0, async_logger, stop_event))
    assert ok is True
    close_calls = [call for call in fake_exchange.create_order_calls
                   if (call["params"] or {}).get("reduceOnly") is True]
    assert close_calls and all(
        (call["params"] or {}).get("positionSide") == "LONG" for call in close_calls), (
        "平仓单 positionSide 必须等于持仓方向"
    )
