# backend/app/main.py (已修复启动错误)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import os

from .api import positions, trading, rebalance, settings
from .core.websocket_manager import manager
# trading_service 依然需要导入，但我们不再调用它的方法
from .core.trading_service import trading_service

app = FastAPI(title="Trading API")

IS_DOCKER = os.environ.get("IS_DOCKER")

# API 和 WebSocket 路由
app.include_router(settings.router)
app.include_router(positions.router)
app.include_router(trading.router)
app.include_router(rebalance.router)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# 生产环境下的静态文件托管
if IS_DOCKER:
    STATIC_FILES_DIR = Path(__file__).resolve().parent / "frontend_dist"

    app.mount(
        "/assets",
        StaticFiles(directory=STATIC_FILES_DIR / "assets"),
        name="assets"
    )

    @app.get("/{full_path:path}")
    async def serve_vue_app(request: Request):
        index_path = STATIC_FILES_DIR / "index.html"
        if not index_path.exists():
            return {"error": "Frontend not built."}
        return FileResponse(index_path)

# 本地开发环境下的 CORS 设置
else:
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=[