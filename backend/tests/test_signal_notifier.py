# backend/tests/test_signal_notifier.py
"""币种信号钉钉推送（Phase 3 补链）的格式与开关单测。"""
import pytest

from app.signals import notifier


def _rec(**overrides):
    record = {
        'id': 'abc',
        'symbol': 'BTC',
        'full_symbol': 'BTC/USDT:USDT',
        'timeframe': '1h',
        'strategy': 'ema_cross',
        'strategy_index': 0,
        'direction': 'long',
        'price': 43210.5,
        'title': '🚀 EMA 放量金叉: BTC/USDT:USDT (1h)',
        'message': '**当前趋势**: 📈 上升',
        'dedupe_key': 'k',
    }
    record.update(overrides)
    return record


def test_format_single_keeps_original_title():
    title, text = notifier.format_signal_batch([_rec()])
    assert title == '🚀 EMA 放量金叉: BTC/USDT:USDT (1h)'
    assert '### 🔔 币种信号 · 1 条' in text
    assert '🔴 做多' in text
    assert 'ema_cross' in text
    assert '43,210.50' in text


def test_format_batch_merges_into_one_message():
    title, text = notifier.format_signal_batch([
        _rec(),
        _rec(symbol='ETH', direction='short', price=0.5234,
             title='📉 跌破支撑: ETH/USDT:USDT (4h)'),
    ])
    assert title == '🔔 币种信号 × 2'
    assert text.count('---') == 1
    assert '🟢 做空' in text
    assert '0.5234' in text


def test_format_truncates_long_body():
    title, text = notifier.format_signal_batch(
        [_rec(message='x' * (notifier.MAX_ITEM_CHARS + 500))])
    assert len(text) < notifier.MAX_ITEM_CHARS + 500
    assert text.endswith('…')


@pytest.mark.parametrize('dingtalk_enabled,signal_enabled,expected', [
    (True, True, True),
    (True, False, False),
    (False, True, False),
])
def test_is_enabled_switches(monkeypatch, dingtalk_enabled, signal_enabled, expected):
    monkeypatch.setenv('DINGTALK_WEBHOOK_URL', 'https://example.com/robot/send')
    assert notifier.is_enabled({
        'dingtalk_enabled': dingtalk_enabled,
        'signal_dingtalk_enabled': signal_enabled,
    }) is expected


def test_is_enabled_without_webhook(monkeypatch):
    monkeypatch.delenv('DINGTALK_WEBHOOK_URL', raising=False)
    assert notifier.is_enabled({'dingtalk_enabled': True, 'signal_dingtalk_enabled': True}) is False


def test_signal_switch_defaults_on_for_old_settings(monkeypatch):
    """老库没有 signal_dingtalk_enabled 键时应视为开启（只看总开关 + webhook）。"""
    monkeypatch.setenv('DINGTALK_WEBHOOK_URL', 'https://example.com/robot/send')
    assert notifier.is_enabled({'dingtalk_enabled': True}) is True


# ------------------------------------------------------------------ 推送量能过滤

_SETTINGS = {'signal_scan_static_symbols': ['BTC', 'ETH'], 'signal_push_volume_multiplier': 2.0}


def test_static_symbols_always_pushed():
    records = [_rec(), _rec(volume_ratio=0.3), _rec(volume_ratio=None)]
    kept = notifier.filter_for_push(records, _SETTINGS)
    assert len(kept) == 3  # BTC 是静态币，无论量能都推


def test_non_static_requires_volume_ratio():
    records = [
        _rec(symbol='DOGE', volume_ratio=2.5),   # 达标 -> 推
        _rec(symbol='DOGE', volume_ratio=1.9),   # 未达标 -> 过滤
        _rec(symbol='DOGE', volume_ratio=None),  # 无法计算 -> 过滤
    ]
    kept = notifier.filter_for_push(records, _SETTINGS)
    assert len(kept) == 1
    assert kept[0]['volume_ratio'] == 2.5


def test_multiplier_zero_disables_filter():
    kept = notifier.filter_for_push(
        [_rec(symbol='DOGE', volume_ratio=None)],
        {'signal_scan_static_symbols': [], 'signal_push_volume_multiplier': 0},
    )
    assert len(kept) == 1


def test_item_shows_volume_ratio():
    _, text = notifier.format_signal_batch([_rec(volume_ratio=3.2)])
    assert '`3.2x`' in text
    # inf 与缺失不显示
    _, text2 = notifier.format_signal_batch([_rec(volume_ratio=float('inf'))])
    assert '`inf' not in text2 and 'x`' not in text2.replace('43,210.50', '')
