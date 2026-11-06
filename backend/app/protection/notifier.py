# backend/app/protection/notifier.py
"""仓位保护告警输出。

原 monitor 通过钉钉/桌面通知推送；并入 WebApp 后统一走「UI 日志（WebSocket）+ loguru」，
不依赖任何外部通道或密钥。函数保持同步签名，内部把广播任务丢给当前事件循环，
不阻塞风控主循环。
"""
import asyncio
from typing import Optional

from loguru import logger

from ..core.websocket_manager import log_message

_LEVEL_MAP = (
    ("止盈", "success"),
    ("警告", "warning"),
    ("错误", "error"),
)


def _level_of(title: str) -> str:
    for keyword, level in _LEVEL_MAP:
        if keyword in title:
            return level
    return "info"


def send_alert(config=None, title: str = "", message: str = "", symbol: str = "N/A",
               image_path: Optional[str] = None) -> None:
    """输出仓位保护告警（同步、非阻塞）。

    保留 monitor 的调用签名（config/title/message/symbol/image_path）以零改动复用引擎，
    config 与 image_path 仅用于兼容，不再使用。
    """
    text = f"🛡️ [仓位保护] {title} | {symbol} | {message}"
    logger.warning(text)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(log_message(text, _level_of(title)))
