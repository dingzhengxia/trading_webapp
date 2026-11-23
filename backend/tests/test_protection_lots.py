"""每笔开仓独立账本：本地计划/进度/数量必须按 lot 隔离。"""
from __future__ import annotations

import pytest

from app.protection import lots, risk_model

CONF = dict(risk_model.V2_DEFAULTS)
STRUCT = (97.0, 95.0, 92.0)


def _plan(entry: float, atr: float = 2.0):
    return risk_model.build_plan('long', entry, atr, STRUCT, CONF)


def _legacy_state(entry=100.0, qty=10.0):
    plan = _plan(entry)
    state = risk_model.new_state('cycle', 'long', entry, qty, plan, 1000.0)
    state['tiers_done'] = [0]
    state['tp_done'] = [1]
    state['stop'] = 94.0
    state['peak'] = 106.0
    return state


def test_migrate_v2_state_into_one_independent_lot():
    old = _legacy_state()
    state = lots.migrate(old, 'long', 100.0, 10.0, 1000.0)

    assert state['version'] == lots.STATE_VERSION
    assert len(state['lots']) == 1
    lot = state['lots'][0]
    assert lot['entry'] == pytest.approx(100.0)
    assert lot['plan']['entry'] == pytest.approx(100.0)
    assert lot['tiers_done'] == [0]
    assert lot['tp_done'] == [1]
    assert lot['stop'] == pytest.approx(94.0)
    assert lot['peak'] == pytest.approx(106.0)


def test_add_lot_keeps_old_plan_progress_and_stop_untouched():
    state = lots.migrate(_legacy_state(), 'long', 100.0, 10.0, 1000.0)
    old = state['lots'][0]
    old_snapshot = (dict(old['plan']), list(old['tiers_done']), old['stop'], old['peak'])

    fresh = lots.add_lot(state, 'long', 110.0, 4.0, _plan(110.0), 2000.0)
    assert len(state['lots']) == 2
    assert fresh['entry'] == pytest.approx(110.0)
    assert fresh['plan']['tp_prices'] != old['plan']['tp_prices']
    assert (old['plan'], old['tiers_done'], old['stop'], old['peak']) == old_snapshot
    assert state['contracts'] == pytest.approx(14.0)


def test_external_reduce_is_allocated_pro_rata_without_changing_prices():
    state = lots.migrate(_legacy_state(), 'long', 100.0, 10.0, 1000.0)
    lots.add_lot(state, 'long', 110.0, 10.0, _plan(110.0), 2000.0)
    first, second = state['lots']
    first_tp = list(first['plan']['tp_prices'])
    second_tp = list(second['plan']['tp_prices'])

    removed = lots.allocate_reduce(state, 8.0)
    assert removed == []
    assert [x['contracts'] for x in state['lots']] == pytest.approx([6.0, 6.0])
    # 规模锚同比缩小，后续比例减仓的语义不漂移
    assert [x['size_anchor'] for x in state['lots']] == pytest.approx([6.0, 6.0])
    assert first['plan']['tp_prices'] == first_tp
    assert second['plan']['tp_prices'] == second_tp


def test_owned_reduce_only_touches_its_own_lot():
    state = lots.migrate(_legacy_state(), 'long', 100.0, 10.0, 1000.0)
    fresh = lots.add_lot(state, 'long', 110.0, 10.0, _plan(110.0), 2000.0)
    old = state['lots'][0]

    cleared = lots.apply_owned_reduce(state, fresh['id'], 2.5, [0], [2], 3000.0)
    assert cleared is False
    assert fresh['contracts'] == pytest.approx(7.5)
    assert fresh['tiers_done'] == [0] and fresh['tp_done'] == [2]
    assert old['contracts'] == pytest.approx(10.0)
    assert old['tiers_done'] == [0] and old['tp_done'] == [1]


def test_lot_view_writeback_does_not_leak_progress_between_lots():
    state = lots.migrate(_legacy_state(), 'long', 100.0, 10.0, 1000.0)
    fresh = lots.add_lot(state, 'long', 110.0, 4.0, _plan(110.0), 2000.0)
    old, new = state['lots']
    view = lots.lot_view(state, new)
    view['tiers_done'] = [3]
    view['peak'] = 999.0

    assert lots.writeback(new, {'tiers_done': [3], 'peak': 999.0}) is True
    assert new['tiers_done'] == [3] and new['peak'] == pytest.approx(999.0)
    assert old['tiers_done'] == [0] and old['peak'] == pytest.approx(106.0)


def test_algo_client_id_carries_full_lot_id():
    from app.protection.exits import _make_client_algo_id

    lot_id = 'a1b2c3d4'
    client_id = _make_client_algo_id('BTC/USDT:USDT', 'long', lot_id)
    assert lots.algo_lot_id(client_id) == lot_id
    assert len(lots.algo_lot_id(_make_client_algo_id('BTC/USDT:USDT', 'long'))) == 8


def test_stop_orders_group_by_lot_id():
    state = lots.migrate(_legacy_state(), 'long', 100.0, 10.0, 1000.0)
    first = lots.add_lot(state, 'long', 110.0, 4.0, _plan(110.0), 2000.0)
    stops = [
        {'clientAlgoId': f'PM_WS_SL_BTCUSDT_L_{first["id"][:8]}'},
        {'clientAlgoId': 'PM_WS_SL_BTCUSDT_L_legacy01'},
    ]
    grouped = lots.group_stops_by_lot(stops, state['lots'])
    assert [s['clientAlgoId'] for s in grouped[first['id']]] == [stops[0]['clientAlgoId']]
    assert grouped[None] == [stops[1]]


def test_sync_total_keeps_proportions_when_exchange_drifts():
    state = lots.migrate(_legacy_state(), 'long', 100.0, 10.0, 1000.0)
    lots.add_lot(state, 'long', 110.0, 10.0, _plan(110.0), 2000.0)
    lots.sync_total(state, 18.0)
    assert [x['contracts'] for x in state['lots']] == pytest.approx([9.0, 9.0])
