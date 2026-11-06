"""信号分析模块离线测试（MERGE_PLAN §8.6 上半）：
fake 行情 + fake 策略产出 -> 结构化 SignalRecord（direction/strategy/price）；冷却去重生效。
"""
from __future__ import annotations

import asyncio
import queue
import sys
from pathlib import Path

import pandas as pd
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import database  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """隔离 DB 与 runtime 冷却状态。"""
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "USER_SETTINGS_FILE", tmp_path / "u.json")
    monkeypatch.setattr(database, "COIN_LISTS_FILE", tmp_path / "c.json")
    database.init_db()

    from app.signals import runtime
    # 原地清空（strategies 模块通过 from-import 持有同一 dict 对象引用）
    runtime.alerted_states.clear()
    # 清空全局队列，避免其他测试遗留数据
    while True:
        try:
            runtime.signal_queue.get_nowait()
        except queue.Empty:
            break
    yield


def _make_df(n_flat: int = 28):
    """构造会产生 SMA 突破看涨信号的 K 线（默认 30 根，1h 周期）。"""
    closes = [100.0] * n_flat + [99.0, 200.0]
    rows = []
    for i, close in enumerate(closes):
        rows.append({
            "timestamp": 1_700_000_000_000 + i * 3_600_000,
            "open": close, "high": close, "low": close, "close": close,
            "volume": 1000.0,
        })
    return pd.DataFrame(rows)


def _config():
    return {
        "market_settings": {"static_symbols": []},
        "strategy_params": {
            "trend_ema_short": {"fast": 12, "medium": 26, "long": 60},
            "trend_ema_long": {"fast": 26, "medium": 50, "long": 120},
        },
    }


def _drain_queue() -> list:
    from app.signals import runtime
    records = []
    while True:
        try:
            records.append(runtime.signal_queue.get_nowait())
        except queue.Empty:
            return records


def test_ma_breakout_emits_structured_record():
    from app.signals.analysis.strategies import check_ma_breakout

    config = _config()
    config["strategy_params"]["ma_breakout"] = {
        "enabled": True, "ma_type": "sma", "ma_periods": [7],
        "volume_confirm": False, "volume_multiplier": 1.5,
    }
    df = _make_df()
    check_ma_breakout(None, "BTC/USDC:USDC", "1h", config, df, config["strategy_params"]["ma_breakout"], 0)

    records = _drain_queue()
    assert len(records) == 1
    record = records[0]
    # 结构化字段（MERGE_PLAN §3.1/§3.3），不依赖标题关键字解析
    assert record["symbol"] == "BTC"
    assert record["full_symbol"] == "BTC/USDC:USDC"
    assert record["strategy"] == "ma_breakout"
    assert record["strategy_index"] == 0
    assert record["direction"] == "long"
    assert record["price"] == pytest.approx(200.0)
    assert record["timeframe"] == "1h"
    assert record["id"] and record["created_at"] and record["dedupe_key"]
    assert "突破" in record["title"]


def test_cooldown_dedup_blocks_second_signal():
    from app.signals.analysis.strategies import check_ma_breakout

    config = _config()
    config["strategy_params"]["ma_breakout"] = {
        "enabled": True, "ma_type": "sma", "ma_periods": [7], "volume_confirm": False,
    }
    df = _make_df()
    check_ma_breakout(None, "BTC/USDC:USDC", "1h", config, df, config["strategy_params"]["ma_breakout"], 0)
    assert len(_drain_queue()) == 1

    # 同 alert_key 在冷却期内 -> 不重复发射
    check_ma_breakout(None, "BTC/USDC:USDC", "1h", config, df, config["strategy_params"]["ma_breakout"], 0)
    assert _drain_queue() == []


