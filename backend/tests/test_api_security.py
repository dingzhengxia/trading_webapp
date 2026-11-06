"""Offline API smoke tests: auth + 4xx validation without any exchange access.

Contract: report 4.5 / 5.3 / 5.5.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

MANUAL_URL = "/api/trading/manual"
RESOLVE_URL = "/api/trading/resolve-symbols"


@pytest.fixture(scope="module")
def client():
    # Do not use TestClient as a context manager: no lifespan/network side effects.
    from app.main import app

    return TestClient(app)


@pytest.fixture(scope="module")
def api_key():
    from app.config.config import load_settings

    key = (load_settings().get("app_access_key") or "").strip()
    assert key, "app_access_key must be configured for the authenticated smoke tests"
    return key


def _manual_payload(items, default_value=10.0):
    return {"request_id": "offline-test-req", "default_value": default_value, "items": items}


def test_status_requires_api_key(client):
    response = client.get("/api/status")
    assert response.status_code == 403


def test_status_returns_200_with_valid_key(client, api_key):
    response = client.get("/api/status", headers={"X-API-KEY": api_key})
    assert response.status_code == 200
    assert "is_running" in response.json()


def test_settings_returns_200_with_valid_key(client, api_key):
    response = client.get("/api/settings", headers={"X-API-KEY": api_key})
    assert response.status_code == 200


def test_manual_requires_api_key(client):
    response = client.post(MANUAL_URL, json=_manual_payload([
        {"symbol": "BTC", "action": "long", "value": 10.0},
    ]))
    assert response.status_code == 403


def test_manual_rejects_empty_items(client, api_key):
    response = client.post(
        MANUAL_URL,
        json={"request_id": "offline-test-req", "items": []},
        headers={"X-API-KEY": api_key},
    )
    assert response.status_code in (400, 422), response.status_code


def test_manual_rejects_duplicate_symbols(client, api_key):
    response = client.post(
        MANUAL_URL,
        json=_manual_payload([
            {"symbol": "BTC", "action": "long", "value": 10.0},
            {"symbol": " btc ", "action": "short", "value": 10.0},
        ]),
        headers={"X-API-KEY": api_key},
    )
    assert response.status_code == 400, response.status_code
    assert response.json().get("detail")


def test_manual_rejects_non_positive_value(client, api_key):
    response = client.post(
        MANUAL_URL,
        json=_manual_payload([{"symbol": "BTC", "action": "long", "value": 0}]),
        headers={"X-API-KEY": api_key},
    )
    assert response.status_code in (400, 422), response.status_code


def test_resolve_symbols_requires_api_key(client):
    response = client.get(RESOLVE_URL, params={"symbols": "BTC"})
    assert response.status_code == 403
