# backend/app/protection/service.py
"""仓位保护引擎的进程级生命周期管理（启动 / 停止 / 状态查询）。

设计：
- supervisor 每 5 秒读取一次配置（SQLite，load_settings 有缓存），
  `position_protection.enabled` 为 True 且引擎未运行 → 启动；为 False → 取消；
- 引擎内部是无限循环（protect_positions_main），异常退出后 supervisor 会自动重启并记录错误；
- 状态查询直接读引擎的 RUNTIME（持仓映射 + 每个方向的风险周期状态），不额外发请求。
"""
import asyncio
import time
from typing import Any, Dict, List, Optional

from loguru import logger

from ..core.exchange_manager import get_shared_exchange
from ..core.tasks import cancel_task, cancel_tasks
from . import engine
from .config import load_protection_config

_supervisor_task: Optional[asyncio.Task] = None
_engine_task: Optional[asyncio.Task] = None
_last_error: Optional[str] = None
_started_at: Optional[float] = None


async def _run_engine() -> None:
    """获取共享交易所实例并运行仓位保护主循环（按配置选择 v1 / v2 引擎）。"""
    global _started_at
    exchange = await get_shared_exchange()
    _started_at = time.time()
    conf = load_protection_config().get("position_protection", {})
    version = str(conf.get("engine_version") or "v2").lower()
    if version == "v1":
        logger.info("🛡️ 使用 v1 仓位保护引擎（engine_version=v1）")
        await engine.protect_positions_main(exchange)
        return
    # 延迟导入：v2 依赖 engine 的下单原语，放模块顶部会形成循环导入
    from . import runner
    logger.info("🛡️ 使用 v2 仓位保护引擎（engine_version=v2）")
    await runner.protect_positions_main_v2(exchange)


async def _supervisor() -> None:
    """按配置开关启停引擎，并在异常退出后自动重启。"""
    global _engine_task, _last_error
    while True:
        try:
            conf = load_protection_config().get("position_protection", {})
            enabled = bool(conf.get("enabled", False))
            running = _engine_task is not None and not _engine_task.done()

            if enabled and not running:
                if _engine_task is not None and _engine_task.done():
                    exc = _engine_task.exception()
                    if exc is not None:
                        _last_error = f"{type(exc).__name__}: {exc}"
                        logger.warning(f"仓位保护引擎上次异常退出，准备重启: {_last_error}")
                _engine_task = asyncio.create_task(_run_engine(), name="position-protection")
                logger.info("🛡️ 仓位保护引擎已启动（配置 enabled=true）")
            elif not enabled and running:
                _engine_task.cancel()
                try:
                    await _engine_task
                except asyncio.CancelledError:
                    pass
                logger.info("🛡️ 仓位保护引擎已停止（配置 enabled=false）")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - supervisor 不能因单次失败退出
            _last_error = f"{type(exc).__name__}: {exc}"
            logger.error(f"仓位保护 supervisor 异常: {_last_error}")
        await asyncio.sleep(5)


async def startup_protection() -> None:
    """lifespan 启动时调用：注册 supervisor（引擎是否运行由配置决定）。"""
    global _supervisor_task
    if _supervisor_task is not None and not _supervisor_task.done():
        return
    _supervisor_task = asyncio.create_task(_supervisor(), name="protection-supervisor")
    logger.info("🛡️ 仓位保护 supervisor 就绪（enabled 由配置决定，默认关闭）")


async def shutdown_protection() -> None:
    """lifespan 关闭时调用：停止 supervisor 与引擎。"""
    global _supervisor_task, _engine_task
    await cancel_tasks((_engine_task, _supervisor_task))
    _engine_task = None
    _supervisor_task = None


async def restart_protection() -> None:
    """配置变更后立即生效：重启引擎任务（下一轮 supervisor 会按新配置拉起）。"""
    global _engine_task
    await cancel_task(_engine_task)
    _engine_task = None


