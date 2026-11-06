# backend/app/protection/__init__.py
"""Phase 3：monitor 项目的仓位保护引擎（WS 实时风控）并入后端。"""

from .service import get_protection_status, restart_protection, shutdown_protection, startup_protection

__all__ = [
    "get_protection_status",
    "restart_protection",
    "shutdown_protection",
    "startup_protection",
]
