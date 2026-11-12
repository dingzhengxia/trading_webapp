"""signals API 离线测试（MERGE_PLAN §8.8）：无 key 403；非法配置 400；GET 结构正确。

不连交易所、不启动扫描（TestClient 不进入 lifespan）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture(scope="module")
def client():
    # 不用上下文管理器：避免触发 lifespan（无网络副作用）
    from app.main import app
    return TestClient(app)


@pytest.fixture(scope="module")
def api_key():
    from app.config.config import load_settings
    key = (load_settings().get("app_access_key") or "").strip()
    assert key, "app_access_key 必须已配置"
    return key


@pytest.fixture
def no_real_save(monkeypatch):
    """拦截 save_settings，避免测试把配置写入真实 data/app.db。"""
    from app.config import config as app_config
    saved_calls = []

    def fake_save(current_config):
        saved_calls.append({k: v for k, v in current_config.items()
                            if str(k).startswith("signal_")})
        app_config._cached_settings = None
        return True

    monkeypatch.setattr(app_config, "save_settings", fake_save)
    return saved_calls


def test_get_signals_requires_api_key(client):
    assert client.get("/api/signals").status_code == 403


def test_scan_requires_api_key(client):
    assert client.post("/api/signals/scan").status_code == 403


def test_config_requires_api_key(client):
    assert client.post("/api/signals/config", json={"signal_scan_enabled": True}).status_code == 403


def test_get_signals_structure(client, api_key):
    response = client.get("/api/signals", headers={"X-API-KEY": api_key})
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"status", "signals", "config", "strategy", "push", "tracking"}
    assert set(data["tracking"]) == {"params", "open_positions", "trades", "paper_stats", "forward_stats"}
    assert data["tracking"]["params"]["sl_atr"] > 0
    # 策略参数持久化：来源标记 + 至少含策略表
    assert data["strategy"]["source"] in ("db", "file")
    assert "strategy_params" in data["strategy"]["config"]
    # status 结构（MERGE_PLAN §6）
    status = data["status"]
    for key in ("enabled", "last_scan_at", "next_scan_at", "scanned_symbols", "emitted_count",
                "error_count", "last_error", "running",
                "auto_trade_enabled", "last_auto_open"):
        assert key in status
    # 扫描循环未启动时 enabled 必须为 False（前端开关依赖该字段）
    assert status["enabled"] is False
    # 默认配置：扫描与自动开仓均关闭；信号钉钉推送子开关默认开启
    assert data["config"]["signal_scan_enabled"] is False
    assert data["config"]["signal_auto_trade_enabled"] is False
    assert data["config"]["signal_dingtalk_enabled"] is True
    # 推送状态：未配置 webhook 时 mock 环境下也不应抛错
    assert set(data["push"]) == {"dingtalk_configured", "dingtalk_enabled",
                                 "signal_dingtalk_enabled",
                                 "signal_push_volume_multiplier", "static_symbols"}
    assert data["push"]["signal_push_volume_multiplier"] >= 0


def test_config_rejects_unknown_key(client, api_key):
    response = client.post("/api/signals/config",
                           json={"not_signal_key": 1}, headers={"X-API-KEY": api_key})
    assert response.status_code == 400


def test_config_rejects_invalid_values(client, api_key):
    # 间隔低于最小值 30 -> 400（Pydantic 校验）
    response = client.post("/api/signals/config",
                           json={"signal_scan_interval_seconds": 5},
                           headers={"X-API-KEY": api_key})
    assert response.status_code == 400

    # 金额 <= 0 -> 400
    response = client.post("/api/signals/config",
                           json={"signal_auto_trade_value_usd": 0},
                           headers={"X-API-KEY": api_key})
    assert response.status_code == 400

    # 非法方向 -> 400
    response = client.post("/api/signals/config",
                           json={"signal_auto_trade_directions": ["up"]},
                           headers={"X-API-KEY": api_key})
    assert response.status_code == 400

    # 非法时间框架 -> 400
    response = client.post("/api/signals/config",
                           json={"signal_scan_timeframes": ["2x"]},
                           headers={"X-API-KEY": api_key})
    assert response.status_code == 400

    # 非法策略 -> 400
    response = client.post("/api/signals/config",
                           json={"signal_auto_trade_strategies": ["moon_shot"]},
                           headers={"X-API-KEY": api_key})
    assert response.status_code == 400


def test_config_accepts_valid_partial_update(client, api_key, no_real_save):
    response = client.post("/api/signals/config",
                           json={"signal_scan_interval_seconds": 600,
                                 "signal_auto_trade_confirmations": 2},
                           headers={"X-API-KEY": api_key})
    assert response.status_code == 200
    config = response.json()["config"]
    assert config["signal_scan_interval_seconds"] == 600
    assert config["signal_auto_trade_confirmations"] == 2
    assert no_real_save, "配置应经过 save_settings 持久化"


def test_static_symbols_are_normalized(client, api_key, no_real_save):
    """静态币种入库前统一 base 大写去重：' sol '、'SOL'、'BTC/USDT:USDT' -> SOL / BTC。"""
    response = client.post("/api/signals/config",
                           json={"signal_scan_static_symbols":
                                 [" sol ", "SOL", "btc/usdt:usdt", ""]},
                           headers={"X-API-KEY": api_key})
    assert response.status_code == 200
    assert response.json()["config"]["signal_scan_static_symbols"] == ["SOL", "BTC"]


def test_static_symbols_reject_invalid_chars(client, api_key, no_real_save):
    response = client.post("/api/signals/config",
                           json={"signal_scan_static_symbols": ["BT C"]},
                           headers={"X-API-KEY": api_key})
    assert response.status_code == 400


def test_auto_trade_toggle_roundtrip(client, api_key, no_real_save):
    response = client.post("/api/signals/auto-trade",
                           json={"enabled": True}, headers={"X-API-KEY": api_key})
    assert response.status_code == 200
    assert response.json() == {"enabled": True}

    # 恢复默认关闭
    response = client.post("/api/signals/auto-trade",
                           json={"enabled": False}, headers={"X-API-KEY": api_key})
    assert response.status_code == 200
    assert response.json() == {"enabled": False}


def test_auto_trade_rejects_missing_body(client, api_key):
    response = client.post("/api/signals/auto-trade",
                           json={}, headers={"X-API-KEY": api_key})
    assert response.status_code == 400


def test_clear_signals(client, api_key):
    response = client.post("/api/signals/clear", headers={"X-API-KEY": api_key})
    assert response.status_code == 200
    assert response.json() == {"cleared": True, "remaining": 0}


def test_scan_endpoint_offline(client, api_key, monkeypatch):
    """手动扫描允许提交（即使开关关闭）；替换共享 exchange，保证完全不触网。"""
    from app.signals import service as signal_service

    class _OfflineExchange:
        markets = {}

        async def fetch_tickers(self):
            return {}

        async def load_markets(self):
            return {}

    async def fake_shared_exchange():
        return _OfflineExchange()

    monkeypatch.setattr(signal_service, "get_shared_exchange", fake_shared_exchange)

    response = client.post("/api/signals/scan", headers={"X-API-KEY": api_key})
    assert response.status_code == 200
    assert response.json() == {"message": "扫描任务已提交"}


@pytest.fixture
def tmp_strategy_db(tmp_path, monkeypatch):
    """策略配置落库的隔离 DB，避免污染真实 data/app.db。"""
    from app.core import database
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    return tmp_path


def test_strategy_config_roundtrip(client, api_key, tmp_strategy_db):
    """POST 局部更新 -> 落库 -> GET 回读一致（下一轮扫描即生效）。"""
    response = client.post("/api/signals/strategy-config",
                           json={"strategy_params": {"ma_breakout": {"enabled": False}}},
                           headers={"X-API-KEY": api_key})
    assert response.status_code == 200
    config = response.json()["strategy"]["config"]
    assert config["strategy_params"]["ma_breakout"]["enabled"] is False
    assert isinstance(config["strategy_params"]["ma_breakout"]["ma_periods"], list)  # 深合并保留兄弟键

    data = client.get("/api/signals", headers={"X-API-KEY": api_key}).json()
    assert data["strategy"]["source"] == "db"
    assert data["strategy"]["config"]["strategy_params"]["ma_breakout"]["enabled"] is False


def test_strategy_config_reset(client, api_key, tmp_strategy_db):
    client.post("/api/signals/strategy-config",
                json={"strategy_params": {"ma_breakout": {"enabled": False}}},
                headers={"X-API-KEY": api_key})
    response = client.post("/api/signals/strategy-config", json={"reset": True},
                           headers={"X-API-KEY": api_key})
    assert response.status_code == 200
    assert response.json()["strategy"]["config"]["strategy_params"]["ma_breakout"]["enabled"] is True


def test_strategy_config_rejects_unknown(client, api_key, tmp_strategy_db):
    response = client.post("/api/signals/strategy-config",
                           json={"strategy_params": {"no_such_strategy": {"enabled": True}}},
                           headers={"X-API-KEY": api_key})
    assert response.status_code == 400


def test_strategy_config_requires_api_key(client):
    assert client.post("/api/signals/strategy-config",
                       json={"strategy_params": {"ma_breakout": {"enabled": False}}}).status_code == 403


def test_paper_config_bounds(client, api_key):
    """纸面出场参数有上下限：0 或越界 -> 400。"""
    assert client.post("/api/signals/config", json={"signal_paper_sl_atr": 0},
                       headers={"X-API-KEY": api_key}).status_code == 400
    assert client.post("/api/signals/config", json={"signal_paper_max_bars": 0},
                       headers={"X-API-KEY": api_key}).status_code == 400
    ok = client.post("/api/signals/config",
                     json={"signal_paper_enabled": True, "signal_paper_sl_atr": 1.2,
                           "signal_paper_tp_r": 2.5, "signal_paper_max_bars": 8},
                     headers={"X-API-KEY": api_key})
    assert ok.status_code == 200
    config = ok.json()["config"]
    assert config["signal_paper_enabled"] is True
    assert config["signal_paper_sl_atr"] == 1.2
    assert config["signal_paper_max_bars"] == 8
