"""选币/设置持久化回归测试（离线）：POST /api/settings 后 GET 必须读回同一份值。

背景：用户反馈「控制面板选完币种，刷新页面就没了」。这条链路是
前端 SmartSelect -> settingsStore.patchSettings -> POST /api/settings
-> settings 表 -> GET /api/settings。本测试锁定后端这一段：任何一环丢键都会红。
"""
from __future__ import annotations

from datetime import datetime, timezone

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


# ---------------------------------------------- R-P0-2/P1-2/P1-5 新配置校验
def test_new_phase3_settings_persist_and_validate(client):
    """新配置（unprotected_position_action / close_price_chase_ticks / api_*）可保存。"""
    payload = {
        "unprotected_position_action": "keep_alert",
        "close_price_chase_ticks": 3,
        "api_max_concurrency": 5,
        "api_min_interval_sec": 0.15,
        "api_max_retries": 4,
    }
    response = client.post("/api/settings", json=payload, headers={"X-API-KEY": TEST_KEY})
    assert response.status_code == 200, response.text
    stored = _get_settings(client)
    assert stored["unprotected_position_action"] == "keep_alert"
    assert stored["close_price_chase_ticks"] == 3
    assert stored["api_max_concurrency"] == 5
    assert stored["api_min_interval_sec"] == pytest.approx(0.15)
    assert stored["api_max_retries"] == 4


def test_api_settings_out_of_range_rejected_400(client):
    for key, bad in (
        ("close_price_chase_ticks", 99),
        ("api_max_concurrency", 0),
        ("api_max_retries", 0),
        ("api_failure_threshold", 999),
        ("api_418_cooldown_sec", 0),
    ):
        response = client.post("/api/settings", json={key: bad},
                               headers={"X-API-KEY": TEST_KEY})
        assert response.status_code == 400, f"{key}={bad} 越界必须 400"


def test_unprotected_position_action_choice_validated(client):
    response = client.post("/api/settings", json={"unprotected_position_action": "boom"},
                           headers={"X-API-KEY": TEST_KEY})
    assert response.status_code == 400, "枚举值之外必须 400"
    response = client.post("/api/settings", json={"unprotected_position_action": "auto_close"},
                           headers={"X-API-KEY": TEST_KEY})
    assert response.status_code == 200
    assert _get_settings(client)["unprotected_position_action"] == "auto_close"


# ---------------------------------------------- 权重与币种清单一同落定
# 2026-11-15 用户要求：权重跟着最新选的币种走，默认均分；不许捞上一次的权重。
def test_weights_are_rebuilt_when_only_coin_list_is_saved(client):
    """只提交清单：权重自动对齐成均分，旧键（AAPL 那套）必须被丢弃。"""
    assert client.post("/api/settings", json={
        "long_coin_list": ["BTC", "ETH", "BNB"],
        "long_custom_weights": {"AAPL": 14.29, "AMD": 14.29, "NVDA": 14.29},
    }, headers={"X-API-KEY": TEST_KEY}).status_code == 200
    assert _get_settings(client)["long_custom_weights"] == {
        "BTC": pytest.approx(33.33), "ETH": pytest.approx(33.33),
        "BNB": pytest.approx(33.34),
    }

    # 只改清单，不再传权重：不能把上一套清单的权重带过来
    assert client.post("/api/settings", json={"long_coin_list": ["BTC", "ETH"]},
                       headers={"X-API-KEY": TEST_KEY}).status_code == 200
    assert _get_settings(client)["long_custom_weights"] == {
        "BTC": pytest.approx(50.0), "ETH": pytest.approx(50.0),
    }


def test_weights_and_coin_list_saved_in_one_request(client):
    """清单一改，权重就在同一个请求里对齐（键集合 = 清单、合计 100）。"""
    response = client.post("/api/settings", json={
        "long_coin_list": ["ETH", "BNB"],
        "long_custom_weights": {"ETH": 70, "BNB": 30},
    }, headers={"X-API-KEY": TEST_KEY})
    assert response.status_code == 200, response.text
    stored = _get_settings(client)
    assert stored["long_coin_list"] == ["ETH", "BNB"]
    assert stored["long_custom_weights"] == {"ETH": pytest.approx(70.0),
                                             "BNB": pytest.approx(30.0)}


def test_weights_only_update_keeps_list_keys(client):
    """只改权重（清单不动）：键集合仍必须等于清单，新增的币按剩余比例均分。"""
    client.post("/api/settings", json={"long_coin_list": ["BTC", "ETH", "BNB"]},
                headers={"X-API-KEY": TEST_KEY})
    response = client.post("/api/settings",
                           json={"long_custom_weights": {"BTC": 40, "ETH": 40}},
                           headers={"X-API-KEY": TEST_KEY})
    assert response.status_code == 200, response.text
    weights = _get_settings(client)["long_custom_weights"]
    assert set(weights) == {"BTC", "ETH", "BNB"}
    assert weights["BTC"] == pytest.approx(40.0)
    assert weights["BNB"] == pytest.approx(20.0)
    assert sum(weights.values()) == pytest.approx(100.0)


def test_empty_coin_list_clears_weights(client):
    client.post("/api/settings", json={"long_coin_list": ["BTC", "ETH"]},
                headers={"X-API-KEY": TEST_KEY})
    client.post("/api/settings", json={"long_coin_list": []}, headers={"X-API-KEY": TEST_KEY})
    assert _get_settings(client)["long_custom_weights"] == {}


def test_cooldown_toggle_persists_and_returns_server_until(client):
    """用户反馈「改了拒绝开仓开关和冷静时长，刷新又变回去了」。

    锁定两点：
    1. POST 必须落库（GET 能读回同一份值）；
    2. 响应要带回服务端算出的 trade_cooldown_until —— 前端算不出这个时间，
       不回写就会出现「已进冷静期但页面没有倒计时」。
    """
    response = client.post(
        "/api/settings",
        json={"trade_cooldown_enabled": True, "trade_cooldown_minutes": 30},
        headers={"X-API-KEY": TEST_KEY})
    assert response.status_code == 200, response.text
    saved = response.json()["user_settings"]
    assert saved["trade_cooldown_enabled"] is True
    assert saved["trade_cooldown_minutes"] == 30
    assert saved["trade_cooldown_triggered_by"] == "manual"
    until = saved["trade_cooldown_until"]
    assert until and datetime.fromisoformat(until) > datetime.now(timezone.utc)

    stored = _get_settings(client)
    assert stored["trade_cooldown_enabled"] is True
    assert stored["trade_cooldown_minutes"] == 30
    assert stored["trade_cooldown_until"] == until

    # 关闭：状态立即清空，开仓立刻恢复
    response = client.post("/api/settings", json={"trade_cooldown_enabled": False},
                           headers={"X-API-KEY": TEST_KEY})
    assert response.status_code == 200, response.text
    assert response.json()["user_settings"]["trade_cooldown_until"] is None
    assert _get_settings(client)["trade_cooldown_enabled"] is False
