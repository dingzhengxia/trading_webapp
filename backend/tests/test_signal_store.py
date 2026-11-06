"""SignalStore 离线测试：环形缓冲、方向过滤、统计快照、清空。"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.signals.signal_store import SignalStore  # noqa: E402


def _signal(i: int, direction="long", strategy="ema_cross", symbol="BTC"):
    return {
        "id": f"id-{i}", "created_at": f"2026-01-01T00:00:{i:02d}+00:00",
        "symbol": symbol, "full_symbol": f"{symbol}/USDC:USDC", "timeframe": "1h",
        "strategy": strategy, "strategy_index": 0, "direction": direction,
        "price": 100.0 + i, "title": f"t{i}", "message": "m", "dedupe_key": f"k{i}",
    }


def test_ring_buffer_cap():
    store = SignalStore(max_signals=3)
    for i in range(5):
        store.add(_signal(i))
    assert len(store) == 3
    recent = store.recent(10)
    # 环形缓冲保留最新 3 条，且按时间倒序
    assert [s["id"] for s in recent] == ["id-4", "id-3", "id-2"]


def test_recent_direction_filter_and_limit():
    store = SignalStore()
    for i in range(4):
        store.add(_signal(i, direction="long" if i % 2 == 0 else "short"))
    longs = store.recent(10, direction="long")
    assert [s["id"] for s in longs] == ["id-2", "id-0"]
    shorts = store.recent(1, direction="short")
    assert [s["id"] for s in shorts] == ["id-3"]


def test_snapshot_and_status_update():
    store = SignalStore()
    status = store.snapshot()
    assert status["running"] is False
    assert status["last_scan_at"] is None
    assert status["emitted_count"] == 0

    store.update_scan_status(running=True, scanned_symbols=42, last_error=None)
    store.add(_signal(1))
    store.update_auto_status(auto_trade_enabled=True, last_auto_open="2026-01-01T01:00:00+00:00")
    snap = store.snapshot()
    assert snap["running"] is True
    assert snap["scanned_symbols"] == 42
    assert snap["emitted_count"] == 1
    assert snap["auto_trade_enabled"] is True
    assert snap["last_auto_open"] == "2026-01-01T01:00:00+00:00"


def test_clear():
    store = SignalStore()
    store.add(_signal(1))
    store.add(_signal(2))
    assert len(store) == 2
    store.clear()
    assert len(store) == 0
    assert store.recent(10) == []


def test_add_is_defensive_copy():
    store = SignalStore()
    record = _signal(1)
    store.add(record)
    record["price"] = 99999
    assert store.recent(1)[0]["price"] == 101.0
