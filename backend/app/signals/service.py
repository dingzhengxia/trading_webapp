# backend/app/signals/service.py
"""信号引擎组装与生命周期管理（main.py lifespan 与 API 路由共用）。

- store / market_data / auto_trader / scanner 全部为模块级单例，惰性创建；
- 共享 exchange 通过 get_shared_exchange 懒加载，扫描未启用时不会触达交易所；
- start/stop 供 lifespan 与 POST /api/signals/config 热应用调用。
"""
import asyncio
from typing import Any, Dict, Optional

from loguru import logger

from ..config.config import load_settings
from ..core.exchange_manager import get_shared_exchange
from ..core.rest_guardian import RestGuardian
from ..core.trading_service import trading_service
from ..logic.exchange_logic_async import fetch_positions_with_pnl_async
from .auto_trader import SignalAutoTrader
from .dispatcher import SignalDispatcher
from .market_data import MarketDataService
from .runtime import emit_signal  # noqa: F401  供外部统一导入
from .scanner import SignalScanner
from .config_store import load_signal_config
from .signal_store import SignalStore
from .tracker import OutcomeTracker

store = SignalStore()
auto_trader: Optional[SignalAutoTrader] = None
scanner: Optional[SignalScanner] = None
market_data: Optional[MarketDataService] = None
tracker: Optional[OutcomeTracker] = None


def _build_rest_guardian() -> RestGuardian:
    """用策略配置（DB 优先，见 config_store）的 market_settings.api_limit 初始化 RestGuardian。"""
    try:
        api_limit = load_signal_config().get('market_settings', {}).get('api_limit', {})
    except Exception:
        api_limit = {}
    return RestGuardian(api_limit)


def _get_market_data() -> MarketDataService:
    global market_data
    if market_data is None:
        settings = load_settings()
        market_data = MarketDataService(
            get_shared_exchange,
            guardian=_build_rest_guardian(),
            ticker_ttl=float(settings.get('signal_ticker_cache_seconds', 30) or 30),
            ohlcv_ttl=float(settings.get('signal_ohlcv_cache_seconds', 30) or 30),
        )
    return market_data


def get_market_data() -> MarketDataService:
    """对外暴露行情服务单例（周期报告等模块复用同一缓存与限流器）。"""
    return _get_market_data()


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
            market_data=_get_market_data(),
            store=store,
        )
    return tracker


def _get_scanner() -> SignalScanner:
    global scanner
    if scanner is None:
        scanner = SignalScanner(
            settings_loader=load_settings,
            store=store,
            market_data=_get_market_data(),
            exchange_provider=get_shared_exchange,
        )
    return scanner


async def _fetch_positions() -> list:
    """自动开仓过滤链的持仓提供者（共享 exchange，只读）。"""
    exchange = await get_shared_exchange()
    settings = load_settings()
    return await fetch_positions_with_pnl_async(exchange, settings.get('leverage', 1))


async def _open_from_signal(signal: Dict[str, Any]) -> bool:
    """open_callback：委托 TradingService.auto_open_from_signal。"""
    config = load_settings()
    return await trading_service.auto_open_from_signal(signal, config)


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
