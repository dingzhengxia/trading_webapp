"""黑天鹅冷却 + 开仓前置闸门（离线测试）。

修复背景（2026-11-14 ETH）：15m 本根 K 线跌 1.27%（位移 23.97 > 阈值 20.37 且跌破
前 4 根低点）触发黑天鹅全平；3 分半后开仓计划又买 ETH，22:06:04 同一根 K 线的同一
信号把新仓再次全平——两次都是 -0.06% 的往返，白付双边手续费与滑点。

黑天鹅是状态型信号，所以在 K 线走完前任何新仓都会被立刻判定。因此：
  1. 黑天鹅全平 → 同币冷却（cooldown.note_emergency_flat）；
  2. 开仓前闸门 → 冷却中 / 正处于黑天鹅状态时拒绝下单（entry_gate.check_entry_allowed）。
"""
import asyncio
import time

import pytest

from app.core import database
from app.protection import cooldown, entry_gate


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "USER_SETTINGS_FILE", tmp_path / "user_settings.json")
    monkeypatch.setattr(database, "COIN_LISTS_FILE", tmp_path / "coin_lists.json")
    database.init_db()
    return tmp_path


CONF = {
    'enabled': True,
    'emergency_enabled': True,
    'emergency_cooldown_sec': 1800.0,
    'emergency_block_new_entries': True,
}


# ---------------------------------------------------------------- 冷却存储

def test_note_then_remaining(tmp_db):
    cooldown.note_emergency_flat('ETH/USDC:USDC', 'long', '结构性黑天鹅', CONF)
    left, reason = cooldown.cooldown_remaining('ETH/USDC:USDC', 'long', CONF)
    assert 1790 < left <= 1800
    assert '黑天鹅' in reason


def test_symbol_and_side_normalization(tmp_db):
    """交易所全名与基础币种、buy/long 必须命中同一条冷却。"""
    cooldown.note_emergency_flat('ETH/USDC:USDC', 'long', '黑天鹅', CONF)
    assert cooldown.cooldown_remaining('ETH', 'buy', CONF)[0] > 0
    # 反向不共用
    assert cooldown.cooldown_remaining('ETH', 'short', CONF)[0] == 0


def test_cooldown_zero_disables(tmp_db):
    conf = dict(CONF, emergency_cooldown_sec=0)
    cooldown.note_emergency_flat('ETH/USDC:USDC', 'long', '黑天鹅', conf)
    assert cooldown.cooldown_remaining('ETH', 'long', conf)[0] == 0


def test_expired_entry_pruned(tmp_db):
    database.set_value('signal_state', 'protection_emergency_cooldown',
                       {'ETH|long': {'ts': time.time() - 3600, 'reason': '旧'}})
    assert cooldown.cooldown_remaining('ETH', 'long', CONF)[0] == 0
    assert database.get_value('signal_state', 'protection_emergency_cooldown') == {}


def test_snapshot_lists_only_active(tmp_db):
    cooldown.note_emergency_flat('ETH', 'long', '黑天鹅', CONF)
    raw = database.get_value('signal_state', 'protection_emergency_cooldown')
    raw['OLD|short'] = {'ts': time.time() - 9999, 'reason': '旧'}
    database.set_value('signal_state', 'protection_emergency_cooldown', raw)
    snap = cooldown.snapshot(CONF)
    assert set(snap) == {'ETH|long'}
    assert snap['ETH|long']['remaining_sec'] > 0


# ---------------------------------------------------------------- 开仓闸门

class _FakeExchange:
    """闸门只把 exchange 透传给行情层，本测试不触网。"""


def _run(coro):
    return asyncio.run(coro)


def test_gate_allows_when_protection_disabled(tmp_db):
    cooldown.note_emergency_flat('ETH', 'long', '黑天鹅', CONF)
    allowed, reason = _run(entry_gate.check_entry_allowed(
        _FakeExchange(), 'ETH/USDC:USDC', 'buy', dict(CONF, enabled=False)))
    assert allowed and reason == ''


def test_gate_blocks_during_cooldown(tmp_db, monkeypatch):
    """冷却中必须拒绝，且不能再浪费一次行情请求。"""
    called = {'n': 0}

    async def _boom(*args, **kwargs):
        called['n'] += 1
        return False, None

    monkeypatch.setattr('app.protection.market_data._emergency_signal', _boom)
    cooldown.note_emergency_flat('ETH', 'long', '结构性黑天鹅', CONF)
    allowed, reason = _run(entry_gate.check_entry_allowed(
        _FakeExchange(), 'ETH/USDC:USDC', 'buy', CONF))
    assert not allowed
    assert '冷却' in reason and '黑天鹅' in reason
    assert called['n'] == 0


def test_gate_blocks_on_live_emergency(tmp_db, monkeypatch):
    async def _hit(exchange, symbol, side, conf, live_rows=None):
        return True, {'move': 23.97, 'threshold': 20.37, 'volume_crash': False}

    monkeypatch.setattr('app.protection.market_data._emergency_signal', _hit)
    allowed, reason = _run(entry_gate.check_entry_allowed(
        _FakeExchange(), 'ETH/USDC:USDC', 'buy', CONF))
    assert not allowed
    assert '黑天鹅' in reason and '23.97' in reason and '多' in reason


def test_gate_respects_switch_off(tmp_db, monkeypatch):
    async def _hit(*args, **kwargs):
        raise AssertionError('开关关闭时不应取行情')

    monkeypatch.setattr('app.protection.market_data._emergency_signal', _hit)
    conf = dict(CONF, emergency_block_new_entries=False)
    allowed, reason = _run(entry_gate.check_entry_allowed(
        _FakeExchange(), 'BTC/USDC:USDC', 'sell', conf))
    assert allowed and reason == ''


def test_gate_fail_open_on_error(tmp_db, monkeypatch):
    async def _boom(*args, **kwargs):
        raise RuntimeError('行情接口炸了')

    monkeypatch.setattr('app.protection.market_data._emergency_signal', _boom)
    allowed, reason = _run(entry_gate.check_entry_allowed(
        _FakeExchange(), 'BTC/USDC:USDC', 'sell', CONF))
    assert allowed and reason == ''


def test_first_blocker_helper(tmp_db, monkeypatch):
    async def _miss(*args, **kwargs):
        return False, None

    monkeypatch.setattr('app.protection.market_data._emergency_signal', _miss)
    cooldown.note_emergency_flat('ETH', 'long', '黑天鹅', CONF)
    assert '冷却' in _run(entry_gate.first_blocker(
        _FakeExchange(), 'ETH/USDC:USDC', 'long', CONF))
    assert _run(entry_gate.first_blocker(
        _FakeExchange(), 'BTC/USDC:USDC', 'long', CONF)) == ''
