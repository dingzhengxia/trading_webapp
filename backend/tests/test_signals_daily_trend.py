# tests/test_signals_daily_trend.py
"""信号列表补日线趋势标签（attach_daily_trend）：顺势/逆势/不适用 + 去重 + 容错。

趋势判定本身在 test_trend_filter.py 覆盖，这里只验证「列表装饰」的接线与降级，
所以直接给 service 塞一个 stub TrendFilter，不碰 K 线与 pandas-ta。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.signals import service as signal_service  # noqa: E402


class _StubTrendFilter:
    """trend_of 打桩：按 symbol 返回预设趋势，记录调用次数。"""

    def __init__(self, mapping, error_symbols=()):
        self.mapping = mapping
        self.error_symbols = set(error_symbols)
        self.calls = []

    async def trend_of(self, symbol):
        self.calls.append(symbol)
        if symbol in self.error_symbols:
            raise RuntimeError('boom')
        return self.mapping.get(symbol, 'neutral')


def _sig(symbol, direction, full=None):
    return {'symbol': symbol, 'full_symbol': full or f'{symbol}/USDT:USDT',
            'direction': direction, 'strategy': 'ma_breakout', 'timeframe': '4h'}


def _run(signals, stub, monkeypatch):
    monkeypatch.setattr(signal_service, '_get_trend_display_filter', lambda: stub)
    return asyncio.run(signal_service.attach_daily_trend(signals))


def test_marks_with_trend_and_against_trend(monkeypatch):
    stub = _StubTrendFilter({'BTC/USDT:USDT': 'short', 'ETH/USDT:USDT': 'long'})
    signals = [_sig('BTC', 'short'), _sig('ETH', 'short')]
    out = _run(signals, stub, monkeypatch)

    assert out[0]['daily_trend'] == 'short' and out[0]['trend_ok'] is True
    assert out[1]['daily_trend'] == 'long' and out[1]['trend_ok'] is False


def test_neutral_trend_or_neutral_signal_is_not_applicable(monkeypatch):
    stub = _StubTrendFilter({'SOL/USDT:USDT': 'neutral', 'BNB/USDT:USDT': 'short'})
    signals = [_sig('SOL', 'long'), _sig('BNB', 'neutral')]
    out = _run(signals, stub, monkeypatch)

    assert out[0]['daily_trend'] == 'neutral' and out[0]['trend_ok'] is None
    assert out[1]['daily_trend'] == 'short' and out[1]['trend_ok'] is None  # 观望信号永不开仓


def test_same_symbol_queried_once(monkeypatch):
    stub = _StubTrendFilter({'BTC/USDT:USDT': 'long'})
    signals = [_sig('BTC', 'long'), _sig('BTC', 'short'), _sig('BTC', 'long')]
    out = _run(signals, stub, monkeypatch)

    assert stub.calls == ['BTC/USDT:USDT']
    assert [s['trend_ok'] for s in out] == [True, False, True]


def test_single_symbol_failure_does_not_break_list(monkeypatch):
    stub = _StubTrendFilter({'BTC/USDT:USDT': 'long'}, error_symbols={'ETH/USDT:USDT'})
    signals = [_sig('ETH', 'long'), _sig('BTC', 'long')]
    out = _run(signals, stub, monkeypatch)

    assert 'daily_trend' not in out[0]        # 失败的那条只是没有标签
    assert out[1]['daily_trend'] == 'long' and out[1]['trend_ok'] is True


def test_empty_list_is_noop(monkeypatch):
    stub = _StubTrendFilter({})
    assert _run([], stub, monkeypatch) == []
    assert stub.calls == []
