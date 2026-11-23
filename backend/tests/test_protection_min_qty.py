"""数量精度：仓位小到拆不动时，不能每轮把必然被拒的单发出去。

现场：BTC 0.001 / BNB 0.04 这类仓位，分批止盈算出 0.0002 张，币安回
「must be greater than minimum amount precision」，而止盈/止损是每轮重新算的，
于是每 3 秒报一次同样的错、档位永远不前进。
"""
from __future__ import annotations

import asyncio

import pytest

from app.core import database
from app.protection import engine, ledger, lots, risk_model, runner

SYMBOL = 'ETH/USDC:USDC'
STRUCT = (97.0, 95.0, 92.0)


class _Exchange:
    """只有元数据的最小假交易所：最小下单量 0.01。"""

    def __init__(self) -> None:
        self.create_calls = 0

    def market(self, _symbol):
        return {'limits': {'amount': {'min': 0.01}}}

    def amount_to_precision(self, _symbol, amount):
        return str(amount)


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
    conf['min_qty_retry_cooldown_sec'] = 300.0
    return conf


def _state(qty: float) -> dict:
    plan = risk_model.build_plan('long', 100.0, 2.0, STRUCT, _conf())
    state = risk_model.new_state('c1', 'long', 100.0, qty, plan, 1000.0)
    return lots.migrate(state, 'long', 100.0, qty, 1000.0)


def _bundle(state: dict, lot: dict) -> dict:
    snap = risk_model.Snapshot(
        symbol=SYMBOL, side='long', entry=100.0, price=110.0, last_close=110.0,
        contracts=float(lot['contracts']), atr=2.0, structure=STRUCT,
        closed_ts=0, now=2000.0, exchange_stop=0.0, exchange_checked=False,
        rebased=False, base_contracts=float(lot['contracts']))
    return {'symbol': SYMBOL, 'side': 'long', 'state': state, 'snap': snap,
            'pos': {'symbol': SYMBOL, 'entryPrice': 100.0,
                    'contracts': float(lot['contracts']),
                    'info': {'positionSide': 'BOTH'}}}


def test_stop_skips_lot_smaller_than_min_amount(tmp_db, monkeypatch):
    created = []

    async def fake_find(*_a, **_k):
        return []

    async def fake_create(*_a, **_k):
        created.append(1)

    monkeypatch.setattr(engine, '_find_stop_orders', fake_find)
    monkeypatch.setattr(engine, '_create_lot_stop', fake_create)

    state = _state(10.0)
    dust = lots.add_lot(state, 'long', 104.0, 0.004,
                        risk_model.build_plan('long', 104.0, 2.0, STRUCT, _conf()), 2000.0)
    act = {'type': 'stop', 'price': 96.0, 'tag': 'stop:move', 'reason': '测试',
           'lot_id': dust['id'], '_lot': dust}
    asyncio.run(runner._apply_stop(_Exchange(), _conf(), _bundle(state, dust), act))

    assert created == []
    skips = [e for e in ledger.recent_events(10, symbol=SYMBOL) if e['kind'] == 'skip']
    assert len(skips) == 1 and '最小下单量' in skips[0]['message']

    # 冷却期内不再打接口、也不再刷第二条事件
    asyncio.run(runner._apply_stop(_Exchange(), _conf(), _bundle(state, dust), act))
    assert created == []
    assert len([e for e in ledger.recent_events(10, symbol=SYMBOL)
                if e['kind'] == 'skip']) == 1


def test_reduce_skips_tier_below_min_amount(tmp_db, monkeypatch):
    async def fake_two_source(*_a, **_k):
        return True, {}

    async def fake_fresh(*_a, **_k):
        return {'symbol': SYMBOL, 'entryPrice': 100.0, 'contracts': 0.004,
                'info': {'positionSide': 'BOTH'}}

    async def no_order(*_a, **_k):
        raise AssertionError('低于最小下单量的减仓不应发到交易所')

    monkeypatch.setattr(engine, '_two_source_price_ok', fake_two_source)
    monkeypatch.setattr(engine, '_position_fresh', fake_fresh)
    monkeypatch.setattr(engine, '_cancel_bot_reduce_orders', no_order)
    monkeypatch.setattr(engine, '_limit_reduce_with_maker_retry', no_order)

    state = _state(0.004)
    lot = state['lots'][0]
    bundle = _bundle(state, lot)
    act = {'type': 'reduce', 'ratio': 0.2, 'qty': 0.0008, 'tps': [0],
           'tag': 'tp:1', 'reason': '分批止盈 TP1', 'lot_id': lot['id'], '_lot': lot}

    asyncio.run(runner._apply_reduce(_Exchange(), _conf(), bundle, act))

    skips = [e for e in ledger.recent_events(10, symbol=SYMBOL) if e['kind'] == 'skip']
    assert len(skips) == 1
    assert '低于交易所最小下单量' in skips[0]['message']
    # 档位没有被标记成已完成，仓位也没被扣
    assert lot['tp_done'] == []
    assert lot['contracts'] == pytest.approx(0.004)
