# backend/app/main.py
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import positions, protection, rebalance, settings, signals, trading
from .api import status as status_router  # status 模块与 fastapi.status 避免命名冲突
from .core.exchange_manager import close_shared_exchange
from .core.security import access_key_warning
from .core.websocket_manager import log_message, manager
from .protection.service import shutdown_protection, startup_protection
from .signals.service import shutdown_signals, startup_signals

IS_DOCKER = os.environ.get("IS_DOCKER")
STATIC_FILES_DIR = Path(__file__).resolve().parent / "frontend_dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("---" * 20)
    print("[OK] Application startup complete.")
    warning = access_key_warning()
    if warning:
        print(warning)
        await log_message(warning, "error")
    else:
        print("[SECURITY] 访问密钥已配置（启动日志不展示密钥内容）。")
    # 信号引擎：默认 signal_scan_enabled=False，启动不发起任何行情请求
    try:
        await startup_signals()
    except Exception as e:
        print(f"--- [WARNING] 信号引擎启动失败（不影响交易主功能）: {e} ---")
    # 仓位保护：默认 position_protection.enabled=False，只有打开开关才会轮询交易所
    try:
        await startup_protection()
    except Exception as e:
        print(f"--- [WARNING] 仓位保护启动失败（不影响交易主功能）: {e} ---")
    print("---" * 20)
    yield
    await shutdown_protection()
    await shutdown_signals()
    await close_shared_exchange()
    print("--- Application shutdown complete. ---")


app = FastAPI(title="Trading API", lifespan=lifespan)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_message = f"Unhandled exception for request {request.method} {request.url}: {exc}"
    print(f"--- [FATAL] {error_message} ---")
    await log_message(f"服务器内部错误: {exc}", "error")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected server error occurred. Check server logs and UI logs for details."},
    )


app.include_router(settings.router)
app.include_router(positions.router)
app.include_router(trading.router)
app.include_router(rebalance.router)
app.include_router(status_router.router)
app.include_router(signals.router)
app.include_router(protection.router)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                # 心跳响应
                message = json.loads(data)
                if isinstance(message, dict) and message.get('type') == 'ping':
                    await websocket.send_text('{"type":"pong"}')
            except json.JSONDecodeError:
                # 忽略无法解析或非 JSON 格式的消息
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)


if IS_DOCKER:
    if not STATIC_FILES_DIR.exists():
        # Docker 模式下静态目录缺失时只给出明确日志，不因挂载失败而崩溃
        print(f"--- [ERROR] 未找到前端静态目录: {STATIC_FILES_DIR}。"
              f"请确认前端已构建并复制到该目录，否则 / 路由不可用。---")
    else:
        assets_dir = STATIC_FILES_DIR / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
        else:
            print(f"--- [WARNING] 未找到前端静态资源目录: {assets_dir}，跳过 /assets 挂载。---")

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

    # 使用请求头鉴权，不使用 Cookie 凭据，因此关闭 allow_credentials 以符合 CORS 规范
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
