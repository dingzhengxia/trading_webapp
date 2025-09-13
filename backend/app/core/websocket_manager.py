import asyncio
import json
from typing import List
from fastapi import WebSocket

class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        if not self.active_connections: return
        message = json.dumps(data)
        tasks = [conn.send_text(message) for conn in self.active_connections]
        await asyncio.gather(*tasks, return_exceptions=True)

manager = WebSocketManager()

async def log_message(message: str, level: str = "normal"):
    print(f"LOG ({level.upper()}): {message}")
    await manager.broadcast({"type": "log", "payload": {"message": message, "level": level}})

async def update_status(message: str, is_running: bool = None):
    payload = {"message": message}
    if is_running is not None:
        payload["isRunning"] = is_running
    await manager.broadcast({"type": "status", "payload": payload})