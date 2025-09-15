from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import asyncio
import os

from .api import positions, trading, rebalance, settings
from .core.websocket_manager import manager
from .core.trading_service import trading_service

app = FastAPI(title="Trading API")

# --- 核心修复：根据环境决定行为 ---

# 检查是否在 Docker 生产环境中
IS_DOCKER = os.environ.get("IS_DOCKER")

if IS_DOCKER:
    # --- 生产环境 (Docker) 逻辑 ---
    # 静态文件托管
    STATIC_FILES_DIR = Path(__file__).resolve().parent / "frontend_dist"

    app.mount(
        "/assets",
        StaticFiles(directory=STATIC_FILES_DIR / "assets"),
        name="assets"
    )


    # 全匹配路由，提供 index.html
    @app.get("/{full_path:path}")
    async def serve_vue_app(request: Request):
        index_path = STATIC_FILES_DIR / "index.html"
        if not index_path.exists():
            return {"error": "Frontend not built."}
        return FileResponse(index_path)

else:
    # --- 本地开发环境逻辑 ---
    from fastapi.middleware.cors import CORSMiddleware

    # 只需要配置 CORS，允许前端开发服务器访问
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# --- 修复结束 ---


# API 路由 (对所有环境都生效)
app.include_router(settings.router)
app.include_router(positions.router)
app.include_router(trading.router)
app.include_router(rebalance.router)


# WebSocket 路由 (对所有环境都生效)
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# 应用生命周期事件 (对所有环境都生效)
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(trading_service.start_worker())


@app.on_event("shutdown")
async def shutdown_event():
    pass