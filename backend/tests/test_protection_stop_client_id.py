"""兜底 STOP 的单号：唯一性 + -4116 收敛 + 失败退避。

现场：同一笔 lot 改价是「先撤旧单再挂新单」，撤单没落地时用同一个
clientAlgoId 重挂会被币安回 -4116，而 _apply_stop 没有冷却 → 每 3 秒刷一条错误，
这一笔的止损永远推不上去。
"""
from __future__ import annotations

import asyncio

import pytest

from app.core import database
from app.protection import engine, lots, risk_model, runner
from app.protection.exits import _make_client_algo_id

SYMBOL = 'ETH/USDC:USDC'
STRUCT = (97.0, 95.0, 92.0)


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(database, 'USER_SETTINGS_FILE', tmp_path / 'user_settings.json')
    monkeypatch.setattr(database, 'COIN_LISTS_FILE', tmp_path / 'coin_lists.json')
    database.init_db()
    return tmp_path


def _conf() -> dict:
    conf = dict(risk_model.V2_DEFAULTS)
    conf['enabled'] = True
    conf['dry_run'] = False
    conf['stop_retry_cooldown_sec'] = 20.0
    return conf


def _state() -> dict:
    plan = risk_model.build_plan('long', 100.0, 2.0, STRUCT, _conf())
    state = risk_model.new_state('c1', 'long', 100.0, 10.0, plan, 1000.0)
    return lots.migrate(state, 'long', 100.0, 10.0, 1000.0)


def _bundle(state: dict) -> dict:
    lot = state['lots'][0]
    snap = risk_model.Snapshot(
        symbol=SYMBOL, side='long', entry=100.0, price=110.0, last_close=110.0,
        contracts=_f_lot(lot), atr=2.0, structure=STRUCT, closed_ts=0, now=2000.0,
        exchange_stop=0.0, exchange_checked=False, rebased=False,
        base_contracts=_f_lot(lot))
    return {
        'symbol': SYMBOL, 'side': 'long', 'state': state, 'snap': snap,
        'pos': {'symbol': SYMBOL, 'entryPrice': 100.0, 'contracts': _f_lot(lot),
                'info': {'positionSide': 'BOTH'}},
    }


def _f_lot(lot: dict) -> float:
    return float(lot.get('contracts') or 0.0)


def _act(lot: dict, price: float, tag: str = 'stop:move') -> dict:
    return {'type': 'stop', 'price': price, 'tag': tag, 'reason': '测试',
            'lot_id': lot['id'], '_lot': lot}


def _stop_order(lot: dict, trigger: float) -> dict:
    return {
        'algoId': 'a-1', 'clientAlgoId': _make_client_algo_id(SYMBOL, 'long', lot['id'], 1),
        'orderType': 'STOP_MARKET', 'algoStatus': 'NEW',
        'triggerPrice': trigger, 'side': 'SELL',
    }


def test_client_algo_id_is_unique_per_attempt():
    first = _make_client_algo_id(SYMBOL, 'long', 'a1b2c3d4', 1)
    second = _make_client_algo_id(SYMBOL, 'long', 'a1b2c3d4', 2)
    assert first != second
    # 尾部仍是 lot id，交易所上的单还能反查归属
    assert lots.algo_lot_id(first) == 'a1b2c3d4'
    assert lots.algo_lot_id(second) == 'a1b2c3d4'
    assert len(first) <= 36 and len(second) <= 36


def test_apply_stop_bumps_seq_on_every_attempt(tmp_db, monkeypatch):
    seqs = []

    async def fake_find(*_a, **_k):
        return []

    async def fake_create(_exchange, _symbol, _pos, _side, _price, _qty, _lot_id, _conf, seq=0):
        seqs.append(seq)
        return {'algoId': f'o-{seq}'}

    async def fake_cancel(*_a, **_k):
        return None

    monkeypatch.setattr(engine, '_find_stop_orders', fake_find)
    monkeypatch.setattr(engine, '_create_lot_stop', fake_create)
    monkeypatch.setattr(engine, '_cancel_stop_orders', fake_cancel)

    state = _state()
    lot = state['lots'][0]
    for price in (104.0, 105.0):
        asyncio.run(runner._apply_stop(
            object(), _conf(), _bundle(state), _act(lot, price)))

    assert seqs == [1, 2]
    assert lot['stop_seq'] == 2
    assert lot['stop'] == pytest.approx(105.0)


def test_duplicated_client_id_adopts_stop_already_on_exchange(tmp_db, monkeypatch):
    """-4116 说明这张单其实还在：价格已是目标值就直接收编，不再重犯。"""
    calls = {'find': 0}

    async def fake_find(*_a, **_k):
        calls['find'] += 1
        return [] if calls['find'] == 1 else [_stop_order(state['lots'][0], 104.0)]

    async def fake_create(*_a, **_k):
        raise RuntimeError('binanceusdm {"code":-4116,"msg":"ClientOrderId is duplicated."}')

    async def fake_cancel(*_a, **_k):
        raise AssertionError('已存在的等价止损单不应被撤掉')

    monkeypatch.setattr(engine, '_find_stop_orders', fake_find)
    monkeypatch.setattr(engine, '_create_lot_stop', fake_create)
    monkeypatch.setattr(engine, '_cancel_stop_orders', fake_cancel)

    state = _state()
    lot = state['lots'][0]
    # 不抛异常：否则 _execute 每轮都会记一条 error
    asyncio.run(runner._apply_stop(
        object(), _conf(), _bundle(state), _act(lot, 104.0)))

    assert lot['stop'] == pytest.approx(104.0)
    assert calls['find'] == 2


def test_duplicated_client_id_cancels_stale_stop_and_backs_off(tmp_db, monkeypatch):
    """残留的是旧价单：撤掉、不硬重试；冷却期内不再打交易所。"""
    creates = []
    cancels = []

    async def fake_find(*_a, **_k):
        return [] if not creates else [_stop_order(state['lots'][0], 98.0)]

    async def fake_create(*_a, **_k):
        creates.append(1)
        raise RuntimeError('binanceusdm {"code":-4116,"msg":"ClientOrderId is duplicated."}')

    async def fake_cancel(_exchange, _symbol, stops, _conf):
        cancels.extend(stops)

    monkeypatch.setattr(engine, '_find_stop_orders', fake_find)
    monkeypatch.setattr(engine, '_create_lot_stop', fake_create)
    monkeypatch.setattr(engine, '_cancel_stop_orders', fake_cancel)

    state = _state()
    lot = state['lots'][0]
    asyncio.run(runner._apply_stop(object(), _conf(), _bundle(state), _act(lot, 104.0)))
    assert len(creates) == 1
    assert len(cancels) == 1
    assert lot['stop'] is None

    # 冷却未到：这一轮必须直接返回，不能第二次打接口
    asyncio.run(runner._apply_stop(object(), _conf(), _bundle(state), _act(lot, 104.0)))
    assert len(creates) == 1
