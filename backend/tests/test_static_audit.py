"""Static audit of backend production code (offline, AST based).

Contract: report 3.2, P0-6, P1-13, P2 and 5.4.
"""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND_APP = Path(__file__).resolve().parents[1] / "app"


def _python_files():
    return sorted(BACKEND_APP.rglob("*.py"))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _literal_order_type(node: ast.Call):
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
        return node.args[1].value
    for keyword in node.keywords:
        if keyword.arg in {"type", "order_type", "orderType"} and isinstance(keyword.value, ast.Constant):
            return keyword.value.value
    return None


def test_no_market_orders_in_backend_app():
    violations = []
    for path in _python_files():
        for node in ast.walk(_parse(path)):
            if not isinstance(node, ast.Call):
                continue
            if "create_order" not in _call_name(node):
                continue
            order_type = _literal_order_type(node)
            if isinstance(order_type, str) and order_type.strip().lower() == "market":
                violations.append("%s:%d" % (path, node.lineno))
    assert not violations, "market order submission found (forbidden): %s" % violations


def test_no_pass_only_function_shells():
    offenders = []
    for path in _python_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = list(node.body)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body = body[1:]
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                offenders.append("%s:%d %s" % (path, node.lineno, node.name))
    assert not offenders, "empty 'pass'-only function shells found: %s" % offenders


def test_i18n_module_removed_and_no_longer_imported():
    assert not (BACKEND_APP / "config" / "i18n.py").exists(), (
        "config/i18n.py must be renamed to config/constants.py"
    )
    offenders = []
    for path in _python_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[-1] == "i18n":
                offenders.append("%s:%d" % (path, node.lineno))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[-1] == "i18n":
                        offenders.append("%s:%d" % (path, node.lineno))
    assert not offenders, "legacy i18n imports found: %s" % offenders


def test_main_uses_lifespan_instead_of_deprecated_on_event():
    source = (BACKEND_APP / "main.py").read_text(encoding="utf-8")
    assert "@app.on_event" not in source, "deprecated @app.on_event must be replaced by lifespan"
    assert "lifespan" in source