def test_ema_cross_direction_metadata():
    from app.signals.analysis.strategies import check_ema_signals

    config = _config()
    ema_params = {"enabled": True, "period": 30, "volume_confirm": False,
                  "atr_period": 14, "atr_multiplier": 1}
    config["strategy_params"]["ema_cross"] = ema_params
    df = _make_df(n_flat=48)  # 需要 > EMA(30) 根数，保证 prev 行的 EMA 非 NaN
    # 前高后低结构：EMA(30) 上穿后有效突破 -> long
    check_ema_signals(None, "ETH/USDC:USDC", "1h", config, df, ema_params, 2)

    records = _drain_queue()
    assert records, "应产生至少一个结构化信号"
    for record in records:
        assert record["strategy"] == "ema_cross"
        assert record["direction"] in ("long", "short")
        assert record["symbol"] == "ETH"
        assert record["price"] == pytest.approx(200.0)


def test_level_breakout_emits_structured_record():
    """level_breakout（自动开仓白名单策略）必须能实际发出信号。

    原 monitor 版本模板引用 {original_type}/{closest_res[...]}/{current[...]} 但
    template_data 为空，format 抛 KeyError 导致信号永远无法发出 —— 本测试守护该修复。
    """
    from app.signals.analysis.strategies import check_level_breakout

    config = _config()
    config["strategy_params"]["level_breakout"] = {
        "enabled": True, "volume_confirm": False, "volume_multiplier": 1.5,
        "level_detection": {"swing_pivots": {"enabled": False}, "rolling_pivots": {"enabled": True}},
        "breakout_period": 10, "volume_ma_period": 20,
        "atr_period": 14, "atr_multiplier_breakout": 0.1,
    }
    # 前期箱体 100 -> 插针 80 -> 收盘 200：向上突破箱体顶部（近期前高/箱体顶部为阻力）
    closes = [100.0] * 28 + [99.0, 200.0]
    highs = [100.5] * 28 + [100.5, 200.0]
    lows = [99.5] * 28 + [80.0, 200.0]
    volumes = [1000.0] * 29 + [5000.0]
    df = pd.DataFrame([{"timestamp": 1_700_000_000_000 + i * 3_600_000,
                        "open": c, "high": h, "low": l, "close": c, "volume": v}
                       for i, (c, h, l, v) in enumerate(zip(closes, highs, lows, volumes))])

    check_level_breakout(None, "SOL/USDC:USDC", "1h", config, df,
                         config["strategy_params"]["level_breakout"], 0)

    records = [r for r in _drain_queue() if r["strategy"] == "level_breakout"]
    assert records, "level_breakout 应产生结构化信号（模板修复后）"
    record = records[0]
    assert record["direction"] in ("long", "short", "neutral")
    assert record["symbol"] == "SOL"
    assert record["price"] is not None


def test_emit_signal_thread_safety_smoke():
    """emit_signal 可从普通线程调用（策略在线程池执行）。"""
    import threading
    from app.signals import runtime

    def worker():
        runtime.emit_signal(symbol="SOL/USDC:USDC", full_symbol="SOL/USDC:USDC",
                            timeframe="4h", strategy="level_breakout", strategy_index=1,
                            direction="short", price=42.5, title="t", message="m",
                            dedupe_key="k-thread")

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    records = _drain_queue()
    assert len(records) == 1
    assert records[0]["symbol"] == "SOL"
    assert records[0]["direction"] == "short"
    assert records[0]["strategy_index"] == 1


def test_alert_states_persist_to_sqlite():
    """冷却状态持久化走 SQLite signal_state 表（替代 signal_cooldown.json）。"""
    from datetime import datetime, timedelta, timezone
    from app.signals import runtime

    runtime.alerted_states = {"BTC_1h_MA": datetime.now(timezone.utc) + timedelta(minutes=30)}
    runtime.save_alert_states()

    assert database.get_value("signal_state", "alerted_states") is not None

    runtime.alerted_states = {}
    runtime.load_alert_states()
    assert "BTC_1h_MA" in runtime.alerted_states
