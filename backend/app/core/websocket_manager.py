# backend/app/core/websocket_manager.py (最终修复版)
import asyncio
import datetime
import json
from collections import deque
from typing import List, Deque

from fastapi import WebSocket

LOG_HISTORY: Deque[dict] = deque(maxlen=200)

class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        # 持有后台任务引用，避免 "Task was destroyed but it is pending"/提前 GC
        self._tasks: set[asyncio.Task] = set()

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        if LOG_HISTORY:
            self._spawn(self.send_history(websocket))

    async def send_history(self, websocket: WebSocket):
        try:
            await websocket.send_text(json.dumps({
                "type": "log", "payload": {"message": "--- 加载历史日志 ---", "level": "info", "timestamp": ""}
            }))
            for log_entry in list(LOG_HISTORY):
                await websocket.send_text(json.dumps(log_entry))
        except Exception:
            self.disconnect(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        """广播消息：立即返回，不在交易主流程上等待任何客户端。

        调用方多为下单/平仓链路中的日志上报，若同步等待所有 WebSocket 写完，
        任一慢客户端（切后台、断网未 FIN）都会把订单流程卡住。因此改为后台发送，
        单连接 3 秒超时，失败即摘除该连接。
        """
        if data.get("type") == "log":
            LOG_HISTORY.append(data)
        if not self.active_connections:
            return
        message = json.dumps(data)
        self._spawn(self._send_all(message))

    async def _send_all(self, message: str) -> None:
        for conn in list(self.active_connections):
            try:
                await asyncio.wait_for(conn.send_text(message), timeout=3)
            except Exception:
                self.disconnect(conn)

manager = WebSocketManager()

async def log_message(message: str, level: str = "normal"):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    await manager.broadcast({"type": "log", "payload": {"message": message, "level": level, "timestamp": timestamp}})

async def update_status(message: str, is_running: bool = None):
    payload = {"message": message}
    if is_running is not None: payload["isRunning"] = is_running
    await manager.broadcast({"type": "status", "payload": payload})

# --- 核心修改在这里 ---
# 将函数签名中的参数名改为与调用时一致的关键字参数名
async def broadcast_progress_details(success_count: int, failed_count: int, total: int, task_name: str, is_final: bool = False):
    """广播详细的任务进度，包括成功、失败和总数"""
    await manager.broadcast({
        "type": "progress_update",
        "payload": {
            "success_count": success_count,
            "failed_count": failed_count,
            "total": total,
            "task_name": task_name,
            "is_final": is_final
        }
    })
# --- 修改结束 ---