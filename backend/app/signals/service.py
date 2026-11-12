# backend/app/signals/service.py
"""信号引擎组装与生命周期管理（main.py lifespan 与 API 路由共用）。

- store / market_data / auto_trader / scanner / tracker / exit_executor 全部惰性单例；
- 共享 exchange 通过 get_shared_exchange 懒加载，扫描未启用时不会触达交易所；
- start/stop 供 lifespan 与 POST /api/signals/config 热应用调用；
- 行情单例由 `market_data.shared_market_data()` 持有，实盘 ATR 挂单也读这一份缓存。
"""
import asyncio
from typing import Any, Dict, Optional

from loguru import logger

from ..config.config import load_settings
from ..core.exchange_manager import get_shared_exchange
from ..core.trading_service import trading_service
from ..logic.exchange_logic_async import fetch_positions_with_pnl_async
from .auto_trader import SignalAutoTrader
from .dispatcher import SignalDispatcher
from .exit_executor import LiveExitExecutor
from .market_data import MarketDataService, shared_market_data
from .runtime import emit_signal  # noqa: F401  供外部统一导入
from .scanner import SignalScanner
from .signal_store import SignalStore
from .tracker import OutcomeTracker

store = SignalStore()
auto_trader: Optional[SignalAutoTrader] = None
scanner: Optional[SignalScanner] = None
tracker: Optional[OutcomeTracker] = None
exit_executor: Optional[LiveExitExecutor] = None


def get_market_data() -> MarketDataService:
    """对外暴露行情服务单例（周期报告 / 实盘 ATR 止损复用同一缓存与限流器）。

    单例由 `market_data.shared_market_data()` 管理，本函数只是稳定入口。
    """
    return shared_market_data()


def _get_auto_trader() -> SignalAutoTrader:
    global auto_trader
    if auto_trader is None:
        auto_trader = SignalAutoTrader(
            settings_loader=load_settings,
            position_provider=_fetch_positions,
            open_callback=_open_from_signal,
        )
        auto_trader._store = store  # 开仓提交时更新 last_auto_open 快照
    return auto_trader


def _get_tracker() -> OutcomeTracker:
    global tracker
    if tracker is None:
        tracker = OutcomeTracker(
            settings_loader=load_settings,
            market_data=get_market_data(),
            store=store,
        )
    return tracker


def _get_scanner() -> SignalScanner:
    global scanner
    if scanner is None:
        scanner = SignalScanner(
            settings_loader=load_settings,
            store=store,
            market_data=get_market_data(),
            exchange_provider=get_shared_exchange,
        )
    return scanner


async def _fetch_positions() -> list:
    """自动开仓过滤链的持仓提供者（共享 exchange，只读）。"""
    exchange = await get_shared_exchange()
    settings = load_settings()
    return await fetch_positions_with_pnl_async(exchange, settings.get('leverage', 1))


async def _close_position(full_symbol: str) -> bool:
    """实盘超时平仓：市价全平指定交易对（只对登记过的自动仓调用）。"""
    from ..core.websocket_manager import log_message
    from ..logic.exchange_logic_async import close_position_async

    exchange = await get_shared_exchange()
    return await close_position_async(exchange, full_symbol, 1.0, log_message, asyncio.Event())


def _get_exit_executor() -> LiveExitExecutor:
    global exit_executor
    if exit_executor is None:
        exit_executor = LiveExitExecutor(
            settings_loader=load_settings,
            position_provider=_fetch_positions,
            close_callback=_close_position,
        )
    return exit_executor


async def _open_from_signal(signal: Dict[str, Any]) -> bool:
    """open_callback：委托 TradingService.auto_open_from_signal，成交后登记实盘出场。"""
    config = load_settings()
    return await trading_service.auto_open_from_signal(
        signal, config,
        on_opened=lambda: _get_exit_executor().register(signal))


# ------------------------------------------------------------------ 消费循环
# 信号分发（展示/推送/开仓）统一由 SignalDispatcher 编排，service 只负责装配与生命周期。
_dispatcher: Optional[SignalDispatcher] = None


def _get_dispatcher() -> SignalDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = SignalDispatcher(store=store, auto_trader=_get_auto_trader(),
                                       tracker=_get_tracker())
    return _dispatcher


async def start_consumer() -> None:
    _get_dispatcher().start()


async def stop_consumer() -> None:
    await _get_dispatcher().stop()


# ------------------------------------------------------------------ 生命周期
async def startup_signals() -> None:
    """FastAPI lifespan 启动：默认 signal_scan_enabled=False，不触达交易所。"""
    from . import runtime as _runtime
    _runtime.load_alert_states()
    await start_consumer()
    _get_tracker().start()
    _get_exit_executor().start()
    settings = load_settings()
    store.update_auto_status(auto_trade_enabled=bool(settings.get('signal_auto_trade_enabled', False)))
    if settings.get('signal_scan_enabled', False):
        await _get_scanner().start()
    else:
        logger.info("信号扫描未启用（默认关闭），启动时不发起任何行情请求。")


async def shutdown_signals() -> None:
    """FastAPI lifespan 关闭：停止扫描与消费循环（共享 exchange 由 main 关闭）。"""
    if scanner is not None:
        await scanner.stop()
    if tracker is not None:
        await tracker.stop()
    if exit_executor is not None:
        await exit_executor.stop()
    await stop_consumer()


async def apply_signal_config(settings: Dict[str, Any]) -> Dict[str, Any]:
    """配置热应用：扫描开关变化时启动/停止扫描循环，返回 signal_* 配置子集。"""
    store.update_auto_status(auto_trade_enabled=bool(settings.get('signal_auto_trade_enabled', False)))
    if settings.get('signal_scan_enabled', False):
        if scanner is None or not scanner.is_loop_running():
            await _get_scanner().start()
    else:
        if scanner is not None:
            await scanner.stop()
    return {k: v for k, v in settings.items() if str(k).startswith('signal_')}
