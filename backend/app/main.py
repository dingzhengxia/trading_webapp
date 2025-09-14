from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio

from .api import positions, trading, rebalance, settings
from .core.websocket_manager import manager
from .core.trading_service import trading_service

app = FastAPI(title="Trading API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """应用启动时，启动交易任务 worker"""
    asyncio.create_task(trading_service.start_worker())

app.include_router(settings.router)
app.include_router(positions.router)
app.include_router(trading.router)
app.include_router(rebalance.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to the Trading API"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)