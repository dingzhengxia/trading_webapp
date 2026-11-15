"""Offline acceptance tests: pure trade-plan calculator (report P1-3 / 5.3)."""
from __future__ import annotations

import pytest

from app.logic.plan_calculator import calculate_trade_plan, stale_weight_note


def _base_config(**overrides):
    config = {
        "enable_long_trades": True,
        "enable_short_trades": True,
        "total_long_position_value": 1000.0,
        "total_short_position_value": 500.0,
        "long_coin_list": [],
        "short_coin_list": [],
        "long_custom_weights": {},
    }
    config.update(overrides)
    return config


def _plans(config):
    result = calculate_trade_plan(config)
    assert isinstance(result, tuple) and len(result) == 2, (
        "calculate_trade_plan must keep returning (long_plan, short_plan), got %r" % (result,)
    )
    return result


def test_btc_eth_special_allocation_with_remaining_split():
    long_plan, short_plan = _plans(_base_config(
        long_coin_list=["BTC", "ETH", "SOL", "XRP"],
    ))
    assert long_plan == {
        "BTC": pytest.approx(400.0),
        "ETH": pytest.approx(300.0),
        "SOL": pytest.approx(150.0),
        "XRP": pytest.approx(150.0),
    }
    assert short_plan == {}


def test_satellite_only_coins_are_split_evenly():
    long_plan, _ = _plans(_base_config(long_coin_list=["SOL", "XRP"]))
    assert long_plan == {"SOL": pytest.approx(500.0), "XRP": pytest.approx(500.0)}


def test_custom_weights_are_normalised():
    long_plan, _ = _plans(_base_config(
        long_coin_list=["BTC", "SOL"],
        long_custom_weights={"BTC": 1, "SOL": 3},
    ))
    assert long_plan == {"BTC": pytest.approx(250.0), "SOL": pytest.approx(750.0)}


def test_all_zero_custom_weights_fall_back_to_even_split():
    long_plan, _ = _plans(_base_config(
        long_coin_list=["SOL", "XRP"],
        long_custom_weights={"SOL": 0, "XRP": 0},
    ))
    assert long_plan == {"SOL": pytest.approx(500.0), "XRP": pytest.approx(500.0)}


def test_weights_for_coins_outside_the_list_are_ignored():
    long_plan, _ = _plans(_base_config(
        long_coin_list=["SOL", "XRP"],
        long_custom_weights={"SOL": 60, "DOGE": 40},
    ))
    assert long_plan == {"SOL": pytest.approx(600.0), "XRP": pytest.approx(400.0)}


def test_equal_weights_split_total_evenly():
    """均分权重：3000 分给 ETH/BNB 两个币 → 各 1500（2026-11-15 用户实际场景）。"""
    long_plan, _ = _plans(_base_config(
        total_long_position_value=3000.0,
        long_coin_list=["ETH", "BNB"],
        long_custom_weights={"ETH": 50, "BNB": 50},
    ))
    assert long_plan == {"ETH": pytest.approx(1500.0), "BNB": pytest.approx(1500.0)}


def test_unassigned_coin_is_not_dropped_when_weights_already_sum_to_100():
    """只给 BTC/ETH 设了 50/50，后来把 BNB 加进清单：
    旧实现给 BNB 权重 0 → BNB 直接不出现在计划里（用户只看到「这个币怎么没开」）。
    现在按已分配权重的均值参与 → 三个币均分。"""
    long_plan, _ = _plans(_base_config(
        total_long_position_value=3000.0,
        long_coin_list=["BTC", "ETH", "BNB"],
        long_custom_weights={"BTC": 50, "ETH": 50},
    ))
    assert long_plan == {
        "BTC": pytest.approx(1000.0),
        "ETH": pytest.approx(1000.0),
        "BNB": pytest.approx(1000.0),
    }


def test_partial_weights_share_the_remaining_percentage():
    """权重总和 <100 时保持原口径：剩余比例由未设置权重的币种均分。"""
    long_plan, _ = _plans(_base_config(
        long_coin_list=["BTC", "SOL", "XRP"],
        long_custom_weights={"BTC": 60},
    ))
    assert long_plan == {
        "BTC": pytest.approx(600.0),
        "SOL": pytest.approx(200.0),
        "XRP": pytest.approx(200.0),
    }


def test_empty_coin_list_returns_empty_plans():
    long_plan, short_plan = _plans(_base_config())
    assert long_plan == {}
    assert short_plan == {}


def test_short_list_is_split_evenly():
    long_plan, short_plan = _plans(_base_config(short_coin_list=["ADA", "DOT"]))
    assert long_plan == {}
    assert short_plan == {"ADA": pytest.approx(250.0), "DOT": pytest.approx(250.0)}


def test_symbols_are_uppercased_and_deduplicated():
    long_plan, _ = _plans(_base_config(long_coin_list=["SOL", "sol", "XRP", "xrp", "SOL"]))
    assert long_plan == {"SOL": pytest.approx(500.0), "XRP": pytest.approx(500.0)}


def test_disabled_direction_produces_no_plan():
    long_plan, short_plan = _plans(_base_config(
        enable_long_trades=False,
        enable_short_trades=False,
        long_coin_list=["BTC"],
        short_coin_list=["ADA"],
    ))
    assert long_plan == {}
    assert short_plan == {}


def test_calculator_does_not_print_debug_output(capsys):
    long_plan, _ = _plans(_base_config(long_coin_list=["BTC", "SOL"]))
    assert long_plan
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


# ---------------------------------------------------------------------------
# 权重自查（2026-11-15 事故：存的是另一套币的权重 → 静默回退默认分配）
# ---------------------------------------------------------------------------
def test_stale_weights_are_reported_when_no_key_matches():
    note = stale_weight_note(_base_config(
        long_coin_list=["BTC", "ETH", "BNB"],
        long_custom_weights={"AAPL": 14.29, "AMD": 14.29, "NVDA": 14.29},
    ))
    assert "没有一个币在当前做多清单" in note
    assert "AAPL" in note


def test_stale_weight_note_is_silent_when_weights_match():
    assert stale_weight_note(_base_config(
        long_coin_list=["BTC", "ETH"],
        long_custom_weights={"BTC": 50, "ETH": 50},
    )) == ""
    # 一部分能对上就不算失效
    assert stale_weight_note(_base_config(
        long_coin_list=["BTC", "ETH"],
        long_custom_weights={"BTC": 50, "AAPL": 50},
    )) == ""
    # 没设权重 = 正常使用默认分配，不需要警告
    assert stale_weight_note(_base_config(long_coin_list=["BTC"])) == ""
