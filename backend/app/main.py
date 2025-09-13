from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .api import positions, trading, rebalance, settings
from .core.websocket_manager import manager

app = FastAPI(title="Trading API")

# --- 核心修复：CORS 配置 ---
# 在开发环境中，允许所有来源可以极大地简化调试过程。
# 在生产部署时，您应该将其替换为您的前端域名。
origins = [
    "http://localhost",
    "http://localhost:5173",
    "http://127.0.0.1",
    "http://127.0.0.1:5173",
    # 您也可以在这里添加您的具体IP地址，但使用通配符更方便
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # <-- 改为通配符 "*"，允许任何来源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有HTTP方法 (GET, POST, etc.)
    allow_headers=["*"],  # 允许所有HTTP头
)

# @app.on_event("shutdown")
# async def shutdown_event():
#     await close_exchange()

app.include_router(positions.router)
app.include_router(trading.router)
app.include_router(settings.router) # <-- 包含 settings 路由

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