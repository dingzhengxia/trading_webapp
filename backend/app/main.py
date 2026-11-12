# backend/app/main.py
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import positions, protection, rebalance, reports, settings, signals, trading
from .api import status as status_router  # status 模块与 fastapi.status 避免命名冲突
from .core import database
from .core.exchange_manager import close_shared_exchange
from .core.paths import IS_DOCKER
from .core.security import access_key_warning, verify_ws_token, ws_auth_disabled
from .core.ui_log_sink import install_ui_log_sink
from .core.websocket_manager import log_message, manager
from .protection.service import shutdown_protection, startup_protection
from .reports.service import shutdown_reports, startup_reports
from .signals.service import shutdown_signals, startup_signals

from loguru import logger

# monitor 引擎（信号/仓位保护）日志转发到网页日志抽屉（幂等）
install_ui_log_sink()

STATIC_FILES_DIR = Path(__file__).resolve().parent / "frontend_dist"


def init_app_storage() -> None:
    """应用启动时初始化持久化存储（幂等，可重复调用）。

    T13（P2-5）：此前由 app.config 在 import 时调用 database.init_db() 与
    load_coin_lists()，导致「import 即建库/读库」——任何单测或工具脚本导入
    app 都会在项目根落一个 data/app.db。现在两步都收进应用生命周期的
    显式阶段，只在 lifespan 中执行。
    """
    database.init_db()
    # 函数内 late import：币种池加载依赖 init_db 建好的表
    from .config import config as app_config

    app_config.load_coin_lists()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 白名单：以下启动横幅允许使用 print（见 test_engineering_hygiene.py）---
    init_app_storage()
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
    # 周期报告：默认 periodic_reports 全部 enabled=False，不发起任何行情请求
    try:
        await startup_reports()
    except Exception as e:
        print(f"--- [WARNING] 周期报告启动失败（不影响交易主功能）: {e} ---")
    print("---" * 20)
    yield
    await shutdown_reports()
    await shutdown_protection()
    await shutdown_signals()
    await close_shared_exchange()
    print("--- Application shutdown complete. ---")


app = FastAPI(title="Trading API", lifespan=lifespan)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_message = f"Unhandled exception for request {request.method} {request.url}: {exc}"
    logger.error("--- [FATAL] {} ---", error_message)
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
app.include_router(reports.router)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # R-P0-5 WS 鉴权：握手阶段校验 ?token=（与 REST 同一把 app_access_key）。
    # 失败 → 记 warning（不含 token 内容）→ accept 后立即 close(4401)，不进入广播循环。
    if ws_auth_disabled():
        logger.error(
            "🚨 安全告警：WS_AUTH_DISABLED=1 已生效，WebSocket 鉴权已关闭！"
            "任何能访问端口的人都可以接收交易日志/持仓推送，仅限本机调试使用。")
    else:
        token = websocket.query_params.get('token', '')
        if not verify_ws_token(token):
            logger.warning("WebSocket 握手被拒绝：缺少或无效的访问 token。")
            await websocket.accept()
            await websocket.close(code=4401)
            return
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
        logger.error(
            "--- [ERROR] 未找到前端静态目录: {}。请确认前端已构建并复制到该目录，"
            "否则 / 路由不可用。---", STATIC_FILES_DIR)
    else:
        assets_dir = STATIC_FILES_DIR / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
        else:
            logger.warning(
                "--- [WARNING] 未找到前端静态资源目录: {}，跳过 /assets 挂载。---", assets_dir)

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
