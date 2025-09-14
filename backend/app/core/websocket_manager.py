import asyncio
import json
from typing import List, Deque
from collections import deque
from fastapi import WebSocket

LOG_HISTORY: Deque[dict] = deque(maxlen=200)


class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        # 新客户端连接时，立即发送历史日志
        if LOG_HISTORY:
            # 创建一个任务来发送历史记录，避免阻塞连接过程
            asyncio.create_task(self.send_history(websocket))

    async def send_history(self, websocket: WebSocket):
        try:
            # 发送历史日志前，先发一条分隔提示
            await websocket.send_text(json.dumps({
                "type": "log",
                "payload": {"message": "--- 加载历史日志 ---", "level": "info", "timestamp": ""}
            }))
            for log_entry in list(LOG_HISTORY):
                await websocket.send_text(json.dumps(log_entry))
        except Exception:
            # 客户端可能在发送历史期间断开
            pass

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        # 如果是日志，先存入历史记录
        if data.get("type") == "log":
            LOG_HISTORY.append(data)

        if not self.active_connections: return

        message = json.dumps(data)
        tasks = [conn.send_text(message) for conn in self.active_connections]
        await asyncio.gather(*tasks, return_exceptions=True)


manager = WebSocketManager()


async def log_message(message: str, level: str = "normal"):
    print(f"LOG ({level.upper()}): {message}")
    # 在广播前获取时间戳
    import datetime
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    await manager.broadcast({
        "type": "log",
        "payload": {"message": message, "level": level, "timestamp": timestamp}
    })


async def update_status(message: str, is_running: bool = None):
    payload = {"message": message}
    if is_running is not None:
        payload["isRunning"] = is_running
    await manager.broadcast({"type": "status", "payload": payload})