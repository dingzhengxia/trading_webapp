# backend/app/signals/trend_filter.py
"""日线趋势过滤器（自动开仓的第 2.5 道闸）。

用户口径：日线是空头趋势就只允许开空，多头趋势只允许开多。
趋势判定**复用 analysis/trend.get_current_trend**（钉钉文案用的同一份实现，
三线 EMA 严格排列：fast>medium>long 才算多头）——保证自动开仓的过滤口径
与推送文案完全一致，不会出现"钉钉写着空头趋势却开了多单"的自相矛盾。
判定周期固定日线（用户明确要求看日线），参数走 signal_config.json 的
trend_ema_long 组（26/50/120）。

结果映射：多头趋势 → 'long'（只放行做多）；空头趋势 → 'short'；
震荡趋势 / 趋势未知 / 行情异常 → 'neutral'（放行——过滤器故障绝不能
变成"一个仓都不开"，与 dispatcher 的降级风格一致）。

结果按 symbol 缓存（默认 30 分钟）：日线趋势一天内变化极小，不值得每个
信号都拉一次 K 线；行情请求经 MarketDataService（内含 RestGuardian +
in-flight 去重），与信号扫描共用同一份限流合规层。
"""
import time
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

import pandas as pd
from loguru import logger

from .analysis.trend import get_current_trend

# 中文趋势标签 → 过滤链方向；震荡/未知一律 neutral（放行）
_TREND_MAP = {'多头趋势': 'long', '空头趋势': 'short'}


class TrendFilter:
    """基于日线三线 EMA（get_current_trend）的趋势判定 + TTL 缓存。"""

    def __init__(self, market_data: Any, strategy_config: Callable[[], Dict[str, Any]],
                 timeframe: str = '1d', cache_seconds: float = 1800.0,
                 neutral_cache_seconds: float = 0.0):
        """
        :param market_data: MarketDataService 单例（K 线缓存 + RestGuardian）
        :param strategy_config: 返回 signal_config（含 strategy_params.trend_ema_long），
                                复用 build_scan_config 保证与信号生成同一份参数
        :param timeframe: 趋势判定周期，固定日线
        :param cache_seconds: 判定结果缓存时长；0 = 不缓存
        :param neutral_cache_seconds: 震荡/无数据结果的缓存时长。
            开仓链路保持 0（故障恢复后立刻重试，宁可多问一次）；
            展示链路（信号列表 10s 轮询）必须大于 0，否则震荡币会被反复重拉日线。
        """
        self._market_data = market_data
        self._strategy_config = strategy_config
        self._timeframe = timeframe
        self._cache_seconds = max(0.0, float(cache_seconds))
        self._neutral_cache_seconds = max(0.0, float(neutral_cache_seconds))
        # symbol → (cached_at_monotonic, trend)；缓存关闭时永远为空
        self._cache: Dict[str, Tuple[float, str]] = {}

    async def trend_of(self, symbol: str) -> str:
        """返回 'long' | 'short' | 'neutral'。任何异常降级为 neutral（放行）。"""
        cached = self._cache.get(symbol)
        if cached:
            ttl = self._cache_seconds if cached[1] != 'neutral' else self._neutral_cache_seconds
            if ttl > 0 and time.monotonic() - cached[0] < ttl:
                return cached[1]
        trend = await self._compute(symbol)
        ttl = self._cache_seconds if trend != 'neutral' else self._neutral_cache_seconds
        if ttl > 0:
            # 默认 neutral 不缓存：多半是行情暂时拿不到，下一轮再试
            self._cache[symbol] = (time.monotonic(), trend)
        return trend

    async def _compute(self, symbol: str) -> str:
        try:
            rows = await self._market_data.get_ohlcv(symbol, self._timeframe, limit=200)
        except Exception as e:
            logger.warning(f"📈 [趋势] {symbol} 拉 {self._timeframe} K线失败（放行）: {e}")
            return 'neutral'

        closes = [float(r[4]) for r in (rows or []) if len(r) > 4 and r[4]]
        if len(closes) < 60:
            # 三线 EMA（最长 120 期）拿不满判不出可靠趋势，放行（新上市币种）
            return 'neutral'

        df = pd.DataFrame({'close': closes})
        try:
            status, _emoji = get_current_trend(df, self._timeframe,
                                               self._strategy_config().get('strategy_params') or {})
        except Exception as e:
            logger.warning(f"📈 [趋势] {symbol} 日线趋势判定异常（放行）: {e}")
            return 'neutral'
        return _TREND_MAP.get(status, 'neutral')


def make_trend_provider(get_filter: Callable[[], Optional[TrendFilter]],
                        settings_loader: Callable[[], Dict[str, Any]],
                        symbol_of: Callable[[Dict[str, Any]], str],
                        ) -> Callable[[Dict[str, Any]], Awaitable[str]]:
    """装配出 auto_trader 过滤链用的 trend_provider。

    :param get_filter: 返回 TrendFilter 单例（可惰性创建）；None = 功能未装配，放行
    :param settings_loader: 读 signal_auto_trade_trend_* 配置
    :param symbol_of: 从信号 record 取查询用的完整交易对（full_symbol 优先于 base symbol）
    """

    async def provider(signal: Dict[str, Any]) -> str:
        settings = settings_loader() or {}
        if not bool(settings.get('signal_auto_trade_trend_filter_enabled', True)):
            return 'neutral'
        trend_filter = get_filter()
        if trend_filter is None:
            return 'neutral'
        return await trend_filter.trend_of(symbol_of(signal))

    return provider
