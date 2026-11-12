"""R-P0-5 WebSocket 鉴权离线测试。

验收要点（ARCH_REFACTOR_PHASE3 §7 T03）：
- 无 token / 错误 token 连接 → 4401 且不进入广播循环；
- 正确 token → 正常收发消息；
- WS_AUTH_DISABLED=1 降级放行（告警由启动/握手日志承担）；
- verify_ws_token / ws_auth_disabled 单元口径。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.security import verify_ws_token, ws_auth_disabled
from app.core.websocket_manager import manager


@pytest.fixture(scope="module")
def client():
    # 不用 context manager：避免 lifespan 启动引擎等副作用（与 test_api_security 一致）
    from app.main import app

    return TestClient(app)


@pytest.fixture(scope="module")
def api_key():
    from app.config.config import load_settings

    key = (load_settings().get("app_access_key") or "").strip()
    assert key, "app_access_key must be configured for the authenticated smoke tests"
    return key


def test_ws_without_token_rejected(client):
    from starlette.websockets import WebSocketDisconnect

    with client.websocket_connect("/ws") as ws:
        # 服务端 accept 后立即 close(4401)：第一条 receive 即抛 WebSocketDisconnect
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()
    assert exc_info.value.code == 4401
    assert manager.active_connections == [], "被拒绝的连接不得进入广播列表"


def test_ws_with_wrong_token_rejected(client):
    from starlette.websockets import WebSocketDisconnect

    with client.websocket_connect("/ws?token=wrong-token") as ws:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()
    assert exc_info.value.code == 4401
    assert manager.active_connections == []


def test_ws_with_valid_token_receives_messages(client, api_key):
    with client.websocket_connect(f"/ws?token={api_key}") as ws:
        # 服务端握手成功后（有历史日志时）会先发历史，随后 ping/pong 双向可用
        ws.send_json({"type": "ping"})
        # 读到的第一条可能是历史日志或 pong，都证明连接已进入正常收发循环
        for _ in range(3):
            message = ws.receive_json()
            if message.get("type") in ("pong", "log"):
                break
        assert message.get("type") in ("pong", "log")


def test_verify_ws_token_unit(api_key, monkeypatch):
    assert verify_ws_token(api_key) is True
    assert verify_ws_token("") is False
    assert verify_ws_token("bad") is False
    # 空密钥一律拒绝
    monkeypatch.setattr("app.core.security.get_app_access_key", lambda: "")
    assert verify_ws_token(api_key) is False


def test_ws_auth_disabled_env_only(monkeypatch):
    monkeypatch.delenv("WS_AUTH_DISABLED", raising=False)
    assert ws_auth_disabled() is False
    monkeypatch.setenv("WS_AUTH_DISABLED", "1")
    assert ws_auth_disabled() is True
    monkeypatch.setenv("WS_AUTH_DISABLED", "true")  # 非 "1" 值不生效（仅显式 1）
    assert ws_auth_disabled() is False
