# backend/app/core/database.py
"""轻量级 SQLite 存储层（任务 A：JSON -> SQLite 迁移）。

设计要点：
- DB 路径：PROJECT_ROOT/data/app.db（Docker 下 /app/data/app.db，目录自动创建）；
- 每次操作开短连接 + WAL 模式，避免跨线程复用连接的问题；
- 模块级 RLock 串行化写操作，保证多线程写安全；
- 四张表：
  - settings(key TEXT PRIMARY KEY, value TEXT)   value 存 JSON 编码值（任意类型）
  - coin_pools(pool TEXT PRIMARY KEY, coins TEXT) coins 为 JSON 数组
  - signal_state(key TEXT PRIMARY KEY, value TEXT) 信号冷却等运行状态
  - protection_state(key TEXT PRIMARY KEY, value TEXT) 仓位保护风险周期状态（Phase 3）
- init_db() 幂等：建表 + 一次性迁移旧 JSON 文件（迁移后保留旧文件不动）。

所有函数在调用时读取模块级 DB_PATH，测试可 monkeypatch 该路径指向 tmp_path。
"""
import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any, Dict

from .paths import PROJECT_ROOT as _PROJECT_ROOT

DB_PATH: Path = _PROJECT_ROOT / 'data' / 'app.db'

# 允许使用的表名白名单，防止调用方拼接任意表名
ALLOWED_TABLES = ('settings', 'coin_pools', 'signal_state', 'protection_state',
                  'open_history', 'protection_positions', 'protection_events')

# 迁移用的旧 JSON 文件路径（由 config.py 注入，避免循环导入时仅作默认值）
USER_SETTINGS_FILE = _PROJECT_ROOT / 'user_settings.json'
COIN_LISTS_FILE = _PROJECT_ROOT / 'coin_lists.json'

_lock = RLock()

_CONNECT_TIMEOUT_SEC = 15.0

_CREATE_SQL = (
    "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)",
    "CREATE TABLE IF NOT EXISTS coin_pools (pool TEXT PRIMARY KEY, coins TEXT)",
    "CREATE TABLE IF NOT EXISTS signal_state (key TEXT PRIMARY KEY, value TEXT)",
    "CREATE TABLE IF NOT EXISTS protection_state (key TEXT PRIMARY KEY, value TEXT)",
    "CREATE TABLE IF NOT EXISTS open_history (key TEXT PRIMARY KEY, value TEXT)",
    # v2 仓位保护：一仓一行（symbol|side），避免整表 blob 并发覆盖；事件表做审计轨迹
    "CREATE TABLE IF NOT EXISTS protection_positions (key TEXT PRIMARY KEY, value TEXT)",
    "CREATE TABLE IF NOT EXISTS protection_events (key TEXT PRIMARY KEY, value TEXT)",
)


