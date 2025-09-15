# backend/app/main.py (完整代码)
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import os

from .api import positions, trading, rebalance, settings, status
from .core.websocket_manager import manager
from .core.trading_service import trading_service

app = FastAPI(title="Trading API")

IS_DOCKER = os.environ.get("IS_DOCKER")

app.include_router(settings.router)
app.include_router(positions.router)
app.include_router(trading.router)
app.include_router(rebalance.router)
app.include_router(status.router)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if IS_DOCKER:
    STATIC_FILES_DIR = Path(__file__).resolve().parent / "frontend_dist"
    app.mount("/assets", StaticFiles(directory=STATIC_FILES_DIR / "assets"), name="assets")
    @app.get("/{full_path:path}")
    async def serve_vue_app(request: Request):
        index_path = STATIC_FILES_DIR / "index.html"
        if not index_path.exists():
            return {"error": "Frontend not built."}
        return FileResponse(index_path)
else:
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

@app.on_event("shutdown")
async def shutdown_event():
    pass