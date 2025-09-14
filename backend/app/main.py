from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles # <-- 核心修复：导入 StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import asyncio

from .api import positions, trading, rebalance, settings
from .core.exchange_manager import close_exchange
from .core.websocket_manager import manager
from .core.trading_service import trading_service

app = FastAPI(title="Trading API")

# 定义前端构建文件的路径
# Path(__file__) -> .../backend/app/main.py -> .parent -> .../backend/app/
STATIC_FILES_DIR = Path(__file__).resolve().parent / "frontend_dist"

# 挂载 `assets` 目录，让 FastAPI 可以提供 CSS, JS 文件
app.mount(
    "/assets",
    StaticFiles(directory=STATIC_FILES_DIR / "assets"),
    name="assets"
)

# API 路由
app.include_router(settings.router)
app.include_router(positions.router)
app.include_router(trading.router)
app.include_router(rebalance.router)

# WebSocket 路由
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# “全匹配”路由，用于提供单页应用 (SPA)
@app.get("/{full_path:path}")
async def serve_vue_app(request: Request):
    index_path = STATIC_FILES_DIR / "index.html"
    if not index_path.exists():
        return {"error": "Frontend not built. Run 'npm run build' in frontend directory."}
    return FileResponse(index_path)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(trading_service.start_worker())

@app.on_event("shutdown")
async def shutdown_event():
    # 在生产环境中，可以根据需要决定是否关闭连接
    # await close_exchange()
    pass