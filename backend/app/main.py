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

IS_DOCKER = os.environ.get("IS_DOCKER")

# --- 核心修复：调整路由顺序 ---

# 1. API 和 WebSocket 路由 (最具体，必须放在最前面)
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


# 2. 静态文件托管 (只在生产环境生效)
if IS_DOCKER:
    STATIC_FILES_DIR = Path(__file__).resolve().parent / "frontend_dist"

    # 挂载 assets 目录
    app.mount(
        "/assets",
        StaticFiles(directory=STATIC_FILES_DIR / "assets"),
        name="assets"
    )


    # 3. “全匹配”路由 (最通用，必须放在最后面)
    @app.get("/{full_path:path}")
    async def serve_vue_app(request: Request):
        index_path = STATIC_FILES_DIR / "index.html"
        if not index_path.exists():
            return {"error": "Frontend not built."}
        return FileResponse(index_path)

else:
    # 本地开发时，只需要 CORS
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# --- 修复结束 ---

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(trading_service.start_worker())


@app.on_event("shutdown")
async def shutdown_event():
    pass