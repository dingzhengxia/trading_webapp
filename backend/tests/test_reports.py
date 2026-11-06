# backend/tests/test_reports.py
"""周期报告（monitor periodic_reporter 并入）离线测试。

不触达交易所/钉钉/恐惧贪婪接口：行情用 FakeDataService，通知只测签名与截断逻辑。
"""
from __future__ import annotations

import asyncio

import pandas as pd
import pytest
from fastapi import HTTPException

from app.reports import dingtalk
from app.reports.engine import (
    calc_rsi,
    generate_report,
    interval_minutes,
    ohlcv_to_df,
    render_markdown,
    summarize_ohlcv,
)

SYMBOL = 'BTC/USDT:USDT'


def _make_rows(rows: int = 60, up_streak: int = 3):
    """构造一段温和上涨的 K 线：最后 up_streak 根为阳线，倒数第二根放量。

    注意报告口径只看最后一根**已收盘**K 线（iloc[-2]），因此放量/涨幅都落在 rows-2。
    """
    records = []
    price = 100.0
    for index in range(rows):
        open_price = price
        is_up = index >= rows - up_streak
        close_price = open_price * (1.01 if is_up else 0.995)
        volume = 3000.0 if index == rows - 2 else 1000.0
        records.append([index * 60000, open_price, max(open_price, close_price),
                        min(open_price, close_price), close_price, volume])
        price = close_price
    return records


def _make_df(rows: int = 60, up_streak: int = 3) -> pd.DataFrame:
    return ohlcv_to_df(_make_rows(rows, up_streak))


def test_interval_minutes_parsing():
    assert interval_minutes('4h') == 240
    assert interval_minutes('1d') == 1440
    assert interval_minutes('30m') == 30
    assert interval_minutes('2h') == 120
    assert interval_minutes('bogus', default=240) == 240


def test_summarize_ohlcv_detects_gain_consecutive_and_volume_ratio():
    df = _make_df(rows=60, up_streak=3)
    stats = summarize_ohlcv(df, {'volume_ma_period': 20, 'min_consecutive_candles': 2})

    assert stats['gain'] > 0
    # 连涨从最后一根「已收盘」K 线（iloc[-2]）往前数，最新未收盘那根不计入
    assert stats['consecutive'] == 2
    assert stats['volume_ratio'] == pytest.approx(3.0, rel=0.05)


def test_summarize_ohlcv_requires_enough_candles():
    df = _make_df(rows=10)
    assert summarize_ohlcv(df, {'volume_ma_period': 20}) == {}


def test_calc_rsi_in_valid_range():
    df = _make_df(rows=120, up_streak=5)
    value = calc_rsi(df, 14)
    assert value is not None and 0 <= value <= 100


def test_render_markdown_handles_empty_market():
    text = render_markdown({'report_name': '测试报告'}, '4h', None, [], [], [], [], [], 0)
    assert '市场观察' in text
    assert '不构成投资建议' in text


def test_render_markdown_sections():
    text = render_markdown(
        {'report_name': '测试报告', 'top_n_gainers': 5, 'top_n_volume_ratio': 5},
        '4h',
        {'value': 60, 'classification': 'Greed'},
        [{'symbol': SYMBOL, 'gain': 5.2}],
        [{'symbol': SYMBOL, 'ratio': 3.1, 'volume': 1000, 'volume_ma': 300}],
        [{'symbol': SYMBOL, 'rsi': 78.2}],
        [],
        [{'symbol': SYMBOL, 'candles': 4}],
        12,
    )
    assert '市场情绪' in text and 'Greed' in text
    assert '涨幅榜' in text and '成交量异动' in text
    assert '超买' in text and '连涨' in text


class _FakeDataService:
    """假行情服务：只返回预设的 tickers 与 K 线（原始 ccxt 数组格式）。"""

    def __init__(self, symbols, rows):
        self._symbols = symbols
        self._rows = rows
        self.ohlcv_calls = 0

    async def get_top_symbols_by_volume(self, top_n):
        return list(self._symbols)[:top_n]

    async def get_ohlcv(self, symbol, timeframe, limit=400):
        self.ohlcv_calls += 1
        return list(self._rows)


def test_generate_report_with_fake_data(monkeypatch):
    service = _FakeDataService([SYMBOL, 'ETH/USDT:USDT'], _make_rows(rows=60, up_streak=4))

    # 关闭恐惧贪婪（外部接口）避免网络请求
    monkeypatch.setattr('app.reports.engine.fetch_fear_greed', _no_sentiment)

    result = asyncio.run(generate_report({
        'report_name': '离线测试报告',
        'run_interval': '4h',
        'top_n_by_volume': 10,
        'top_n_gainers': 5,
        'top_n_volume_ratio': 5,
        'min_consecutive_candles': 2,
        'volume_ma_period': 20,
        'market_sentiment': {'enabled': False},
    }, data_service=service))

    assert result['report_name'] == '离线测试报告'
    assert result['scanned'] == 2
    assert result['counts']['gainers'] == 2
    assert '涨幅榜' in result['markdown']
    assert result['title'].startswith('📰')


async def _no_sentiment():
    return None


def test_generate_report_raises_when_no_symbols(monkeypatch):
    monkeypatch.setattr('app.reports.engine.fetch_fear_greed', _no_sentiment)
    with pytest.raises(RuntimeError):
        asyncio.run(generate_report({'report_name': '空市场'},
                                    data_service=_FakeDataService([], _make_rows(rows=60))))


def test_dingtalk_signature_and_truncate(monkeypatch):
    monkeypatch.setenv('DINGTALK_WEBHOOK_URL', 'https://example.invalid/robot/send?access_token=abc')
    monkeypatch.setenv('DINGTALK_SECRET', 'secret-value')

    assert dingtalk.is_configured() is True
    url = dingtalk.build_signed_url('https://example.invalid/robot/send?access_token=abc',
                                    'secret-value', timestamp_ms=1700000000000)
    assert 'timestamp=1700000000000' in url
    assert 'sign=' in url

    long_text = 'x' * (dingtalk.MAX_MARKDOWN_CHARS + 100)
    truncated = dingtalk.truncate(long_text)
    assert len(truncated) < len(long_text)
    assert '已截断' in truncated


def test_dingtalk_not_configured(monkeypatch):
    monkeypatch.delenv('DINGTALK_WEBHOOK_URL', raising=False)
    assert dingtalk.is_configured() is False
    assert dingtalk.send_markdown_sync('t', 'x') is False


def test_reports_api_validation_rejects_bad_interval():
    from app.api.reports import _validate_report

    with pytest.raises(HTTPException) as exc:
        _validate_report({'report_name': 'x', 'run_interval': '3h'})
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException):
        _validate_report({'report_name': '', 'run_interval': '4h'})

    with pytest.raises(HTTPException):
        _validate_report({'report_name': 'x', 'run_interval': '4h', 'top_n_by_volume': 9999})

    valid = _validate_report({
        'report_name': '测试', 'enabled': True, 'run_interval': '4h',
        'top_n_by_volume': 50, 'market_sentiment': {'enabled': True, 'rsi_period': 14},
    })
    assert valid['run_interval'] == '4h' and valid['top_n_by_volume'] == 50
