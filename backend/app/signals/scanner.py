# backend/app/signals/scanner.py
"""异步信号扫描循环 + 手动触发（MERGE_PLAN §4）。

单个扫描周期：
1. tickers = await market_data.get_tickers()（每轮一次）；
2. 目标币种 = signal_scan_static_symbols ∪ TopN（按 quoteVolume 降序，排除稳定币/黑名单，
   同 base 去重，USDC 优先）；
3. 对每个 (symbol, timeframe)：每轮每 key 只拉一次 K 线，同一份 df 跑该 timeframe 下
   所有启用策略（asyncio.to_thread 线程池执行）；
4. 每轮结束更新 status；异常记录 last_error。
"""
import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

import pandas as pd
from loguru import logger

from ..core.tasks import cancel_task
from . import runtime
from .analysis.strategies import (
    check_ema_signals, check_kdj_cross, check_volatility_breakout,
    check_level_breakout, check_rsi_divergence, check_consecutive_candles,
    check_trend_channel_breakout, check_ob_luxalgo, check_ob_fluxcharts,
    check_ma_breakout, _get_params_for_timeframe,
)
from .market_data import STABLE_BASES
from .config_store import (  # noqa: F401  (load_signal_config 保持旧导入路径可用)
    FALLBACK_SIGNAL_CONFIG, SIGNAL_CONFIG_FILE, load_signal_config,
)

# 策略注册表：name -> (函数, K线数量 limit)（与 monitor signal_scanner.py 一致）
STRATEGY_MAP: Dict[str, Dict[str, Any]] = {
    'ema_cross': {'func': check_ema_signals, 'limit': 170},
    'ma_breakout': {'func': check_ma_breakout, 'limit': 150},
    'kdj_cross': {'func': check_kdj_cross, 'limit': 170},
    'volatility_breakout': {'func': check_volatility_breakout, 'limit': 170},
    'level_breakout': {'func': check_level_breakout, 'limit': 400},
    'rsi_divergence': {'func': check_rsi_divergence, 'limit': 170},
    'trend_channel_breakout': {'func': check_trend_channel_breakout, 'limit': 350},
    'consecutive_candles': {'func': check_consecutive_candles, 'limit': 50},
    'ob_luxalgo': {'func': check_ob_luxalgo, 'limit': 250},
    'ob_fluxcharts': {'func': check_ob_fluxcharts, 'limit': 250},
}

MIN_SCAN_INTERVAL_SEC = 30


def build_scan_config(settings: Dict[str, Any]) -> Dict[str, Any]:
    """合并策略配置（DB 优先，见 config_store）与 user_settings 中的 signal_* 覆盖项。"""
    config = load_signal_config()
    market_settings = config.setdefault('market_settings', {})
    # 静态币种与时间框架以 user_settings 的 signal_* 键为准
    market_settings['static_symbols'] = list(settings.get('signal_scan_static_symbols') or [])
    config['user_settings'] = {k: v for k, v in (settings or {}).items() if str(k).startswith('signal_')}
    return config


def _static_full_symbols(bases: List[str], markets: Dict[str, Any]) -> List[str]:
    """静态币种解析为完整交易对：USDC 优先，其次 USDT。"""
    result = []
    for base in bases or []:
        base_upper = str(base).strip().upper()
        if not base_upper:
            continue
        for quote in ('USDC', 'USDT'):
            for candidate in (f"{base_upper}/{quote}:{quote}", f"{base_upper}/{quote}"):
                if candidate in markets:
                    result.append(candidate)
                    break
            else:
                continue
            break
    return result


def _enabled_param_sets(config: Dict[str, Any], timeframe: str) -> List[tuple]:
    """展开某周期下真正要跑的 (策略名, 函数, 参数, 参数序号)。

    跳过未 enabled 的参数组与 exclude_timeframes 命中的周期；供计算 K 线数量
    与实际执行两处复用，避免同一套过滤条件写两遍。
    """
    result = []
    for name, info in STRATEGY_MAP.items():
        raw = config.get('strategy_params', {}).get(name, {})
        for index, base_params in enumerate(raw if isinstance(raw, list) else [raw]):
            if not isinstance(base_params, dict) or not base_params.get('enabled', False):
                continue
            final_params = _get_params_for_timeframe(base_params, timeframe)
            if timeframe in final_params.get('exclude_timeframes', []):
                continue
            result.append((name, info['func'], info['limit'], final_params, index))
    return result


