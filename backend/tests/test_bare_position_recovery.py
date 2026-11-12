"""R-P0-2 裸仓回收 + protection v2 处置权协调离线测试。

验收要点（ARCH_REFACTOR_PHASE3 §7 T02）：
- SL/TP 注入失败 → 触发 reduceOnly 全平且任务结果如实（False + plan._auto_closed）；
- keep_alert 分支不触碰仓位（无 reduceOnly 单）；
- protection 已接管时不重复平仓（单一处置权）。
"""
from __future__ import annotations

import asyncio

import pytest

from app.logic.exchange_logic_async import process_order_with_sl_tp_async

SYMBOL = "BTC/USDC:USDC"


def _config(**overrides):
    config = {
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
    config.update(overrides)
    return config


def _setup_open_success(fake_exchange):
    """让开仓成功：盘口可用、第一张 limit 单立刻成交、开仓后能查到仓位。

    仓位查询用计数闭包：第 1 次（开仓后查仓位）与第 2 次（平仓前确认持仓）返回
    持仓，之后返回空（全平复核确认 contracts==0，避免补平死循环）。
    """
    fake_exchange._order_statuses = {
        "fake-1": [{"status": "closed", "filled": 1.0}],
        # fake-2：auto_close 的 reduceOnly 全平单，立即成交
        "fake-2": [{"status": "closed", "filled": 1.0}],
    }
    position = {
        "symbol": SYMBOL, "side": "long", "contracts": 1.0, "contractSize": 1.0,
        "entryPrice": 100.0, "markPrice": 100.0, "notional": 100.0, "initialMargin": 10.0,
        "info": {"symbol": SYMBOL, "positionAmt": "1.0", "markPrice": "100.0",
                 "breakEvenPrice": "100.0", "unRealizedProfit": "0.0",
                 "notional": "100.0", "initialMargin": "10.0"},
    }

    def _positions(symbols=None):
        _positions.calls += 1
        if _positions.calls <= 2:
            return [position]
        return []

    _positions.calls = 0
    fake_exchange._positions = _positions


def _make_sltp_fail(fake_exchange):
    """让 SL/TP 注入失败：撤历史挂单失败 → set_tp_sl 先决条件不成立直接返回 False。"""

    async def _fail_cancel_all(symbol=None, params=None):
        fake_exchange.cancel_all_orders_calls.append((symbol, params))
        raise RuntimeError("simulated cancel failure")

    fake_exchange.cancel_all_orders = _fail_cancel_all


def _reduce_only_calls(fake_exchange):
    return [call for call in fake_exchange.create_order_calls
            if (call["params"] or {}).get("reduceOnly") is True]


def test_sltp_failure_triggers_auto_close(fake_exchange, async_logger, stop_event, fast_sleep):
    _setup_open_success(fake_exchange)
    _make_sltp_fail(fake_exchange)

    plan = {"coin": "BTC", "value": 100.0, "side": "buy"}
    ok = asyncio.run(process_order_with_sl_tp_async(
        fake_exchange, plan, _config(), async_logger, stop_event,
    ))

    assert ok is False, "SL/TP 失败的任务必须如实计为失败（D1）"
    assert plan.get('_auto_closed') is True, "自动回收结果必须通过 plan 透传给结果项"
    reduce_calls = _reduce_only_calls(fake_exchange)
    assert reduce_calls, "auto_close 必须触发 reduceOnly 全平"
    for call in reduce_calls:
        assert call["type"] == "limit", "自动回收也必须是限价单（禁止市价）"
        assert (call["params"] or {}).get("postOnly") is True
    levels = [level for level, _msg in async_logger.calls]
    assert "warning" in levels, "回收成功应有 warning 级提示"


def test_keep_alert_does_not_touch_position(fake_exchange, async_logger, stop_event, fast_sleep):
    _setup_open_success(fake_exchange)
    _make_sltp_fail(fake_exchange)

    plan = {"coin": "BTC", "value": 100.0, "side": "buy"}
    ok = asyncio.run(process_order_with_sl_tp_async(
        fake_exchange, plan, _config(unprotected_position_action='keep_alert'),
        async_logger, stop_event,
    ))

    assert ok is False
    assert plan.get('_auto_closed') is None
    assert plan.get('_danger') == 'unprotected'
    assert _reduce_only_calls(fake_exchange) == [], "keep_alert 分支不得触碰仓位"


def test_protection_managed_position_is_not_double_closed(
    fake_exchange, async_logger, stop_event, fast_sleep, monkeypatch,
):
    _setup_open_success(fake_exchange)
    _make_sltp_fail(fake_exchange)
    monkeypatch.setattr("app.protection.service.protection_active_for",
                        lambda full_symbol, side: True)

    plan = {"coin": "BTC", "value": 100.0, "side": "buy"}
    ok = asyncio.run(process_order_with_sl_tp_async(
        fake_exchange, plan, _config(), async_logger, stop_event,
    ))

    assert ok is False
    assert plan.get('_auto_closed') is None
    assert _reduce_only_calls(fake_exchange) == [], "protection 接管时主链路不得重复平仓"
    messages = [msg for _level, msg in async_logger.calls]
    assert any("接管" in msg for msg in messages), "应有 protection 接管的 error 强提示"
