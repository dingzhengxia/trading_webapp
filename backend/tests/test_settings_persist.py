"""选币/设置持久化回归测试（离线）：POST /api/settings 后 GET 必须读回同一份值。

背景：用户反馈「控制面板选完币种，刷新页面就没了」。这条链路是
前端 SmartSelect -> settingsStore.saveGeneralSettings -> POST /api/settings
-> settings 表 -> GET /api/settings。本测试锁定后端这一段：任何一环丢键都会红。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import config as app_config
from app.core import database

TEST_KEY = "offline-test-access-key"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """临时库 + 固定访问密钥的 TestClient（不进 lifespan，不联网）。"""
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setitem(app_config.DEFAULT_CONFIG, "app_access_key", TEST_KEY)
    database.init_db()
    app_config._cached_settings = None

    from app.main import app

    yield TestClient(app)

    app_config._cached_settings = None


def _get_settings(client: TestClient) -> dict:
    response = client.get("/api/settings", headers={"X-API-KEY": TEST_KEY})
    assert response.status_code == 200, response.text
    return response.json()["user_settings"]


def test_coin_lists_persist_across_requests(client):
    payload = {"long_coin_list": ["BTC", "DOGE", "LINK"], "short_coin_list": ["ETH", "SOL"]}
    response = client.post("/api/settings", json=payload, headers={"X-API-KEY": TEST_KEY})
    assert response.status_code == 200, response.text

    stored = _get_settings(client)
    assert stored["long_coin_list"] == payload["long_coin_list"]
    assert stored["short_coin_list"] == payload["short_coin_list"]


def test_coin_lists_persist_after_cache_reset(client):
    """模拟进程重启/缓存失效：值必须来自 SQLite，而不是内存默认值。"""
    payload = {"long_coin_list": ["ADA"], "short_coin_list": []}
    assert client.post("/api/settings", json=payload,
                       headers={"X-API-KEY": TEST_KEY}).status_code == 200

    app_config._cached_settings = None  # 等价于重启后重新 load_settings

    stored = _get_settings(client)
    assert stored["long_coin_list"] == ["ADA"]
    assert stored["short_coin_list"] == []


def test_partial_update_keeps_other_keys(client):
    """只提交币种列表时，其它配置不能被重置成默认值。"""
    before = _get_settings(client)
    assert client.post("/api/settings", json={"long_coin_list": ["BTC"]},
                       headers={"X-API-KEY": TEST_KEY}).status_code == 200
    after = _get_settings(client)

    assert after["long_coin_list"] == ["BTC"]
    assert after["leverage"] == before["leverage"]
    assert after["total_long_position_value"] == before["total_long_position_value"]


def test_retry_counts_above_old_limit_are_accepted(client):
    """重试次数上限曾是 10，用户已存 15 时整包保存被 400 拒绝，连改币种都存不进去。"""
    for value in (10, 15, 50):
        response = client.post(
            "/api/settings",
            json={"open_maker_retries": value, "close_maker_retries": value},
            headers={"X-API-KEY": TEST_KEY},
        )
        assert response.status_code == 200, response.text
        stored = _get_settings(client)
        assert stored["open_maker_retries"] == value

    # 仍然拦明显离谱的值
    response = client.post("/api/settings", json={"open_maker_retries": 999},
                           headers={"X-API-KEY": TEST_KEY})
    assert response.status_code == 400
    assert "open_maker_retries" in response.json()["detail"]


def test_masked_secret_is_not_overwritten(client):
    """前端回写掩码（含 ****）时不能覆盖真实密钥。"""
    assert client.post("/api/settings", json={"api_key": "real-key-12345678"},
                       headers={"X-API-KEY": TEST_KEY}).status_code == 200
    masked = _get_settings(client)["api_key"]
    assert "****" in masked

    assert client.post("/api/settings", json={"api_key": masked, "long_coin_list": ["BTC"]},
                       headers={"X-API-KEY": TEST_KEY}).status_code == 200

    from app.config.config import load_settings

    assert load_settings()["api_key"] == "real-key-12345678"
