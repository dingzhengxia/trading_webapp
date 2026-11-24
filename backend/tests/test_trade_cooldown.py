# tests/test_trade_cooldown.py
"""全局开仓冷静期：操作聚合、连亏自动触发、冷静中拒单、到期惰性解除。

口径（用户定义）：一次「操作」= 一次批量开/平仓（时间窗聚合），
系统自动止损算一次，止盈（盈利）不算做错；冷静期内直接拒绝开单。
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import config as app_config  # noqa: E402
from app.core import database  # noqa: E402
from app.protection import trade_cooldown as tc  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """settings 表与内存缓存全部隔离到临时库（冷静状态落在 user settings）。"""
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "USER_SETTINGS_FILE", tmp_path / "u.json")
    monkeypatch.setattr(database, "COIN_LISTS_FILE", tmp_path / "c.json")
    database.init_db()
    monkeypatch.setattr(app_config, "_cached_settings", None)
    yield
    monkeypatch.setattr(app_config, "_cached_settings", None)


class _FakeExchange:
    """blocking_reason 冷静中不触达交易所；连亏检测走 monkeypatch 的 income。"""


def _income(ts_ms: int, pnl: float) -> dict:
    return {'income': str(pnl), 'time': ts_ms, 'incomeType': 'REALIZED_PNL'}


def _ts(minutes_ago: float = 0.0) -> int:
    dt = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return int(dt.timestamp() * 1000)


def _patch_income(monkeypatch, rows):
    async def _fake(exchange):
        return rows
    monkeypatch.setattr(tc, '_fetch_income_today', _fake)
    monkeypatch.setattr(tc, '_income_cache', {})  # 清缓存防串场


# ------------------------------------------------------------------ 聚合
def test_aggregate_merges_nearby_and_splits_distant():
    rows = [
        _income(_ts(10.0), 5.0),     # TP1 部分止盈
        _income(_ts(9.0), -30.0),    # 1 分钟后止损 → 同一操作，合计 -25
        _income(_ts(2.0), -8.0),     # 7 分钟后另一笔独立平仓 → 新操作
    ]
    ops = tc.aggregate_operations(rows)
    assert len(ops) == 2
    assert ops[0]['pnl'] == pytest.approx(-25.0)
    assert ops[1]['pnl'] == pytest.approx(-8.0)


def test_consecutive_losses_requires_all_losing_tail():
    ops = [{'pnl': -10.0}, {'pnl': 5.0}, {'pnl': -3.0}, {'pnl': -4.0}]
    assert tc.consecutive_losses(ops, 2) == ops[-2:]
    assert tc.consecutive_losses(ops, 3) is None      # 中间夹了盈利 → 不是连续
    assert tc.consecutive_losses([{'pnl': -1.0}], 2) is None  # 次数不足


# ------------------------------------------------------------------ 状态
def test_state_disabled_and_until_roundtrip():
    assert tc.cooldown_state() is None
    state = tc.open_cooldown('manual', 45)
    loaded = tc.cooldown_state()
    assert loaded is not None and loaded['minutes'] == 45
    assert loaded['triggered_by'] == 'manual'
    assert loaded['remaining_sec'] <= 45 * 60
    assert state['until'] is not None


def test_expired_state_is_none():
    tc.open_cooldown('manual', 1)
    future_past = datetime.now(timezone.utc) - timedelta(seconds=1)
    settings = app_config.load_settings()
    settings['trade_cooldown_until'] = future_past.isoformat()
    app_config.save_settings(settings)
    assert tc.cooldown_state() is None


# ------------------------------------------------------------------ 闸门
def test_blocking_reason_rejects_during_cooldown():
    tc.open_cooldown('manual', 60)
    reason = asyncio.run(tc.blocking_reason(_FakeExchange()))
    assert reason and '冷静期中' in reason
    # 直接拒绝，不排队：设置保持开启，等待到期或手动关闭
    assert bool(app_config.load_settings().get('trade_cooldown_enabled')) is True


def test_blocking_reason_releases_after_expiry(monkeypatch):
    tc.open_cooldown('manual', 1)
    settings = app_config.load_settings()
    settings['trade_cooldown_until'] = (datetime.now(timezone.utc)
                                        - timedelta(seconds=1)).isoformat()
    app_config.save_settings(settings)
    _patch_income(monkeypatch, [])  # 解除后走连亏检测：当日无平仓 → 放行
    assert asyncio.run(tc.blocking_reason(_FakeExchange())) is None
    assert bool(app_config.load_settings().get('trade_cooldown_enabled')) is False


def test_auto_triggers_after_two_losing_operations(monkeypatch):
    _patch_income(monkeypatch, [
        _income(_ts(30.0), -20.0),          # 操作1：止损
        _income(_ts(5.0), -12.0), _income(_ts(4.0), -6.0),  # 操作2：批量平仓两币合计亏损
    ])
    reason = asyncio.run(tc.blocking_reason(_FakeExchange()))
    assert reason and '自动进入冷静期' in reason and '连续 2 次' in reason
    settings = app_config.load_settings()
    assert settings['trade_cooldown_enabled'] is True
    assert settings['trade_cooldown_triggered_by'] == 'auto'
    # 同一冷静期内再开仓：走「冷静中」拒绝分支，不再重复统计
    reason2 = asyncio.run(tc.blocking_reason(_FakeExchange()))
    assert reason2 and '冷静期中' in reason2


def test_profit_operation_breaks_streak(monkeypatch):
    _patch_income(monkeypatch, [
        _income(_ts(30.0), -20.0),
        _income(_ts(5.0), 15.0),   # 止盈：盈利操作打断连亏
        _income(_ts(2.0), -3.0),
    ])
    assert asyncio.run(tc.blocking_reason(_FakeExchange())) is None
    assert bool(app_config.load_settings().get('trade_cooldown_enabled')) is False


def test_income_failure_passes(monkeypatch):
    async def _boom(exchange):
        raise RuntimeError('net down')
    monkeypatch.setattr(tc, '_fetch_income_today', _boom)
    assert asyncio.run(tc.blocking_reason(_FakeExchange())) is None


# ------------------------------------------------------------------ settings API 钩子
def test_settings_specials_open_sets_until_and_close_clears():
    from app.api.settings import _apply_cooldown_specials

    current = {'trade_cooldown_enabled': False, 'trade_cooldown_minutes': 60}
    updated = {'trade_cooldown_enabled': True}
    _apply_cooldown_specials(updated, current)
    assert updated['trade_cooldown_until'] and updated['trade_cooldown_triggered_by'] == 'manual'
    until = datetime.fromisoformat(updated['trade_cooldown_until'])
    assert timedelta(minutes=59) < until - datetime.now(timezone.utc) <= timedelta(minutes=60)

    updated = {'trade_cooldown_enabled': False}
    _apply_cooldown_specials(updated, current)
    assert updated['trade_cooldown_until'] is None and updated['trade_cooldown_triggered_by'] is None


def test_settings_specials_ignores_unrelated_update():
    from app.api.settings import _apply_cooldown_specials
    updated = {'leverage': 5}
    _apply_cooldown_specials(updated, {})
    assert 'trade_cooldown_until' not in updated
