# backend/tests/test_trading_hours.py
"""币股（TradFi 代币化标的）交易时段判定 + K 线会话过滤单测。

时间锚点：2026-11-16（周一）。11 月起美东已进入冬令时（ET=UTC-5）。
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.signals import trading_hours


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def _ms(dt):
    return int(dt.timestamp() * 1000)


# ------------------------------------------------------------------ 市场识别
def test_tradfi_market_detection():
    markets = {
        'XAG/USDT:USDT': {'info': {'underlyingType': 'COMMODITY',
                                   'underlyingSubType': ['TradFi']}},
        '005930/USDT:USDT': {'info': {'underlyingType': 'KR_EQUITY',
                                      'underlyingSubType': ['TradFi']}},
        '700/USDT:USDT': {'info': {'underlyingType': 'HK_EQUITY'}},
        'BTC/USDT:USDT': {'info': {'underlyingType': 'COIN'}},
        'MYSTERY/USDT:USDT': {'info': {'underlyingSubType': ['TradFi']}},  # 未知类型兜底
        'NOINFO/USDT:USDT': {'symbol': 'NOINFO/USDT:USDT'},
    }
    assert trading_hours.tradfi_market('XAG/USDT:USDT', markets) == 'US'
    assert trading_hours.tradfi_market('005930/USDT:USDT', markets) == 'KR'
    assert trading_hours.tradfi_market('700/USDT:USDT', markets) == 'HK'
    assert trading_hours.tradfi_market('MYSTERY/USDT:USDT', markets) == 'US'
    assert trading_hours.tradfi_market('BTC/USDT:USDT', markets) is None
    assert trading_hours.tradfi_market('NOINFO/USDT:USDT', markets) is None
    assert trading_hours.tradfi_market('MISSING/USDT:USDT', markets) is None


# ------------------------------------------------------------------ 会话判定
def test_us_session_boundaries_est_winter():
    # 开盘 09:30 ET（14:30 UTC）半开区间：恰好 09:30 在内、09:29 不在
    assert trading_hours.in_session('US', _utc(2026, 11, 16, 14, 30))
    assert not trading_hours.in_session('US', _utc(2026, 11, 16, 14, 29))
    # 15:59 在内，16:00 收盘即不在
    assert trading_hours.in_session('US', _utc(2026, 11, 16, 20, 59))
    assert not trading_hours.in_session('US', _utc(2026, 11, 16, 21, 0))
    # 深夜 / 周末（截图里的噪音场景：北京时间周一早上 = 美东周日晚）
    assert not trading_hours.in_session('US', _utc(2026, 11, 16, 3, 0))
    assert not trading_hours.in_session('US', _utc(2026, 11, 15, 20, 37))


def test_us_session_dst_summer():
    # 夏令时（ET=UTC-4）：09:30 ET = 13:30 UTC
    assert trading_hours.in_session('US', _utc(2026, 7, 13, 13, 30))
    assert not trading_hours.in_session('US', _utc(2026, 7, 13, 13, 29))


def test_kr_session_seoul_timezone():
    seoul = ZoneInfo('Asia/Seoul')
    assert trading_hours.in_session('KR', datetime(2026, 11, 16, 10, 0, tzinfo=seoul))
    assert not trading_hours.in_session('KR', datetime(2026, 11, 16, 8, 59, tzinfo=seoul))
    assert not trading_hours.in_session('KR', datetime(2026, 11, 16, 15, 31, tzinfo=seoul))
    assert not trading_hours.in_session('KR', datetime(2026, 11, 15, 10, 0, tzinfo=seoul))  # 周日


def test_hk_session_lunch_break():
    # 港股 09:30-12:00 / 13:00-16:00，午休不在时段内
    assert trading_hours.in_session('HK', _utc(2026, 11, 16, 3, 0))    # 11:00 HKT
    assert not trading_hours.in_session('HK', _utc(2026, 11, 16, 4, 0))   # 12:00 HKT 午休
    assert trading_hours.in_session('HK', _utc(2026, 11, 16, 6, 0))    # 14:00 HKT


# ------------------------------------------------------------------ 扫描闸门
def test_scan_allowed_warmup_gate():
    # 开盘后 30 分钟（10:00 ET）：warmup=60 不放行
    ok, reason = trading_hours.scan_allowed('US', warmup_minutes=60,
                                            dt=_utc(2026, 11, 16, 15, 0))
    assert not ok and '预热' in reason
    # 开盘后 2 小时（11:30 ET）：放行
    ok, _ = trading_hours.scan_allowed('US', warmup_minutes=60,
                                       dt=_utc(2026, 11, 16, 16, 30))
    assert ok
    # warmup=0：开盘即放行
    ok, _ = trading_hours.scan_allowed('US', warmup_minutes=0,
                                       dt=_utc(2026, 11, 16, 14, 31))
    assert ok
    # 未开盘/周末：一律不放行
    ok, reason = trading_hours.scan_allowed('US', warmup_minutes=0,
                                            dt=_utc(2026, 11, 16, 14, 0))
    assert not ok and reason == '非交易时段'
    ok, _ = trading_hours.scan_allowed('US', warmup_minutes=0,
                                       dt=_utc(2026, 11, 15, 15, 0))
    assert not ok


def test_minutes_since_open():
    assert trading_hours.minutes_since_open('US', _utc(2026, 11, 16, 15, 0)) == 30
    assert trading_hours.minutes_since_open('US', _utc(2026, 11, 16, 14, 29)) is None
    assert trading_hours.minutes_since_open('US', _utc(2026, 11, 15, 15, 0)) is None  # 周日


# ------------------------------------------------------------------ K 线会话过滤
def _row(dt):
    return [_ms(dt), 1.0, 1.0, 1.0, 1.0, 10.0]


def test_filter_session_candles_removes_off_session_rows():
    rows = [
        _row(_utc(2026, 11, 14, 15, 0)),   # 周六 10:00 ET -> 删除
        _row(_utc(2026, 11, 15, 20, 0)),   # 周日 15:00 ET -> 删除
        _row(_utc(2026, 11, 16, 14, 0)),   # 周一 09:00 ET（开盘前） -> 删除
        _row(_utc(2026, 11, 16, 14, 30)),  # 周一 09:30 ET -> 保留
        _row(_utc(2026, 11, 16, 18, 0)),   # 周一 13:00 ET -> 保留
        _row(_utc(2026, 11, 16, 21, 30)),  # 周一 16:30 ET（收盘后） -> 删除
    ]
    kept = trading_hours.filter_session_candles(rows, 'US')
    assert [row[0] for row in kept] == [rows[3][0], rows[4][0]]


def test_filter_session_candles_supports_override_windows():
    rows = [
        _row(_utc(2026, 11, 16, 15, 0)),  # 10:00 ET
        _row(_utc(2026, 11, 16, 16, 0)),  # 11:00 ET
        _row(_utc(2026, 11, 16, 18, 0)),  # 13:00 ET
    ]
    kept = trading_hours.filter_session_candles(rows, 'US', overrides={'US': [[600, 660]]})
    assert [row[0] for row in kept] == [rows[0][0]]


def test_filter_session_candles_passthrough_for_unknown_market():
    rows = [_row(_utc(2026, 11, 16, 3, 0))]
    assert trading_hours.filter_session_candles(rows, 'XX') == rows
    assert trading_hours.filter_session_candles([], 'US') == []
