"""策略配置持久化测试：signal_config.json -> SQLite（离线，不触网）。

覆盖：
- 首次加载从文件播种到 DB，之后 DB 覆盖文件（容器重建不回滚线上参数）；
- 深合并局部更新、未知策略校验、reset 重新播种；
- 配置文件缺失/损坏时兜底；
- 策略缺陷回归：level_breakout 测试分支受 alert_on_test / volume_confirm 控制；
  RSI 背离必须是「枢轴对枢轴 + 最小 RSI 差」。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import database  # noqa: E402
from app.signals import config_store  # noqa: E402
from app.signals.analysis import strategies  # noqa: E402

FILE_CONFIG = {
    "config_version": 2,
    "market_settings": {"timeframes": ["1h", "4h"], "dynamic_scan": {"top_n_for_signals": 100}},
    "strategy_params": {
        "ma_breakout": {"enabled": True, "ma_periods": [25, 99], "volume_multiplier": 2.0},
        "level_breakout": {"enabled": True, "alert_on_test": False},
    },
}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """独立 DB + 独立配置文件。"""
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    path = tmp_path / "signal_config.json"
    path.write_text(json.dumps(FILE_CONFIG), encoding="utf-8")
    monkeypatch.setattr(config_store, "SIGNAL_CONFIG_FILE", str(path))
    return path


def test_first_load_seeds_database(isolated):
    config = config_store.load_signal_config()
    assert config["strategy_params"]["ma_breakout"]["ma_periods"] == [25, 99]
    assert config_store.config_source() == "db"
    stored = database.get_value("signal_state", "strategy_config", None)
    assert stored["strategy_params"]["ma_breakout"]["enabled"] is True


def test_db_wins_over_file_after_update(isolated):
    config_store.update_signal_config(
        {"strategy_params": {"ma_breakout": {"enabled": False}}})
    # 文件（新镜像）里的值不能覆盖线上调过的参数
    isolated.write_text(json.dumps({**FILE_CONFIG, "config_version": 3}), encoding="utf-8")
    config = config_store.load_signal_config()
    assert config["strategy_params"]["ma_breakout"]["enabled"] is False
    assert config["strategy_params"]["ma_breakout"]["volume_multiplier"] == 2.0  # 深合并保留兄弟键


def test_validate_rejects_unknown_strategy(isolated):
    config_store.load_signal_config()
    with pytest.raises(ValueError):
        config_store.update_signal_config({"strategy_params": {"no_such": {"enabled": True}}})
    with pytest.raises(ValueError):
        config_store.update_signal_config({"market_settings": {"timeframes": ["1d"]}})


def test_validate_rejects_bad_shape(isolated):
    config_store.load_signal_config()
    with pytest.raises(ValueError):
        config_store.update_signal_config({"strategy_params": {"ma_breakout": "off"}})


def test_reset_reseeds_from_file(isolated):
    config_store.update_signal_config({"strategy_params": {"ma_breakout": {"enabled": False}}})
    config = config_store.reset_signal_config()
    assert config["strategy_params"]["ma_breakout"]["enabled"] is True
    assert config_store.load_signal_config()["strategy_params"]["ma_breakout"]["enabled"] is True


def test_missing_file_falls_back_to_fallback_config(isolated, monkeypatch):
    monkeypatch.setattr(config_store, "SIGNAL_CONFIG_FILE", str(isolated.parent / "missing.json"))
    config = config_store.load_signal_config()
    assert config["strategy_params"] == {}
    assert config_store.config_source() == "file"  # 兜底配置不下发到 DB


# ------------------------------------------------------------------ 策略回归
def _df_with_swing_high():
    """构造：上行到 120 的摆动高点后回落，最后一根插针摸到前高但未突破。"""
    rows = []
    closes = [100 + i * 1.4 for i in range(15)] + [120.0]
    closes += [120 - (i - 15) * 0.6 for i in range(16, 40)]
    for i, close in enumerate(closes):
        high = close + 0.5
        low = close - 0.5
        if i == len(closes) - 1:  # 最后一根：插针到 120.6（越过前高 120.5），收盘仍在下方
            high, close = 120.6, 119.4
        rows.append({"timestamp": i * 3600_000, "open": close - 0.2, "high": high,
                     "low": low, "close": close, "volume": 1000.0})
    return pd.DataFrame(rows)


def test_level_test_branch_respects_alert_on_test(monkeypatch):
    calls = []
    monkeypatch.setattr(strategies, "_prepare_and_send_notification",
                        lambda *a, **k: calls.append(a[4]))

    df = _df_with_swing_high()
    strategies.check_level_breakout("BTC/USDT:USDT", "1h", {"strategy_params": {}}, df,
                                    {"alert_on_test": False, "volume_confirm": True})
    assert calls == []

    strategies.check_level_breakout("BTC/USDT:USDT", "1h", {"strategy_params": {}}, df,
                                    {"alert_on_test": True, "volume_confirm": True})
    assert len(calls) == 1
    assert calls[0]["direction"] == "neutral"
    assert calls[0]["volume_must_confirm"] is True  # 不再硬编码 False


def _rsi_frame(prices, rsis):
    return pd.DataFrame({
        "timestamp": [i * 3600_000 for i in range(len(prices))],
        "open": prices, "high": [p + 0.5 for p in prices], "low": [p - 0.5 for p in prices],
        "close": prices, "rsi": rsis,
    })


def _top_divergence_frame(last_close=125.0, last_rsi=60.0):
    prices = [100 + i * 1.4 for i in range(15)] + [120.0]
    prices += [120 - (i - 15) * 0.6 for i in range(16, 39)]
    prices.append(last_close)
    rsis = [55.0] * len(prices)
    rsis[15] = 70.0
    rsis[-1] = last_rsi
    return _rsi_frame(prices, rsis)


def test_rsi_divergence_detects_pivot_divergence():
    assert strategies.detect_rsi_divergence(_top_divergence_frame(), 60, 5, 5.0) == "top"


def test_rsi_divergence_requires_min_gap():
    """RSI 只低 2 点不算背离（旧实现会误报）。"""
    assert strategies.detect_rsi_divergence(_top_divergence_frame(last_rsi=68.0), 60, 5, 5.0) is None


def test_rsi_divergence_requires_new_high():
    assert strategies.detect_rsi_divergence(_top_divergence_frame(last_close=118.0), 60, 5, 5.0) is None


# ------------------------------------------------ 量能：只记录不拦截（volume_filter_mode）
def _flat_df():
    return pd.DataFrame({
        "timestamp": [i * 3600_000 for i in range(5)],
        "open": [100.0] * 5, "high": [101.0] * 5,
        "low": [99.0] * 5, "close": [100.0] * 5, "volume": [10.0] * 5,
    })


def _run_volume_gate(mode, monkeypatch):
    """用低量能（0.4x）跑统一出口，返回实际发出的信号。"""
    emitted = []
    monkeypatch.setattr(strategies, "is_realtime_volume_over", lambda *a, **k: (False, "vol", 0.4))
    monkeypatch.setattr(strategies, "emit_signal", lambda **kw: emitted.append(kw))
    monkeypatch.setattr(strategies, "save_alert_states", lambda: None)
    strategies.alerted_states.pop("BTCUSDT_1h_TEST", None)
    config = {
        "app_settings": {"volume_filter_mode": mode},
        "market_settings": {"static_symbols": ["ETH"]},
        "strategy_params": {},
    }
    info = {
        "log_name": "TEST", "strategy_name": "ma_breakout", "strategy_index": 0,
        "direction": "long", "alert_key": "BTCUSDT_1h_TEST",
        "volume_must_confirm": True, "fallback_multiplier": 2.0,
        "title_template": "T {vol_label}", "message_template": "{trend_message}{vol_text}",
        "template_data": {},
    }
    strategies._prepare_and_send_notification(config, "BTC/USDT:USDT", "1h", _flat_df(), info)
    return emitted


def test_volume_filter_record_keeps_signal(monkeypatch):
    """record 模式：量能不足也发信号，倍数只进记录与正文。"""
    emitted = _run_volume_gate("record", monkeypatch)
    assert len(emitted) == 1
    assert emitted[0]["volume_ratio"] == 0.4
    assert emitted[0]["title"] == "T"  # 「量能不足」不再写进标题


def test_volume_filter_block_drops_signal(monkeypatch):
    """默认 block 模式保持旧行为，避免存量配置语义静默变化。"""
    assert _run_volume_gate("block", monkeypatch) == []
