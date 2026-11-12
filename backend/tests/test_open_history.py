# backend/tests/test_open_history.py
"""开仓记录（open_history）单元测试：落库、倒序、环形上限、坏数据容错。"""
from __future__ import annotations

import pytest

from app.core import database
from app.core.open_history import HISTORY_KEY, MAX_RECORDS, get_history, record_batch


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "USER_SETTINGS_FILE", tmp_path / "user_settings.json")
    monkeypatch.setattr(database, "COIN_LISTS_FILE", tmp_path / "coin_lists.json")
    database.init_db()


def test_record_batch_persists_snapshot_and_items(tmp_db):
    rec = record_batch(
        'plan', '自动开仓',
        items=[{'coin': 'AAPL', 'side': 'buy', 'target_value': 2000.0, 'success': True},
               {'coin': 'AMZN', 'side': 'buy', 'target_value': 500.0, 'success': False,
                'error': '找不到交易对'}],
        snapshot={'long_coin_list': ['AAPL', 'AMZN'], 'total_long_position_value': 5000},
        allocations={'long': {'AAPL': 2000.0, 'AMZN': 500.0}})
    assert rec is not None
    assert rec['summary'] == {'total': 2, 'success': 1, 'failed': 1}

    history = get_history()
    assert len(history) == 1
    assert history[0]['source'] == 'plan'
    assert history[0]['snapshot']['long_coin_list'] == ['AAPL', 'AMZN']
    assert history[0]['allocations']['long']['AMZN'] == 500.0
    assert history[0]['items'][1]['error'] == '找不到交易对'


def test_empty_items_not_recorded(tmp_db):
    assert record_batch('plan', '自动开仓', items=[]) is None
    assert get_history() == []


def test_history_sorted_desc_and_limit(tmp_db):
    for i in range(5):
        rec = record_batch('manual', '手动交易', items=[{'coin': 'BTC', 'success': True}])
        assert rec is not None
        # 手工回拨时间戳，制造可排序的时间差
        batches = database.get_value('open_history', HISTORY_KEY)
        batches[-1]['ts'] = 1_700_000_000_000 + i * 1000
        database.set_value('open_history', HISTORY_KEY, batches)

    history = get_history(limit=3)
    assert len(history) == 3
    timestamps = [h['ts'] for h in history]
    assert timestamps == sorted(timestamps, reverse=True)
    assert timestamps[0] == 1_700_000_004_000  # 最新在前


def test_ring_buffer_prunes_oldest(tmp_db):
    for i in range(MAX_RECORDS + 10):
        record_batch('signal', '信号自动开仓', items=[{'coin': 'BTC', 'success': True}])
    history = get_history(limit=MAX_RECORDS)
    assert len(history) == MAX_RECORDS
    # 最旧的 10 条已被淘汰：剩余记录数等于上限
    all_batches = database.get_value('open_history', HISTORY_KEY)
    assert len(all_batches) == MAX_RECORDS


def test_corrupted_storage_returns_empty(tmp_db):
    database.set_value('open_history', HISTORY_KEY, "not-a-list")
    assert get_history() == []
    # 写入坏记录也不影响读取
    record_batch('plan', '自动开仓', items=[{'coin': 'BTC', 'success': True}])
    database.set_value('open_history', HISTORY_KEY,
                       [None, "junk", {'id': 'x', 'ts': 'bad', 'items': []}])
    assert get_history()[0]['id'] == 'x'
