# backend/tests/test_engineering_hygiene.py
"""T13（P2-5）工程卫生的静态断言与生命周期断言。

覆盖三条验收项：
1. 无裸 print：backend/app 全包只允许 app/main.py 使用 print，
   且全部 print 调用必须位于 lifespan 函数内（启动横幅白名单入测试）；
2. InterruptedError → TaskInterruptedError：全仓（AST 级）不再定义 /
   引用遮蔽内建异常的业务类名 InterruptedError；
3. import app 不触发建库：database.init_db() 已移入 lifespan 的
   init_app_storage()，导入 app.main 不得创建 SQLite 文件；
   init_app_storage() 本身幂等，可重复调用。
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BACKEND_DIR / "app"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import database  # noqa: E402

STARTUP_BANNER_PRINT_WHITELIST = {"main.py"}


def _app_python_files() -> list[Path]:
    return sorted(APP_DIR.rglob("*.py"))


# ---------------------------------------------------------------------------
# 1. 裸 print 断言（main 启动横幅白名单）
# ---------------------------------------------------------------------------
def test_no_bare_print_outside_startup_banner() -> None:
    """全包只有 main.py 允许 print，且所有 print 必须在 lifespan 函数体内。"""
    offenders: dict[str, int] = {}
    for path in _app_python_files():
        rel = path.relative_to(APP_DIR).as_posix()
        if rel in STARTUP_BANNER_PRINT_WHITELIST:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                offenders[rel] = offenders.get(rel, 0) + 1
    assert not offenders, f"app 内存在裸 print（应改用 loguru）: {offenders}"


def test_main_prints_confined_to_lifespan_banner() -> None:
    """main.py 的 print 全部落在 lifespan 内（启动横幅），横幅外一律 loguru。"""
    path = APP_DIR / "main.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    lifespan_ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "lifespan" and isinstance(node, ast.AsyncFunctionDef):
                lifespan_ranges.append((node.lineno, node.end_lineno or node.lineno))
    assert lifespan_ranges, "main.py 中未找到 lifespan 函数"

    def _inside_lifespan(lineno: int) -> bool:
        return any(start <= lineno <= end for start, end in lifespan_ranges)

    outside: list[int] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
            and not _inside_lifespan(node.lineno)
        ):
            outside.append(node.lineno)
    assert not outside, f"main.py 中 lifespan 之外的 print 行号: {outside}"


# ---------------------------------------------------------------------------
# 2. TaskInterruptedError 重命名断言（AST 级，注释中的提及不算）
# ---------------------------------------------------------------------------
def test_interrupted_error_renamed_everywhere() -> None:
    """app 内不得再定义 / 引用名为 InterruptedError 的业务异常（遮蔽内建）。"""
    offenders: list[str] = []
    for path in _app_python_files():
        rel = path.relative_to(APP_DIR).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            # 类定义 / import / except 捕获 / 显式引用
            if isinstance(node, ast.ClassDef) and node.name == "InterruptedError":
                offenders.append(f"{rel}:{node.lineno} class")
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "InterruptedError" and alias.asname != "TaskInterruptedError":
                        offenders.append(f"{rel}:{node.lineno} import")
            elif isinstance(node, ast.ExceptHandler):
                handler = node.type
                if isinstance(handler, ast.Name) and handler.id == "InterruptedError":
                    offenders.append(f"{rel}:{node.lineno} except")
            elif isinstance(node, ast.Name) and node.id == "InterruptedError":
                offenders.append(f"{rel}:{node.lineno} reference")
    assert not offenders, f"InterruptedError 业务异常残留: {offenders}"

    from app.logic import exceptions

    assert hasattr(exceptions, "TaskInterruptedError")
    assert issubclass(exceptions.TaskInterruptedError, Exception)


def test_trading_and_logic_use_task_interrupted_error() -> None:
    """原 InterruptedError 的两大使用方已切换为 TaskInterruptedError。"""
    for rel in ("core/trading_service.py", "logic/exchange_logic_async.py"):
        source = (APP_DIR / rel).read_text(encoding="utf-8")
        assert "TaskInterruptedError" in source, f"{rel} 未使用 TaskInterruptedError"


# ---------------------------------------------------------------------------
# 3. import 不建库 + init_app_storage 幂等
# ---------------------------------------------------------------------------
def test_import_app_does_not_create_db(tmp_path: Path) -> None:
    """子进程导入 app.main：不得创建 SQLite 文件（建库已移入 lifespan）。"""
    db_path = tmp_path / "probe" / "app.db"
    script = (
        "import sys, json\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, r'{BACKEND_DIR}')\n"
        "from app.core import database\n"
        f"database.DB_PATH = Path(r'{db_path}')\n"
        "import app.main  # noqa: F401  触发完整的 import 链\n"
        "print(json.dumps({'exists': database.DB_PATH.exists()}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"子进程导入 app.main 失败:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["exists"] is False, "import app.main 创建了 SQLite 文件（应只在 lifespan 建库）"


def test_init_app_storage_idempotent(tmp_path: Path, monkeypatch) -> None:
    """init_app_storage() 建表且幂等：重复调用不丢数据、不重复迁移。"""
    import app.main as app_main

    db_path = tmp_path / "app.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    monkeypatch.setattr(
        database, "USER_SETTINGS_FILE", tmp_path / "user_settings.json")
    monkeypatch.setattr(
        database, "COIN_LISTS_FILE", tmp_path / "coin_lists.json")

    app_main.init_app_storage()
    database.set_value("settings", "probe_key", {"a": 1})
    # 二次调用：幂等，已写入的数据保留
    app_main.init_app_storage()
    assert database.get_value("settings", "probe_key") == {"a": 1}
    assert db_path.exists()
