"""Offline acceptance tests for the pure manual-trade task builder (report 4.1-4.3)."""
from __future__ import annotations

import ast
import inspect

import pytest

import app.logic.manual_trade_logic as manual_trade_logic_module
from app.logic.manual_trade_logic import (
    ManualTradeTask,
    build_manual_trade_tasks,
    validate_manual_items,
)

CONFIG = {
    "leverage": 10,
    "total_long_position_value": 1000.0,
    "total_short_position_value": 500.0,
}


def _item(symbol, action, value=None):
    item = {"symbol": symbol, "action": action}
    if value is not None:
        item["value"] = value
    return item


def _tasks_by_coin(tasks):
    return {task.coin: task for task in tasks}


# ---------------------------------------------------------------------------
# validate_manual_items
# ---------------------------------------------------------------------------
def test_validate_rejects_empty_items():
    with pytest.raises(ValueError):
        validate_manual_items([])


def test_validate_rejects_duplicate_symbols():
    with pytest.raises(ValueError):
        validate_manual_items([
            _item("BTC", "long", 10),
            _item(" btc ", "short", 10),
        ])


def test_validate_rejects_unknown_action():
    with pytest.raises(ValueError):
        validate_manual_items([_item("BTC", "hold", 10)])


@pytest.mark.parametrize("bad_value", [0, -1, -0.001])
def test_validate_rejects_non_positive_value(bad_value):
    with pytest.raises(ValueError):
        validate_manual_items([_item("BTC", "long", bad_value)])


def test_validate_accepts_valid_items_with_and_without_value():
    validate_manual_items([
        _item("BTC", "long", 100),
        _item("ETH", "short"),
        _item("SOL", "reverse", 50),
    ])


# ---------------------------------------------------------------------------
# build_manual_trade_tasks: long / short
# ---------------------------------------------------------------------------
def test_build_long_and_short_side_and_value():
    tasks = build_manual_trade_tasks(
        [_item("BTC", "long", 100), _item("ETH", "short", 50)],
        [],
        CONFIG,
    )
    by_coin = _tasks_by_coin(tasks)
    assert isinstance(tasks[0], ManualTradeTask)
    assert by_coin["BTC"].side == "buy"
    assert by_coin["BTC"].value == pytest.approx(100.0)
    assert by_coin["BTC"].close_full_symbols == ()
    assert by_coin["BTC"].skip_reason is None
    assert by_coin["ETH"].side == "sell"
    assert by_coin["ETH"].value == pytest.approx(50.0)


def test_build_uses_default_value_when_item_value_missing():
    tasks = build_manual_trade_tasks(
        [_item("SOL", "long"), _item("XRP", "short")],
        [],
        CONFIG,
        default_value=25.0,
    )
    by_coin = _tasks_by_coin(tasks)
    assert by_coin["SOL"].value == pytest.approx(25.0)
    assert by_coin["XRP"].value == pytest.approx(25.0)


def test_build_splits_config_total_between_same_direction_tasks():
    tasks = build_manual_trade_tasks(
        [_item("BTC", "long"), _item("SOL", "long"), _item("ETH", "short")],
        [],
        CONFIG,
    )
    by_coin = _tasks_by_coin(tasks)
    assert by_coin["BTC"].value == pytest.approx(500.0)
    assert by_coin["SOL"].value == pytest.approx(500.0)
    assert by_coin["ETH"].value == pytest.approx(500.0)


def test_build_marks_task_skipped_when_value_is_invalid():
    config = dict(CONFIG, total_long_position_value=0.0, total_short_position_value=0.0)
    tasks = build_manual_trade_tasks([_item("BTC", "long")], [], config)
    assert tasks, "expected one task (worker only logs skip_reason)"
    assert tasks[0].skip_reason is not None
    assert "无效" in tasks[0].skip_reason


# ---------------------------------------------------------------------------
# build_manual_trade_tasks: reverse
# ---------------------------------------------------------------------------
def test_build_reverse_closes_all_positions_and_opens_opposite_side(position_factory):
    positions = [
        position_factory("BTC", "BTC/USDC:USDC", "long", notional=120.0),
        position_factory("BTC", "BTC/USDT:USDT", "long", notional=30.0),
    ]
    tasks = build_manual_trade_tasks([_item("BTC", "reverse")], positions, CONFIG)
    assert len(tasks) == 1
    task = tasks[0]
    assert task.coin == "BTC"
    assert task.side == "sell"
    assert set(task.close_full_symbols) == {"BTC/USDC:USDC", "BTC/USDT:USDT"}
    assert task.value == pytest.approx(150.0)
    assert task.skip_reason is None


def test_build_reverse_from_short_position_goes_long(position_factory):
    positions = [position_factory("ETH", "ETH/USDT:USDT", "short", notional=80.0)]
    task = _tasks_by_coin(build_manual_trade_tasks([_item("ETH", "reverse")], positions, CONFIG))["ETH"]
    assert task.side == "buy"
    assert task.value == pytest.approx(80.0)
    assert task.skip_reason is None


def test_build_reverse_keeps_explicit_value(position_factory):
    positions = [position_factory("SOL", "SOL/USDC:USDC", "long", notional=200.0)]
    task = _tasks_by_coin(
        build_manual_trade_tasks([_item("SOL", "reverse", 75.0)], positions, CONFIG)
    )["SOL"]
    assert task.value == pytest.approx(75.0)
    assert set(task.close_full_symbols) == {"SOL/USDC:USDC"}


def test_build_reverse_without_position_is_skipped(position_factory):
    positions = [position_factory("ETH", "ETH/USDT:USDT", "long", notional=100.0)]
    task = _tasks_by_coin(build_manual_trade_tasks([_item("BTC", "reverse")], positions, CONFIG))["BTC"]
    assert task.skip_reason is not None
    assert "无持仓" in task.skip_reason
    assert task.side is None


def test_build_reverse_with_mixed_long_and_short_is_skipped(position_factory):
    positions = [
        position_factory("BTC", "BTC/USDC:USDC", "long", notional=100.0),
        position_factory("BTC", "BTC/USDT:USDT", "short", notional=100.0),
    ]
    task = _tasks_by_coin(build_manual_trade_tasks([_item("BTC", "reverse")], positions, CONFIG))["BTC"]
    assert task.skip_reason is not None
    assert any(keyword in task.skip_reason for keyword in ("并存", "多空", "冲突"))
    assert task.side is None


def test_build_normalises_coin_symbols():
    tasks = build_manual_trade_tasks(
        [_item(" btc ", "long", 10), _item("eth", "short", 10)],
        [],
        CONFIG,
    )
    assert {task.coin for task in tasks} == {"BTC", "ETH"}


# ---------------------------------------------------------------------------
# Purity: the module must not perform IO or import ccxt (report 4.3)
# ---------------------------------------------------------------------------
def test_manual_trade_logic_module_is_pure():
    source = inspect.getsource(manual_trade_logic_module)
    tree = ast.parse(source)
    forbidden_modules = {"ccxt", "requests", "aiohttp", "httpx", "urllib", "socket"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden_modules, alias.name
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").split(".")[0]
            assert module not in forbidden_modules, node.module
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            assert name not in {"open", "urlopen", "connect", "request"}, (
                "pure logic module must not perform IO"
            )
