"""任务 A 离线测试：SQLite 存储层（settings/coin_pools/signal_state）与 JSON 迁移。

所有测试把 database.DB_PATH monkeypatch 到 tmp_path，完全不触碰真实 data/app.db。
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import database  # noqa: E402


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """把 DB 路径指向临时目录，并隔离迁移源 JSON 路径。"""
    db_path = tmp_path / "app.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    monkeypatch.setattr(database, "USER_SETTINGS_FILE", tmp_path / "user_settings.json")
    monkeypatch.setattr(database, "COIN_LISTS_FILE", tmp_path / "coin_lists.json")
    database.init_db()
    return db_path


# ---------------------------------------------------------------------------
# settings / signal_state 基础读写
# ---------------------------------------------------------------------------
def test_settings_roundtrip(tmp_db):
    database.init_db()
    database.set_value("settings", "leverage", 20)
    database.set_value("settings", "nested", {"a": [1, 2, 3], "b": "中文"})
    assert database.get_value("settings", "leverage") == 20
    assert database.get_value("settings", "nested") == {"a": [1, 2, 3], "b": "中文"}
    assert database.get_value("settings", "missing", "default") == "default"
    all_vals = database.get_all("settings")
    assert all_vals["leverage"] == 20 and "nested" in all_vals


def test_signal_state_roundtrip(tmp_db):
    database.init_db()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    database.set_value("signal_state", "alerted_states", {"BTC_1h_KDJ_0": now.isoformat()})
    loaded = database.get_value("signal_state", "alerted_states")
    assert "BTC_1h_KDJ_0" in loaded


def test_set_value_overwrites(tmp_db):
    database.init_db()
    database.set_value("signal_state", "k", 1)
    database.set_value("signal_state", "k", 2)
    assert database.get_value("signal_state", "k") == 2


# ---------------------------------------------------------------------------
# config.py 对接（save/load settings 与 coin pools）
# ---------------------------------------------------------------------------
@pytest.fixture
def isolated_config(tmp_db, monkeypatch):
    from app.config import config
    monkeypatch.setattr(config, "_cached_settings", None)
    monkeypatch.setattr(config, "AVAILABLE_COINS", [])
    monkeypatch.setattr(config, "AVAILABLE_LONG_COINS", [])
    monkeypatch.setattr(config, "AVAILABLE_SHORT_COINS", [])
    return config


def test_config_settings_roundtrip(isolated_config):
    config = isolated_config
    payload = dict(config.DEFAULT_CONFIG)
    payload["leverage"] = 33
    payload["signal_scan_enabled"] = True
    payload["signal_auto_trade_value_usd"] = 250.5
    assert config.save_settings(payload) is True

    monkey_cache = config._cached_settings
    config._cached_settings = None  # 模拟重启后的重新加载
    loaded = config.load_settings()
    config._cached_settings = monkey_cache
    assert loaded["leverage"] == 33
    assert loaded["signal_scan_enabled"] is True
    assert loaded["signal_auto_trade_value_usd"] == 250.5
    assert loaded["signal_scan_static_symbols"] == ["BTC", "ETH", "BNB"]


def test_config_coin_pools_roundtrip_and_normalize(isolated_config):
    config = isolated_config
    config.AVAILABLE_COINS = ["BTC", "ETH"]
    result = config.save_coin_pools([" btc ", "SOL", "btc", 123], [" eth ", "", None])
    assert result["coins_pool"] == ["BTC", "ETH"]
    assert result["long_coins_pool"] == ["BTC", "SOL"]  # 去空白/大写/去重/过滤非字符串
    assert result["short_coins_pool"] == ["ETH"]

    config.AVAILABLE_LONG_COINS = []
    config.AVAILABLE_SHORT_COINS = []
    config.load_coin_lists()
    assert config.AVAILABLE_LONG_COINS == ["BTC", "SOL"]
    assert config.AVAILABLE_SHORT_COINS == ["ETH"]
    assert config.AVAILABLE_COINS == ["BTC", "ETH"]


def test_config_add_coin_to_pool(isolated_config):
    config = isolated_config
    config.AVAILABLE_COINS = []
    assert config.add_coin_to_pool("doge") == ["DOGE"]
    with pytest.raises(ValueError):
        config.add_coin_to_pool("DOGE")


# ---------------------------------------------------------------------------
# 一次性迁移：JSON -> SQLite
# ---------------------------------------------------------------------------
def _write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def test_migration_imports_once(tmp_path, tmp_db, monkeypatch):
    settings_file = tmp_path / "user_settings.json"
    coins_file = tmp_path / "coin_lists.json"
    _write_json(settings_file, {"app_access_key": "k-test", "leverage": 7, "signal_scan_enabled": False})
    _write_json(coins_file, {"coins_pool": ["BTC"], "long_coins_pool": ["BTC", "ETH"],
                             "short_coins_pool": []})
    monkeypatch.setattr(database, "USER_SETTINGS_FILE", settings_file)
    monkeypatch.setattr(database, "COIN_LISTS_FILE", coins_file)

    database.init_db()
    assert database.get_value("settings", "leverage") == 7
    assert database.get_value("settings", "app_access_key") == "k-test"
    pools = database.get_all("coin_pools")
    assert pools["coins_pool"] == ["BTC"]
    assert pools["long_coins_pool"] == ["BTC", "ETH"]
    # 旧 JSON 文件保留不动
    assert settings_file.exists() and coins_file.exists()

    # 第二次启动：不重复导入（修改 DB 后再 init_db 不被旧 JSON 覆盖）
    database.set_value("settings", "leverage", 99)
    database.set_value("coin_pools", "coins_pool", ["BTC", "SOL"])
    database.init_db()
    assert database.get_value("settings", "leverage") == 99
    assert database.get_value("coin_pools", "coins_pool") == ["BTC", "SOL"]


def test_migration_without_json_files(tmp_db):
    # 无旧 JSON 时 init_db 应安全建表，不报错
    database.init_db()
    assert database.get_all("settings") == {}
    assert database.get_all("coin_pools") == {}


def test_migration_skips_empty_table_only(tmp_db, tmp_path, monkeypatch):
    # settings 表非空时（例如测试中先写过），即使 JSON 存在也不迁移
    settings_file = tmp_path / "user_settings.json"
    _write_json(settings_file, {"leverage": 5})
    monkeypatch.setattr(database, "USER_SETTINGS_FILE", settings_file)
    database.init_db()
    database.set_value("settings", "leverage", 1)
    database.init_db()
    assert database.get_value("settings", "leverage") == 1


# ---------------------------------------------------------------------------
# 并发写安全
# ---------------------------------------------------------------------------
def test_concurrent_writes_are_safe(tmp_db):
    database.init_db()
    errors: list[str] = []

    def worker(worker_id: int) -> None:
        try:
            for i in range(20):
                database.set_value("settings", f"key_{worker_id}", {"i": i, "w": worker_id})
        except Exception as e:  # noqa: BLE001
            errors.append(repr(e))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    vals = database.get_all("settings")
    assert len(vals) == 8
    for n in range(8):
        assert vals[f"key_{n}"]["w"] == n
