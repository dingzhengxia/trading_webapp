"""runner._prepare 的接线测试：人工加仓/减仓必须走「状态演化」，不能重建整行。

覆盖 2026-11-15 的现场：ETH 减仓后加仓回补（仓位仍小于初始仓位），
旧实现完全看不见 → 计划一直按旧均价算，兜底 STOP 落到真实开仓价之下。
"""
from __future__ import annotations

import asyncio
import time

import pandas as pd
import pytest

from app.core import database
from app.protection import engine, ledger, lots, risk_model, runner

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


def _run(conf, pos, pos_ts=None):
    # pos_ts 默认「刚刚拉到的快照」；传旧时间戳可模拟缓存里的过期持仓
    ts = time.time() if pos_ts is None else pos_ts
    return asyncio.run(runner._prepare(object(), conf, SYMBOL, 'long', pos, ts))


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


def test_prepare_add_creates_independent_lot_and_leaves_old_one_alone(wired):
    conf = _conf()
    _run(conf, _pos(100.0, 10.0))
    stored = ledger.load(SYMBOL, 'long')
    old_lot = stored['lots'][0]
    old_lot['tiers_done'] = [0]
    old_lot['stop'] = 94.0
    ledger.save(SYMBOL, 'long', stored)

    # 人工加仓：均价 100 → 104，仓位 10 → 14（反解本笔成交价 114）
    bundle = _run(conf, _pos(104.0, 14.0))
    state = bundle['state']
    assert len(state['lots']) == 2
    old = next(x for x in state['lots'] if x['id'] == old_lot['id'])
    new = next(x for x in state['lots'] if x['id'] != old_lot['id'])

    # 老笔：计划 / 进度 / 止损 / 规模全部原封不动
    assert old['plan']['entry'] == pytest.approx(100.0)
    assert old['tiers_done'] == [0]
    assert old['stop'] == pytest.approx(94.0)
    assert old['contracts'] == pytest.approx(10.0)
    # 新笔：按自己的成交价单独建计划
    assert new['entry'] == pytest.approx(114.0)
    assert new['plan']['entry'] == pytest.approx(114.0)
    assert new['plan']['disaster_stop'] < 114.0
    assert new['tiers_done'] == []
    assert new['contracts'] == pytest.approx(4.0)
    assert state['contracts'] == pytest.approx(14.0)

    kinds = [e['kind'] for e in ledger.recent_events(20, symbol=SYMBOL)]
    assert 'lot_add' in kinds
    assert 'rebase' not in kinds


def test_prepare_keeps_plan_on_manual_reduce(wired):
    conf = _conf()
    _run(conf, _pos(100.0, 10.0))
    before = ledger.load(SYMBOL, 'long')
    plan_entry = before['plan']['entry']

    bundle = _run(conf, _pos(100.0, 6.0))
    state = bundle['state']
    assert state['plan']['entry'] == pytest.approx(plan_entry)  # 均价没变，计划不动
    assert state['contracts'] == pytest.approx(6.0)
    assert state['lots'][0]['contracts'] == pytest.approx(6.0)
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


def test_prepare_ignores_quantity_drift_right_after_our_own_fill(wired, monkeypatch):
    """自己刚成交完（静默窗口内）：数量差不能判成人工加仓。

    现场：ETH 止盈卖掉 0.002，下一轮拿到成交前的旧快照 → 判成「加仓 +0.002」，
    凭空建了一笔 lot 并推送，再下一轮又判成「外部减仓」，来回横跳。
    """
    conf = _conf()
    _run(conf, _pos(100.0, 10.0))
    state = ledger.load(SYMBOL, 'long')
    state['q_seen'] = 8.0            # 模拟 _apply_reduce 成交后的同步
    state['self_trade_ts'] = time.time()
    ledger.save(SYMBOL, 'long', state)

    async def fake_fresh(*_a, **_k):
        return _pos(100.0, 10.0)

    monkeypatch.setattr(engine, '_position_fresh', fake_fresh)
    bundle = _run(conf, _pos(100.0, 10.0))
    assert len(bundle['state']['lots']) == 1
    assert bundle['state']['contracts'] == pytest.approx(10.0)
    kinds = [e['kind'] for e in ledger.recent_events(20, symbol=SYMBOL)]
    assert 'lot_add' not in kinds
    assert 'intervention' not in kinds


def test_prepare_refetches_position_older_than_our_own_fill(wired, monkeypatch):
    """快照早于自己的成交时刻：必须先取交易所真值，再判断加/减仓。"""
    conf = _conf()
    _run(conf, _pos(100.0, 10.0))
    state = ledger.load(SYMBOL, 'long')
    state['q_seen'] = 6.0
    state['self_trade_ts'] = 5000.0
    ledger.save(SYMBOL, 'long', state)

    async def fake_fresh(*_a, **_k):
        return _pos(100.0, 6.0)

    monkeypatch.setattr(engine, '_position_fresh', fake_fresh)
    bundle = _run(conf, _pos(100.0, 10.0), pos_ts=4000.0)

    assert bundle['state']['contracts'] == pytest.approx(6.0)
    assert len(bundle['state']['lots']) == 1
    kinds = [e['kind'] for e in ledger.recent_events(20, symbol=SYMBOL)]
    assert 'lot_add' not in kinds


def test_prepare_labels_own_stop_trigger_as_stop_fill(wired):
    """兜底 STOP 触发导致的减仓，不能报成「人工/外部减仓」。"""
    conf = _conf()
    _run(conf, _pos(100.0, 10.0))
    state = ledger.load(SYMBOL, 'long')
    state['lots'][0]['stop'] = 101.0      # 已在现价（100）另一侧，具备触发条件
    ledger.save(SYMBOL, 'long', state)

    _run(conf, _pos(100.0, 4.0))
    events = ledger.recent_events(20, symbol=SYMBOL)
    kinds = [e['kind'] for e in events]
    assert 'stop_fill' in kinds
    assert 'intervention' not in kinds
    assert any('兜底止损单已触发' in e['message'] for e in events)


def test_status_reports_per_lot_stop_and_progress(wired):
    """展示层要按 lot 聚合：每笔的止损与进度不上浮，页面就会永远显示「无止损」。"""
    conf = _conf()
    _run(conf, _pos(100.0, 10.0))
    state = ledger.load(SYMBOL, 'long')
    state['lots'][0]['stop'] = 96.5
    state['lots'][0]['tp_done'] = [0]
    second = lots.add_lot(state, 'long', 104.0, 4.0,
                          risk_model.build_plan('long', 104.0, 2.0, (97.0, 95.0, 92.0), conf),
                          2000.0)
    ledger.save(SYMBOL, 'long', state)

    row = next(r for r in runner.status()['positions'] if r['symbol'] == SYMBOL)
    assert row['stop_price'] == pytest.approx(96.5)   # 多头取最靠近现价的那条
    assert row['contracts'] == pytest.approx(14.0)
    assert row['entry_price'] == pytest.approx((100.0 * 10.0 + 104.0 * 4.0) / 14.0)
    assert row['tp1_done'] is True
    assert {x['id'] for x in row['lots']} == {state['lots'][0]['id'], second['id']}
