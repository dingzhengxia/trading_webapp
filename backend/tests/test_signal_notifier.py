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
