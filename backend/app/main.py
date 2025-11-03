# backend/app/main.py (修正命名衝突後的完整代碼)
import os
from pathlib import Path
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# --- 核心修改：為 status 路由使用別名 ---
from .api import positions, trading, rebalance, settings
from .api import status as status_router # 將 status 模組導入為 status_router
# --- 修改結束 ---
from .core.websocket_manager import manager, log_message
from .core.security import APP_ACCESS_KEY

app = FastAPI(title="Trading API")

IS_DOCKER = os.environ.get("IS_DOCKER")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_message = f"Unhandled exception for request {request.method} {request.url}: {exc}"
    print(f"--- [FATAL] {error_message} ---")
    await log_message(f"服务器内部错误: {exc}", "error")
    # 這裡的 status 現在可以正確地引用從 fastapi 導入的 status 物件
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected server error occurred. Check server logs and UI logs for details."},
    )


app.include_router(settings.router)
app.include_router(positions.router)
app.include_router(trading.router)
app.include_router(rebalance.router)
# --- 核心修改：使用新的別名來註冊路由 ---
app.include_router(status_router.router)
# --- 修改結束 ---


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                # REFACTOR: 增加心跳響應邏輯
                message = json.loads(data)
                if isinstance(message, dict) and message.get('type') == 'ping':
                    await websocket.send_text('{"type":"pong"}')
            except json.JSONDecodeError:
                # 忽略無法解析的或非json格式的消息
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)


if IS_DOCKER:
    STATIC_FILES_DIR = Path(__file__).resolve().parent / "frontend_dist"
    if not STATIC_FILES_DIR.exists():
        print(
            f"--- [ERROR] Frontend directory not found at {STATIC_FILES_DIR}. Make sure the frontend was built correctly. ---")

    app.mount("/assets", StaticFiles(directory=STATIC_FILES_DIR / "assets"), name="assets")


    @app.get("/{full_path:path}")
    async def serve_vue_app(request: Request):
        index_path = STATIC_FILES_DIR / "index.html"
        if not index_path.exists():
            return JSONResponse(
                {"error": f"Frontend entry point (index.html) not found at {index_path}"},
                status_code=500
            )
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


@app.on_event("startup")
async def startup_event():
    print("---" * 20)
    print("✅ Application startup complete.")
    print(f"🔑 Your APP_ACCESS_KEY is: {APP_ACCESS_KEY}")
    print("---" * 20)


@app.on_event("shutdown")
async def shutdown_event():
    pass