class SignalScanner:
    """信号扫描器：后台循环 + 手动触发；同一时刻只跑一轮（并发保护）。"""

    def __init__(self, settings_loader: Callable[[], Dict[str, Any]], store,
                 market_data, exchange_provider: Callable[[], Any]):
        self._settings_loader = settings_loader
        self._store = store
        self._market_data = market_data
        self._exchange_provider = exchange_provider
        self._scan_lock = asyncio.Lock()
        self._loop_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._interval_seconds = MIN_SCAN_INTERVAL_SEC

    # -------------------------------------------------------------- 生命周期
    async def start(self) -> bool:
        """enabled 时创建后台循环 task（幂等）。"""
        settings = self._settings_loader()
        if not settings.get('signal_scan_enabled', False):
            logger.info("信号扫描未启用（signal_scan_enabled=False），不启动扫描循环。")
            return False
        if self._loop_task is not None and not self._loop_task.done():
            return True
        runtime.load_alert_states()
        self._stop_event.clear()
        self._interval_seconds = max(MIN_SCAN_INTERVAL_SEC, int(settings.get('signal_scan_interval_seconds', 300)))
        self._loop_task = asyncio.create_task(self._run_loop())
        logger.info(f"信号扫描循环已启动，间隔 {self._interval_seconds} 秒。")
        return True

    async def stop(self) -> None:
        self._stop_event.set()
        task, self._loop_task = self._loop_task, None
        await cancel_task(task)
        logger.info("信号扫描循环已停止。")

    # -------------------------------------------------------------- 状态
    def is_loop_running(self) -> bool:
        return self._loop_task is not None and not self._loop_task.done()

    def is_scanning(self) -> bool:
        return self._scan_lock.locked()

    def status(self) -> Dict[str, Any]:
        """快照 + 扫描开关真实状态（以扫描循环是否在跑为准，前端开关依赖此字段）。"""
        return {'enabled': self.is_loop_running(), **self._store.snapshot()}

    # -------------------------------------------------------------- 扫描
    async def scan_once(self) -> Dict[str, Any]:
        """手动/定时共用的一轮扫描；并发保护（同一时刻只跑一轮）。"""
        if self._scan_lock.locked():
            return {'skipped': True, 'reason': '已有扫描在进行中'}

        async with self._scan_lock:
            self._store.update_scan_status(running=True)
            try:
                result = await self._scan_cycle()
                self._store.update_scan_status(
                    last_scan_at=datetime.now(timezone.utc).isoformat(),
                    scanned_symbols=result.get('scanned_symbols', 0),
                    error_count=result.get('error_count', 0),
                    last_error=result.get('last_error'),
                )
                return result
            except Exception as e:
                logger.error(f"信号扫描周期异常: {e}", exc_info=True)
                prev_stats = self._store.snapshot()
                self._store.update_scan_status(
                    last_scan_at=datetime.now(timezone.utc).isoformat(),
                    last_error=str(e),
                    error_count=int(prev_stats.get('error_count', 0)) + 1,
                )
                return {'scanned_symbols': 0, 'error_count': 1, 'last_error': str(e)}
            finally:
                self._store.update_scan_status(running=False)

    async def _scan_cycle(self) -> Dict[str, Any]:
        settings = self._settings_loader()
        config = build_scan_config(settings)
        timeframes = [str(tf) for tf in (settings.get('signal_scan_timeframes') or ['1h', '4h'])]

        error_count = 0
        last_error: Optional[str] = None

        # 1. 顶部行情：每轮只请求一次 fetch_tickers
        try:
            await self._market_data.get_tickers()
        except Exception as e:
            error_count += 1
            last_error = f"获取全量行情失败: {e}"
            logger.warning(last_error)

        # 2. 目标币种：静态 ∪ TopN，同 base 去重（USDC 优先）
        exclude = sorted(STABLE_BASES | set(
            config.get('market_settings', {}).get('dynamic_scan', {}).get('exclude_symbols', []) or []))
        top_symbols: List[str] = []
        try:
            top_symbols = await self._market_data.get_top_symbols_by_volume(
                int(settings.get('signal_scan_top_n', 100)), exclude=exclude)
        except Exception as e:
            error_count += 1
            last_error = f"计算 TopN 币种失败: {e}"
            logger.warning(last_error)

        try:
            exchange = await self._exchange_provider()
            markets = getattr(exchange, 'markets', None) or {}
        except Exception as e:
            error_count += 1
            last_error = f"获取共享交易所失败: {e}"
            logger.error(last_error)
            return {'scanned_symbols': 0, 'error_count': error_count, 'last_error': last_error}

        static_symbols = _static_full_symbols(
            settings.get('signal_scan_static_symbols') or [], markets)
        symbols: List[str] = []
        seen_bases = set()
        for full_symbol in static_symbols + top_symbols:
            base = full_symbol.split('/')[0].upper()
            if base in seen_bases:
                continue
            seen_bases.add(base)
            symbols.append(full_symbol)

        # 更新热门币种缓存（indicators 动态排名依赖）
        runtime.cached_top_symbols.clear()
        runtime.cached_top_symbols.extend(symbols)

        if not symbols:
            logger.info("本轮无目标币种（TopN 与静态列表均为空），跳过。")
            return {'scanned_symbols': 0, 'error_count': error_count, 'last_error': last_error}

        # 3. K 线扫描：同周期内并发拉取（REST 速率由 RestGuardian 统一限制：
        #    并发 3 + 80ms 最小间隔 + 429/418 退避），每个 (symbol, timeframe) 只发一次请求
        def _run_strategies(full_symbol: str, timeframe: str, df, enabled_sets) -> List[str]:
            """线程内顺序跑该 (symbol, timeframe) 的全部启用策略（R-P1-3 合并派发）。"""
            thread_errors: List[str] = []
            for name, func, _limit, params, index in enabled_sets:
                if self._stop_event.is_set():
                    break
                try:
                    # 策略会往 df 写指标列，逐策略拷贝隔离
                    func(full_symbol, timeframe, config, df.copy(), params, index)
                except Exception as e:
                    thread_errors.append(f"策略 {name} @ {full_symbol} {timeframe}: {e}")
            return thread_errors

        async def _scan_one(timeframe: str, full_symbol: str) -> List[str]:
            """单个 (symbol, timeframe) 的拉取 + 全部策略计算；返回错误列表。"""
            errors: List[str] = []
            if self._stop_event.is_set():
                return errors
            try:
                raw_ohlcv = await self._market_data.get_ohlcv(full_symbol, timeframe, ohlcv_limit)
            except Exception as e:
                return [f"获取 {full_symbol} {timeframe} K线失败: {e}"]
            if not raw_ohlcv:
                return errors
            df = pd.DataFrame(raw_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            if df.empty:
                return errors
            # 一次 to_thread 顺序跑该组合全部策略：派发次数 O(策略数) → O(symbol×timeframe)
            errors.extend(await asyncio.to_thread(
                _run_strategies, full_symbol, timeframe, df, enabled))
            return errors

        for timeframe in timeframes:
            enabled = _enabled_param_sets(config, timeframe)
            if not enabled:
                continue
            ohlcv_limit = max(limit for _, _, limit, _, _ in enabled)
            results = await asyncio.gather(
                *(_scan_one(timeframe, symbol) for symbol in symbols),
                return_exceptions=True,
            )
            for item in results:
                if isinstance(item, BaseException):
                    error_count += 1
                    last_error = str(item)
                elif item:
                    error_count += len(item)
                    last_error = item[-1]

        return {'scanned_symbols': len(symbols), 'error_count': error_count, 'last_error': last_error}

    # -------------------------------------------------------------- 后台循环
    def _current_interval(self) -> int:
        """每轮重读 signal_scan_interval_seconds（R-P1-2 配置热更新）。

        设置页改完间隔后下一轮生效，无需重启扫描循环；非法值回退当前值。
        """
        try:
            settings = self._settings_loader()
            raw = int(settings.get('signal_scan_interval_seconds',
                                   self._interval_seconds))
        except (TypeError, ValueError, AttributeError):
            return self._interval_seconds
        return max(MIN_SCAN_INTERVAL_SEC, raw)

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            start = time.monotonic()
            try:
                await self.scan_once()
            except Exception as e:
                logger.error(f"扫描循环异常（指数退避后重试）: {e}")
            self._interval_seconds = self._current_interval()
            elapsed = time.monotonic() - start
            delay = max(self._interval_seconds, MIN_SCAN_INTERVAL_SEC)
            if self._store.snapshot().get('last_error'):
                # 上轮有错误：简单指数退避（上限为正常间隔的 4 倍）
                delay = min(delay * 2, self._interval_seconds * 4)
            if elapsed < delay:
                next_at = datetime.now(timezone.utc) + timedelta(seconds=delay - elapsed)
                self._store.update_scan_status(next_scan_at=next_at.isoformat())
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=delay - elapsed)
                    break  # stop_event 触发
                except asyncio.TimeoutError:
                    continue