def protection_active_for(full_symbol: str, side: str) -> bool:
    """查询仓位保护引擎是否已接管指定 (symbol, side) 仓位（只读，零请求）。

    R-P0-2 裸仓回收协调：交易主链路在 SL/TP 注入失败时调用本函数判断处置权——
    引擎已接管（enabled=True 且引擎状态中存在该仓位）则跳过自动平仓，避免
    两边同时发单互相顶单；未接管时主链路按 unprotected_position_action 兜底。
    """
    side = str(side or '').lower()
    if side not in ('long', 'short') or not full_symbol:
        return False
    try:
        conf = load_protection_config().get("position_protection", {})
        if not bool(conf.get("enabled", False)):
            return False
        version = str(conf.get("engine_version") or "v2").lower()
        if version == "v1":
            return engine._state_key(full_symbol, side) in engine._load_state()
    except Exception as exc:  # noqa: BLE001 - 查询失败按"未接管"处理（主链路兜底）
        logger.warning(f"查询仓位保护接管状态失败（按未接管处理）: {exc}")
        return False
    # v2：运行时活跃集合 或 一仓一行账本中已有该仓位
    from . import runner
    if (full_symbol, side) in getattr(runner.V2, 'active', set()):
        return True
    try:
        from . import ledger
        return ledger.load(full_symbol, side) is not None
    except Exception:  # noqa: BLE001
        return False


def _position_row(symbol: str, side: str, position: Dict[str, Any]) -> Dict[str, Any]:
    """把交易所仓位 + 引擎运行时状态整理成给前端的行。"""
    key = engine._state_key(symbol, side)
    state = engine.RUNTIME.runtime_position_states.get(key) or {}
    return {
        "symbol": symbol,
        "side": side,
        "contracts": engine._position_size(position),
        "entry_price": engine._f(position.get("entryPrice"), 0.0),
        "mark_price": engine._f(position.get("markPrice"), 0.0),
        "stop_price": engine._f(state.get("last_stop_price"), None),
        "protected_stop": engine._f(state.get("tp_protected_stop"), None),
        "tp1_price": engine._f(state.get("tp1_price"), None),
        "tp2_price": engine._f(state.get("tp2_price"), None),
        "tp3_price": engine._f(state.get("tp3_price"), None),
        "t1_done": bool(state.get("t1_done")),
        "t2_done": bool(state.get("t2_done")),
        "t3_done": bool(state.get("t3_triggered")),
        "tp1_done": bool(state.get("tp1_triggered")),
        "tp2_done": bool(state.get("tp2_triggered")),
        "tp3_done": bool(state.get("tp3_triggered")),
        "risk_cycle_started_at": state.get("risk_cycle_started_at"),
        "position_version": state.get("position_version"),
    }


def _cooldown_snapshot(conf: Dict[str, Any]) -> Dict[str, Any]:
    """黑天鹅冷却快照；单点异常不影响整个状态接口。"""
    try:
        from . import cooldown
        return cooldown.snapshot(conf)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"读取黑天鹅冷却状态失败: {exc}")
        return {}


def get_protection_status() -> Dict[str, Any]:
    """返回仓位保护运行状态（供 /api/protection 使用），不发起任何交易所请求。"""
    conf = load_protection_config().get("position_protection", {})
    version = str(conf.get("engine_version") or "v2").lower()
    running = _engine_task is not None and not _engine_task.done()

    if version == "v1":
        rows: List[Dict[str, Any]] = []
        for (symbol, side), position in list(engine.RUNTIME.global_positions_map.items()):
            try:
                rows.append(_position_row(symbol, side, position or {}))
            except Exception as exc:  # noqa: BLE001 - 单行异常不应影响整体状态查询
                logger.warning(f"整理仓位状态失败 {symbol}/{side}: {exc}")
        return {
            "engine_version": "v1",
            "enabled": bool(conf.get("enabled", False)),
            "running": running,
            "started_at": _started_at,
            "last_error": _last_error,
            "timeframe": conf.get("timeframe"),
            "positions": rows,
            "api": engine.RUNTIME.rest.stats(),
            "config": conf,
        }

    # v2：状态直接读账本（一仓一行），不发任何请求
    from . import runner
    snapshot = runner.status()
    return {
        "engine_version": "v2",
        "enabled": bool(conf.get("enabled", False)),
        "running": running,
        "started_at": _started_at,
        "last_error": _last_error or snapshot.get("last_error"),
        "timeframe": conf.get("v2_timeframe") or conf.get("timeframe"),
        "positions": snapshot.get("positions") or [],
        "v2": {
            "cycle_count": snapshot.get("cycle_count"),
            "last_cycle_ts": snapshot.get("last_cycle_ts"),
            "recent_actions": snapshot.get("recent_actions") or [],
            "dry_run": bool(conf.get("dry_run", False)),
        },
        "api": engine.RUNTIME.rest.stats(),
        "config": conf,
        # 黑天鹅全平后的同币冷却（开仓闸门会据此跳过）：空对象=没有币在冷却
        "cooldowns": _cooldown_snapshot(conf),
    }
