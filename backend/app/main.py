# backend/app/main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from .api import positions, trading, rebalance, settings
from .core.websocket_manager import manager

app = FastAPI(title="Trading API")

# --- 核心修改：静态文件托管 ---

# 1. 定义前端构建文件的路径
#    Path(__file__).resolve() -> .../backend/app/main.py
#    .parent -> .../backend/app/
#    .parent -> .../backend/
#    .parent -> .../ (项目根目录)
#    / "frontend" / "dist"
STATIC_FILES_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

# 2. 挂载 `assets` 目录，让 FastAPI 可以提供 CSS, JS 文件
#    注意路径是相对于 STATIC_FILES_DIR
app.mount(
    "/assets",
    StaticFiles(directory=STATIC_FILES_DIR / "assets"),
    name="assets"
)

# 3. API 路由 (保持不变)
app.include_router(settings.router)
app.include_router(positions.router)
app.include_router(trading.router)
app.include_router(rebalance.router)

# 4. WebSocket 路由 (保持不变)
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# 5. 根路由和“全匹配”路由，始终返回前端的 index.html
#    这对于单页应用 (SPA) 的路由至关重要
@app.get("/{full_path:path}")
async def serve_vue_app(request: Request, full_path: str):
    index_path = STATIC_FILES_DIR / "index.html"
    if not index_path.exists():
        return {"error": "Frontend not built. Please run 'npm run build' in the frontend directory."}
    return FileResponse(index_path)

# --- 修改结束 ---