"""系统已收敛为只使用仓位保护 v2：固定 SL/TP 条件单链路必须完全不干预。

历史版本会按交易所均价撤旧单、重挂固定条件单，与「每笔开仓独立止盈止损」冲突。
这里固化新契约：该链路保留兼容入口，但不下任何单、不撤任何单。
"""
from __future__ import annotations

import asyncio
import inspect

import app.logic.sl_tp_logic_async as sl_tp_module
from app.logic.sl_tp_logic_async import set_tp_sl_for_position_async

CONFIG = {
    "leverage": 20,
    "enable_long_sl_tp": True,
    "long_stop_loss_percentage": 50.0,
    "long_take_profit_percentage": 100.0,
    "enable_long_trailing_stop": True,
    "long_trailing_stop_callback_rate": 1.0,
}


def _run(coro):
    return asyncio.run(coro)


def test_fixed_path_never_places_any_order(
    fake_exchange, async_logger, stop_event, position_factory, fast_sleep,
):
    position = position_factory("BTC", "BTC/USDC:USDC", "long", contracts=1.0, entry_price=100.0)

    assert _run(set_tp_sl_for_position_async(
        fake_exchange, position, CONFIG, async_logger, stop_event)) is True

    assert fake_exchange.create_order_calls == []
    assert fake_exchange.cancel_all_orders_calls == []


def test_short_position_also_ignores_legacy_path(
    fake_exchange, async_logger, stop_event, position_factory, fast_sleep,
):
    position = position_factory("ETH", "ETH/USDT:USDT", "short", contracts=2.0, entry_price=100.0)

    assert _run(set_tp_sl_for_position_async(
        fake_exchange, position, CONFIG, async_logger, stop_event)) is True
    assert fake_exchange.create_order_calls == []


def test_sltp_guard_is_a_noop_without_rest_calls(fake_exchange, async_logger, stop_event):
    stats = _run(sl_tp_module.ensure_positions_sltp_async(
        fake_exchange, [], CONFIG, async_logger, stop_event))
    assert stats == {'checked': 0, 'guarded': 0, 'skipped': 0, 'failed': 0}


def test_orphan_cleanup_is_implemented_or_removed():
    if not hasattr(sl_tp_module, "cleanup_orphan_sltp_orders_async"):
        return
    import ast

    source = inspect.getsource(sl_tp_module.cleanup_orphan_sltp_orders_async)
    tree = ast.parse(source.strip().lstrip("@"))
    function = tree.body[0]
    body_nodes = [node for node in function.body
                  if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))]
    assert not (len(body_nodes) == 1 and isinstance(body_nodes[0], ast.Pass))


def test_orphan_cleanup_cancels_orders_for_symbols_without_positions(
    fake_exchange, async_logger, stop_event, fast_sleep,
):
    if not hasattr(sl_tp_module, "cleanup_orphan_sltp_orders_async"):
        return
    fake_exchange._open_orders = [
        {"id": "orphan-1", "symbol": "DOGE/USDT:USDT", "type": "STOP_MARKET"},
        {"id": "active-1", "symbol": "BTC/USDC:USDC", "type": "TAKE_PROFIT_MARKET"},
    ]

    _run(sl_tp_module.cleanup_orphan_sltp_orders_async(
        fake_exchange, {"BTC/USDC:USDC"}, async_logger,
    ))

    cancelled_ids = {call[0] for call in fake_exchange.cancel_order_calls}
    cancel_all_symbols = {call[0] for call in fake_exchange.cancel_all_orders_calls}
    assert "orphan-1" in cancelled_ids or "DOGE/USDT:USDT" in cancel_all_symbols
    assert "active-1" not in cancelled_ids
