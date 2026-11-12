"""静态审计：REST 必须统一经 RestGuardian 通道（R-P1-1 验收①的可执行口径）。

AST 规则（ARCH_REFACTOR_PHASE3 §1.2-6）：
1. `ccxt.binanceusdm(` 构造点只出现在白名单（logic/exchange_logic_async.py、
   core/guarded_exchange.py 若未来直接构造）；
2. `.underlying` 属性访问只出现在 core/guarded_exchange.py；
3. `RestGuardian(` 实例化只出现在 core/rest_guardian.py。
"""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND_APP = Path(__file__).resolve().parents[1] / "app"

CCXT_CONSTRUCT_WHITELIST = {
    "logic/exchange_logic_async.py",   # 唯一 ccxt 实例构造点（initialize_exchange_async）
}
UNDERLYING_WHITELIST = {
    "core/guarded_exchange.py",
}
GUARDIAN_INSTANTIATION_WHITELIST = {
    "core/rest_guardian.py",
}


def _python_files():
    return sorted(BACKEND_APP.rglob("*.py"))


def _rel(path: Path) -> str:
    return path.relative_to(BACKEND_APP).as_posix()


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _is_dotted(node: ast.expr, *parts: str) -> bool:
    """匹配形如 ccxt.binanceusdm / ccxt.async_support 的属性链。"""
    names = list(parts)
    for item in reversed(names):
        if not isinstance(node, ast.Attribute) or node.attr != item:
            return False
        node = node.value
    return isinstance(node, ast.Name) and node.id == "ccxt"


def _walk_with_parents(tree: ast.Module):
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            yield node, child


def test_ccxt_constructor_only_in_whitelist():
    offenders = []
    for path in _python_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and _is_dotted(func, "binanceusdm"):
                if _rel(path) not in CCXT_CONSTRUCT_WHITELIST:
                    offenders.append(f"{_rel(path)}:{node.lineno}")
    assert not offenders, (
        "ccxt.binanceusdm 只能在白名单内构造（其余实例必须经 exchange_manager 的 "
        f"GuardedExchange 包装通道）: {offenders}"
    )


def test_underlying_access_only_in_guarded_exchange():
    offenders = []
    for path in _python_files():
        if _rel(path) in UNDERLYING_WHITELIST:
            continue
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "underlying":
                offenders.append(f"{_rel(path)}:{node.lineno}")
    assert not offenders, (
        "禁止业务代码访问 .underlying（唯一入口 core/guarded_exchange.py）: "
        f"{offenders}"
    )


def test_rest_guardian_instantiation_only_in_rest_guardian_module():
    offenders = []
    for path in _python_files():
        if _rel(path) in GUARDIAN_INSTANTIATION_WHITELIST:
            continue
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "RestGuardian":
                offenders.append(f"{_rel(path)}:{node.lineno}")
    assert not offenders, (
        "RestGuardian 实例化只允许出现在 core/rest_guardian.py"
        "（业务代码用 shared_guardian()/create_guardian()）: "
        f"{offenders}"
    )


def test_exchange_manager_wraps_shared_instances_with_guarded_exchange():
    source = (BACKEND_APP / "core" / "exchange_manager.py").read_text(encoding="utf-8")
    assert "wrap_exchange" in source, "get_exchange_with_timeout 必须返回 GuardedExchange 代理"


def test_rest_priority_covers_core_trading_methods():
    from app.core.guarded_exchange import REST_PRIORITY

    for name in ("create_order", "cancel_order", "fetch_order", "fetch_positions",
                 "fetch_balance", "set_leverage"):
        assert REST_PRIORITY.get(name) == "HIGH", f"{name} 必须登记为 HIGH"
    assert REST_PRIORITY.get("fetch_ohlcv") == "LOW"
