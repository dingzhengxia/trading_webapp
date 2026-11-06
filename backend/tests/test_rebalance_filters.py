"""Offline acceptance tests for rebalance filters / method validation (report P1-2)."""
from __future__ import annotations

import pytest

from app.logic.rebalance_logic import (
    calculate_indicators_for_filtering,
    screen_coins_based_on_relative_weakness,
    validate_rebalance_method,
)


def test_unsupported_rebalance_method_is_rejected():
    with pytest.raises(ValueError):
        validate_rebalance_method('foam')
    with pytest.raises(ValueError):
        validate_rebalance_method('unknown_method')


def test_supported_rebalance_method_is_normalised():
    assert validate_rebalance_method(' Multi_Factor_Weakest ') == 'multi_factor_weakest'


def _klines(days=60, base=100.0, volume=1000.0, last_volume_multiplier=1.0):
    rows = []
    for index in range(days):
        timestamp = index * 86_400_000
        close = base * (1 + 0.001 * index)
        rows.append([
            timestamp,
            close,
            close * 1.001,
            close * 0.999,
            close,
            volume if index < days - 1 else volume * last_volume_multiplier,
        ])
    return rows


def _criteria():
    return {
        'top_n': 10,
        'enable_rebalance_filters': True,
        'rebalance_rsi_period': 14,
        'rebalance_rsi_threshold': 25.0,
        'rebalance_short_term_momentum_days': 3,
        'rebalance_short_term_momentum_threshold': 15.0,
        'rebalance_bollinger_period': 20,
        'rebalance_bollinger_std_dev': 2,
        'rebalance_bollinger_width_spike_ratio': 2.0,
        'rebalance_volume_ma_days': 20,
        'rebalance_volume_spike_ratio': 3.0,
        'abs_momentum_days': 21,
        'rel_strength_days': 21,
    }


def test_volume_spike_filter_is_applied():
    spiked = {'SPIKE': _klines(last_volume_multiplier=10.0)}
    benchmark = {'BTC': _klines()}

    assert screen_coins_based_on_relative_weakness(spiked, benchmark, _criteria(), []) == []


def test_bollinger_width_spike_filter_is_applied():
    days = 60
    rows = []
    for index in range(days):
        timestamp = index * 86_400_000
        if index < 40:
            close = 100.0
        else:
            close = 100.0 + (8.0 if index % 2 == 0 else -8.0)
        rows.append([timestamp, close, close, close, close, 1000.0])

    indicators = calculate_indicators_for_filtering(
        __import__('pandas').DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        .set_index(__import__('pandas').to_datetime([row[0] for row in rows], unit='ms')),
        _criteria(),
    )
    assert 'bollinger_width_ratio' in indicators
    assert indicators['bollinger_width_ratio'] > _criteria()['rebalance_bollinger_width_spike_ratio']

    candidates = {'WIDE': rows}
    benchmark = {'BTC': _klines()}
    assert screen_coins_based_on_relative_weakness(candidates, benchmark, _criteria(), []) == []


def test_filters_disabled_or_empty_data_is_safe():
    criteria = dict(_criteria(), enable_rebalance_filters=False)
    candidates = {'SPIKE': _klines(last_volume_multiplier=10.0)}
    benchmark = {'BTC': _klines()}
    result = screen_coins_based_on_relative_weakness(candidates, benchmark, criteria, [])
    assert result == ['SPIKE']

    assert screen_coins_based_on_relative_weakness({}, {}, _criteria(), []) == []
    assert screen_coins_based_on_relative_weakness({'X': []}, {'BTC': _klines()}, _criteria(), []) == []
    assert calculate_indicators_for_filtering(None, _criteria()) == {}
