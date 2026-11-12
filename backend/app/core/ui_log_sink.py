# backend/app/core/ui_log_sink.py
"""把 monitor 并入的两个引擎（app.signals / app.protection）的 loguru 日志转发到网页日志抽屉。

背景：monitor 原来是独立进程，有自己的控制台窗口；并入 WebApp 后日志只打到后端控制台，
用户在网页上感知不到引擎活动。本模块安装一个 loguru sink，把这两个模块的日志
（INFO 及以上）转发到 WebSocket 日志抽屉，与交易日志混排显示。

注意事项：
- protection 的告警 notifier.send_alert 已自行推送 UI，此处按消息内容去重；
- 只在事件循环内转发（策略线程中的日志仍走控制台，避免跨线程 create_task 报错）。
"""
import asyncio

from loguru import logger

from .websocket_manager import log_message

# loguru 级别 -> UI 日志级别
_LEVEL_MAP = {
    "INFO": "info",
    "SUCCESS": "success",
    "WARNING": "warning",
    "ERROR": "error",
    "CRITICAL": "error",
}

# 模块前缀 -> UI 日志前缀（用于在网页日志里区分来源）
_SOURCE_PREFIX = (
    ("app.signals", "📡 [信号] "),
    ("app.protection", "🛡️ [仓位保护] "),
    ("app.reports", "📰 [报告] "),
)

_SINK_ID: int | None = None


def _is_forwardable(record: dict) -> bool:
    return any(record["name"].startswith(mod) for mod, _ in _SOURCE_PREFIX)


def _forward(message) -> None:
    record = message.record
    if not _is_forwardable(record):
        return  # 双保险：loguru filter 已拦截，直调 _forward 时也保持一致
    level = _LEVEL_MAP.get(record["level"].name)
    text = record["message"]
    if level is None or "[仓位保护]" in text:
        # notifier 已推送 UI 的告警不重复转发
        return
    # 仓位保护的 INFO 全是心跳/状态行（每仓每轮一条“巡检中/止盈止损位/黑天鹅监控:正常”），
    # 几十个仓位下来会把真正的告警淹没。这类只留控制台，UI 只收 SUCCESS/WARNING/ERROR 事件。
    if record["name"].startswith("app.protection") and level == "info":
        return
    prefix = next((p for mod, p in _SOURCE_PREFIX if record["name"].startswith(mod)), "")
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # 非事件循环线程：仅控制台可见
    loop.create_task(log_message(f"{prefix}{text}", level))


def install_ui_log_sink() -> None:
    """安装转发 sink（幂等，main 导入时调用）。"""
    global _SINK_ID
    if _SINK_ID is not None:
        return
    _SINK_ID = logger.add(_forward, level="INFO", filter=_is_forwardable)
