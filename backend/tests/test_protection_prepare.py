"""runner._prepare 的接线测试：人工加仓/减仓必须走「状态演化」，不能重建整行。

覆盖 2026-11-15 的现场：ETH 减仓后加仓回补（仓位仍小于初始仓位），
旧实现完全看不见 → 计划一直按旧均价算，兜底 STOP 落到真实开仓价之下。
"""
from __future__ import annotations

import asyncio

import pandas as pd
import pytest

from app.core import database
from app.protection import engine, ledger, risk_model, runner

SYMBOL = 'ETH/USDC:USDC'


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "USER_SETTINGS_FILE", tmp_path / "user_settings.json")
    monkeypatch.setattr(database, "COIN_LISTS_FILE", tmp_path / "coin_lists.json")
    database.init_db()
    return tmp_path


@pytest.fixture
def wired(monkeypatch, tmp_db):
    """把 _prepare 需要的 IO 全部替掉，只保留决策与状态逻辑。"""
    df = pd.DataFrame({
        'low': [95.0] * 200,
        'high': [105.0] * 200,
        'close': [100.0] * 200,
    })

    async def fake_ohlcv(*_a, **_k):
        return [[0, 100, 105, 95, 100, 1.0]] * 200

    def fake_levels(_rows, _conf):
        return {'atr': 2.0, 'df': df, 'last_close': 100.0, 'closed_ts': 0}

    async def fake_price(*_a, **_k):
        return 100.0

    async def fake_stops(*_a, **_k):
        return []

    async def fake_emergency(*_a, **_k):
        return False, {}

    monkeypatch.setattr(engine, '_fetch_ohlcv', fake_ohlcv)
    monkeypatch.setattr(engine, '_strategy_levels_from_rows', fake_levels)
    monkeypatch.setattr(engine, '_find_stop_orders', fake_stops)
    monkeypatch.setattr(engine, '_emergency_signal', fake_emergency)
    monkeypatch.setattr(runner, '_price', fake_price)
    monkeypatch.setattr(runner, 'LAST_STOP_VERIFY', {})
    runner.V2.recent_actions.clear()
    return monkeypatch


def _pos(entry: float, contracts: float) -> dict:
    return {'symbol': SYMBOL, 'entryPrice': entry, 'contracts': contracts,
            'info': {'positionSide': 'BOTH'}}


def _run(conf, pos):
    return asyncio.run(runner._prepare(object(), conf, SYMBOL, 'long', pos))


def _conf() -> dict:
    conf = dict(risk_model.V2_DEFAULTS)
    conf['enabled'] = True
    conf['emergency_enabled'] = False
    conf['stop_verify_interval_sec'] = 0.0
    return conf


def test_prepare_creates_plan_on_first_sight(wired):
    conf = _conf()
    bundle = _run(conf, _pos(100.0, 10.0))
    assert bundle is not None
    state = bundle['state']
    assert state['plan']['entry'] == pytest.approx(100.0)
    assert state['size_anchor'] == pytest.approx(10.0)
    assert state['q_seen'] == pytest.approx(10.0)


def test_prepare_treats_entry_drift_as_add_not_new_cycle(wired):
    conf = _conf()
    _run(conf, _pos(100.0, 10.0))
    stored = ledger.load(SYMBOL, 'long')
    stored['tiers_done'] = [0]
    stored['stop'] = 94.0
    ledger.save(SYMBOL, 'long', stored)

    # 人工加仓：均价 100 → 104，仓位 10 → 14
    bundle = _run(conf, _pos(104.0, 14.0))
    state = bundle['state']
    assert state['plan']['entry'] == pytest.approx(104.0)
    assert state['plan']['rebase_count'] == 1
    # 进度保留：卖过的档不会被重置成「没卖过」
    assert state['tiers_done'] == [0]
    # 规模锚跟着加仓抬升，后续档位按新规模分批
    assert state['size_anchor'] == pytest.approx(14.0)
    # 灾难线跟着新均价走，永远在均价下方
    assert state['plan']['disaster_stop'] < 104.0
    assert bundle['snap'].rebased is True

    kinds = [e['kind'] for e in ledger.recent_events(20, symbol=SYMBOL)]
    assert 'rebase' in kinds


def test_prepare_keeps_plan_on_manual_reduce(wired):
    conf = _conf()
    _run(conf, _pos(100.0, 10.0))
    before = ledger.load(SYMBOL, 'long')
    plan_entry = before['plan']['entry']

    bundle = _run(conf, _pos(100.0, 6.0))
    state = bundle['state']
    assert state['plan']['entry'] == pytest.approx(plan_entry)  # 均价没变，计划不动
    assert state['contracts'] == pytest.approx(6.0)
    assert state['size_anchor'] == pytest.approx(10.0)          # 规模锚不缩
    assert bundle['snap'].rebased is False

    kinds = [e['kind'] for e in ledger.recent_events(20, symbol=SYMBOL)]
    assert 'intervention' in kinds


def test_prepare_does_not_flag_our_own_reduce_as_manual(wired):
    """我们自己减仓后 q_seen 立刻同步，下一轮不能误报「人工减仓」。"""
    conf = _conf()
    _run(conf, _pos(100.0, 10.0))
    state = ledger.load(SYMBOL, 'long')
    state['q_seen'] = 7.0        # 模拟 _apply_reduce 成交后的同步
    ledger.save(SYMBOL, 'long', state)

    _run(conf, _pos(100.0, 7.0))
    kinds = [e['kind'] for e in ledger.recent_events(20, symbol=SYMBOL)]
    assert 'intervention' not in kinds