def _connect() -> sqlite3.Connection:
    """打开短连接并启用 WAL 模式。目录不存在时自动创建。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=_CONNECT_TIMEOUT_SEC)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:
        # WAL 打不开（如某些文件系统）不致命，降级为默认 journal 模式
        pass
    return conn


def _check_table(table: str) -> None:
    if table not in ALLOWED_TABLES:
        raise ValueError(f"非法表名: {table}")


# ---------------------------------------------------------------- 基础读写
def _key_column(conn: sqlite3.Connection, table: str) -> str:
    """获取表的第一列（键列）名：settings.key / coin_pools.pool / signal_state.key。"""
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if not cols:
        raise sqlite3.OperationalError(f"表 {table} 不存在或无列")
    return cols[0]


def get_value(table: str, key: str, default=None):
    """读取单个键，JSON 解码；不存在或解析失败时返回 default。"""
    _check_table(table)
    with _lock:
        try:
            conn = _connect()
            try:
                key_col = _key_column(conn, table)
                row = conn.execute(
                    f"SELECT * FROM {table} WHERE {key_col} = ?", (key,)).fetchone()
            finally:
                conn.close()
        except sqlite3.Error as e:
            print(f"--- [ERROR] SQLite 读取 {table}.{key} 失败: {e} ---")
            return default
    if row is None or len(row) < 2:
        return default
    try:
        return json.loads(row[1])
    except (json.JSONDecodeError, TypeError):
        return default


def set_value(table: str, key: str, value) -> None:
    """写入单个键（JSON 编码），幂等 upsert。

    使用 INSERT OR REPLACE 以适配不同表的键列名（settings.key / coin_pools.pool）。
    """
    _check_table(table)
    payload = json.dumps(value, ensure_ascii=False)
    with _lock:
        conn = _connect()
        try:
            conn.execute(f"INSERT OR REPLACE INTO {table} VALUES (?, ?)", (key, payload))
            conn.commit()
        finally:
            conn.close()


def delete_value(table: str, key: str) -> None:
    """删除单个键（不存在时不报错）。"""
    _check_table(table)
    with _lock:
        conn = _connect()
        try:
            key_col = _key_column(conn, table)
            conn.execute(f"DELETE FROM {table} WHERE {key_col} = ?", (key,))
            conn.commit()
        finally:
            conn.close()


def set_many(table: str, mapping: Dict[str, Any]) -> None:
    """在同一连接、同一事务中批量写入多个键。

    用于保存整份用户配置：逐键 set_value 会产生 N 次连接与 N 次 commit，
    中途失败会留下“只写了一半”的风控参数。
    """
    _check_table(table)
    if not mapping:
        return
    rows = [(key, json.dumps(value, ensure_ascii=False)) for key, value in mapping.items()]
    with _lock:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.executemany(f"INSERT OR REPLACE INTO {table} VALUES (?, ?)", rows)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def get_all(table: str) -> dict:
    """读取整表为 {第一列: 第二列 JSON 解码值} 字典。

    表结构约定：第一列为键（settings.key / coin_pools.pool / signal_state.key），
    第二列为 JSON 文本（settings.value / coin_pools.coins / signal_state.value），
    因此不依赖具体列名，SELECT * 即可。
    """
    _check_table(table)
    result: dict = {}
    with _lock:
        try:
            conn = _connect()
            try:
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            finally:
                conn.close()
        except sqlite3.Error as e:
            print(f"--- [ERROR] SQLite 读取整表 {table} 失败: {e} ---")
            return result
    for row in rows:
        if len(row) < 2:
            continue
        key, value = row[0], row[1]
        try:
            result[key] = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            # 跳过损坏行，不中断整体加载
            continue
    return result


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


# ---------------------------------------------------------------- 初始化与迁移
def init_db() -> None:
    """建表 + 一次性迁移旧 JSON 文件。幂等，可重复调用。

    迁移规则：
    - 仅当对应表为空且项目根存在旧 JSON 文件时执行导入；
    - 导入完成后保留旧 JSON 文件不动（作为备份），并打印迁移日志。
    """
    with _lock:
        conn = _connect()
        try:
            for sql in _CREATE_SQL:
                conn.execute(sql)
            conn.commit()

            # --- 迁移 user_settings.json -> settings 表 ---
            if _table_count(conn, 'settings') == 0 and USER_SETTINGS_FILE.exists():
                try:
                    with open(USER_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                        user_settings = json.load(f)
                    if isinstance(user_settings, dict) and user_settings:
                        conn.executemany(
                            "INSERT INTO settings (key, value) VALUES (?, ?)",
                            [(k, json.dumps(v, ensure_ascii=False))
                             for k, v in user_settings.items()])
                        conn.commit()
                        print(f"--- [INFO] 已将 user_settings.json ({len(user_settings)} 项) "
                              f"迁移到 SQLite ({DB_PATH})，旧文件保留作为备份。---")
                except (json.JSONDecodeError, OSError, sqlite3.Error) as e:
                    print(f"--- [ERROR] 迁移 user_settings.json 失败: {e} ---")

            # --- 迁移 coin_lists.json -> coin_pools 表 ---
            if _table_count(conn, 'coin_pools') == 0 and COIN_LISTS_FILE.exists():
                try:
                    with open(COIN_LISTS_FILE, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    pools = {
                        'coins_pool': data.get('coins_pool', []),
                        'long_coins_pool': data.get('long_coins_pool', []),
                        'short_coins_pool': data.get('short_coins_pool', []),
                    }
                    if any(pools.values()):
                        conn.executemany(
                            "INSERT INTO coin_pools (pool, coins) VALUES (?, ?)",
                            [(k, json.dumps(v, ensure_ascii=False))
                             for k, v in pools.items()])
                        conn.commit()
                        print(f"--- [INFO] 已将 coin_lists.json 迁移到 SQLite ({DB_PATH})，"
                              f"旧文件保留作为备份。---")
                except (json.JSONDecodeError, OSError, sqlite3.Error) as e:
                    print(f"--- [ERROR] 迁移 coin_lists.json 失败: {e} ---")
        finally:
            conn.close()
