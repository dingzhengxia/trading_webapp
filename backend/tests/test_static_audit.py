"""Static audit of backend production code (offline, AST based).

Contract: report 3.2, P0-6, P1-13, P2 and 5.4.
"""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND_APP = Path(__file__).resolve().parents[1] / "app"

# T09（P2-7）：市价单静态审计显式白名单 —— protection/exits.py 是全后端
# 唯一允许下发市价单的文件，且必须同时满足：
#   1. params 含 reduceOnly: True（只减仓）
#   2. 下单方向为平仓方向（多仓卖 / 空仓买）
MARKET_ORDER_WHITELIST = {"protection/exits.py"}
CLOSE_SIDE_PATTERN = '"sell" if side == "long" else "buy"'


def _python_files():
    return sorted(BACKEND_APP.rglob("*.py"))


def _rel_path(path: Path) -> str:
    return path.relative_to(BACKEND_APP).as_posix()


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


def _market_dispatch_nodes(tree: ast.Module):
    """收集 AST 内所有“市价单下发”调用节点。

    两种形态都算：
    - 属性调用: exchange.create_market_order(...)
    - REST 方法名派发: _rest(exchange, 'create_market_order', ...)（首参为方法名字符串）
    """
    nodes = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node) == "create_market_order":
            nodes.append(node)
        elif any(isinstance(a, ast.Constant) and a.value == "create_market_order"
                 for a in node.args):
            # _rest(exchange, 'create_market_order', ...) 形式的 REST 方法名派发
            nodes.append(node)
    return nodes


def _enclosing_function(tree: ast.Module, target: ast.Call):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if child is target:
                    return node
    return None


def _find_market_dispatch_violations(entries):
    """entries: [(rel_path, source)] -> violations 列表。

    规则：市价单下发只允许出现在白名单文件内，且白名单内的每一处
    必须落在含 reduceOnly: True 与平仓方向表达式的函数里。
    """
    violations = []
    for rel, source in entries:
        tree = ast.parse(source)
        for node in _market_dispatch_nodes(tree):
            if rel not in MARKET_ORDER_WHITELIST:
                violations.append("%s:%d market dispatch outside whitelist" % (rel, node.lineno))
                continue
            func = _enclosing_function(tree, node)
            segment = ast.get_source_segment(source, func) if func else ""
            # 引号归一化：单双引号等价，避免审计结果依赖书写风格
            segment = segment.replace("'", '"')
            if '"reduceOnly": True' not in segment:
                violations.append("%s:%d market dispatch without reduceOnly" % (rel, node.lineno))
            if CLOSE_SIDE_PATTERN not in segment:
                violations.append("%s:%d market dispatch not close-side" % (rel, node.lineno))
    return violations


def test_no_market_orders_outside_exits_whitelist():
    entries = [(_rel_path(p), p.read_text(encoding="utf-8")) for p in _python_files()]
    violations = _find_market_dispatch_violations(entries)
    assert not violations, "market order dispatch outside protection/exits.py whitelist: %s" % violations


def test_whitelist_market_dispatch_is_reduce_only_and_close_side():
    """白名单文件本身也必须满足 reduceOnly + 平仓方向，否则视为违规。"""
    exits_path = BACKEND_APP / "protection" / "exits.py"
    assert exits_path.exists(), "protection/exits.py（市价单白名单落点）必须存在"
    violations = _find_market_dispatch_violations([("protection/exits.py", exits_path.read_text(encoding="utf-8"))])
    assert not violations, "whitelist exits.py must keep reduceOnly close-side market orders: %s" % violations


def test_market_order_audit_negative_cases():
    """负向用例：白名单外出现市价单、白名单内缺少 reduceOnly/平仓方向 → 必须判违规。"""
    # 1) 白名单外的属性调用形式
    outside = (
        "async def bad(exchange):\n"
        "    await exchange.create_market_order('BTC/USDC:USDC', 'buy', 1)\n"
    )
    assert _find_market_dispatch_violations([("api/bad.py", outside)])
    # 2) 白名单外的 REST 方法名派发形式
    outside_rest = (
        "async def bad(exchange, conf):\n"
        "    await _rest(exchange, 'create_market_order', 'X', 'buy', 1)\n"
    )
    assert _find_market_dispatch_violations([("api/bad_rest.py", outside_rest)])
    # 3) 白名单内但缺少 reduceOnly
    no_reduce = (
        "async def bad(exchange):\n"
        "    await exchange.create_market_order('BTC/USDC:USDC', 'buy', 1)\n"
    )
    assert _find_market_dispatch_violations([("protection/exits.py", no_reduce)])
    # 4) 白名单内 reduceOnly 但方向不是平仓方向
    wrong_side = (
        "async def ok(exchange):\n"
        "    await exchange.create_market_order('BTC/USDC:USDC', 'buy', 1,\n"
        "        params={'reduceOnly': True})\n"
    )
    assert _find_market_dispatch_violations([("protection/exits.py", wrong_side)])
    # 5) 对照组：白名单内 reduceOnly + 平仓方向 → 不违规
    compliant = (
        'async def ok(exchange):\n'
        "    await exchange.create_market_order('BTC/USDC:USDC',\n"
        '        "sell" if side == "long" else "buy", 1,\n'
        "        params={'reduceOnly': True})\n"
    )
    assert not _find_market_dispatch_violations([("protection/exits.py", compliant)])


def test_no_market_type_literal_in_create_order_calls():
    """任意文件内 create_order(..., 'market', ...) 字面量市价开单均禁止（含白名单文件）。"""
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
