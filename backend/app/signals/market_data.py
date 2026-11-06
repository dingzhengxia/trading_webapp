# backend/app/signals/market_data.py
"""行情层：tickers/ohlcv/funding 缓存 + RestGuardian + 涨跌幅 TopN（MERGE_PLAN §2.3）。

要求：
- 所有 REST 请求经 RestGuardian（信号扫描只用 NORMAL/LOW 优先级）；
- 扫描循环内每个 (symbol, timeframe) 只请求一次 K 线（TTL 缓存 + in-flight 去重）；
- 顶部行情每轮只请求一次 fetch_tickers；资金费率用批量接口而不是逐 symbol；
- 失败/限流不崩溃，由调用方记录到扫描状态。
"""
import asyncio
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..core.rest_guardian import RestGuardian

# 稳定币基础币种黑名单（从 monitor market_settings.dynamic_scan.exclude_symbols 提取）
STABLE_BASES = {
    'USDT', 'USD1', 'USDS', 'USDC', 'DAI', 'TUSD', 'BUSD', 'FDUSD',
    'PAXG', 'USDP', 'GUSD', 'USDD', 'EUROC',
}


class MarketDataService:
    """带 TTL 缓存与 in-flight 去重的行情服务。

    :param exchange_provider: 异步工厂，返回 ccxt 交易所实例（共享实例）
    :param guardian: RestGuardian 实例（缺省新建）
    """

    def __init__(self, exchange_provider: Callable[[], Any], guardian: Optional[RestGuardian] = None,
                 ticker_ttl: float = 30.0, ohlcv_ttl: float = 30.0, funding_ttl: float = 60.0):
        self._exchange_provider = exchange_provider
        self.guardian = guardian or RestGuardian()
        self.ticker_ttl = max(1.0, float(ticker_ttl))
        self.ohlcv_ttl = max(1.0, float(ohlcv_ttl))
        self.funding_ttl = max(1.0, float(funding_ttl))
        self._tickers_cache: Optional[Tuple[float, Dict[str, Any]]] = None
        self._ohlcv_cache: Dict[Tuple[str, str], Tuple[float, list]] = {}
        self._ohlcv_inflight: Dict[Tuple[str, str], asyncio.Future] = {}
        self._funding_cache: Optional[Tuple[float, Dict[str, Any]]] = None

    async def _exchange(self):
        return await self._exchange_provider()

    # ------------------------------------------------------------------ tickers
    async def get_tickers(self, force: bool = False) -> Dict[str, Any]:
        """TTL 缓存的 fetch_tickers（默认 30s），一次请求拿全量。"""
        now = time.monotonic()
        if not force and self._tickers_cache and now - self._tickers_cache[0] < self.ticker_ttl:
            return self._tickers_cache[1]
        exchange = await self._exchange()
        tickers = await self.guardian.call(exchange.fetch_tickers, priority='NORMAL')
        self._tickers_cache = (time.monotonic(), tickers or {})
        return self._tickers_cache[1]

    # ------------------------------------------------------------------ ohlcv
    async def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 400) -> list:
        """按 (symbol, timeframe) 缓存的 K 线请求；同 key in-flight 去重（只发一次请求）。"""
        key = (symbol, timeframe)
        now = time.monotonic()
        cached = self._ohlcv_cache.get(key)
        if cached and now - cached[0] < self.ohlcv_ttl:
            return cached[1]

        fut = self._ohlcv_inflight.get(key)
        if fut is not None:
            # 已有相同 key 的请求在跑，等待它而不是重复发起
            return await asyncio.shield(fut)

        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._ohlcv_inflight[key] = fut
        try:
            exchange = await self._exchange()
            ohlcv = await self.guardian.call(
                exchange.fetch_ohlcv, symbol, timeframe, None, limit, priority='LOW')
            data = ohlcv or []
            fut.set_result(data)
            self._ohlcv_cache[key] = (time.monotonic(), data)
            return data
        except BaseException as exc:
            # CancelledError 属于 BaseException：必须把取消传给等待方，
            # 否则共享 Future 永远不会完成，所有 await shield(fut) 的协程会永久挂起。
            if not fut.done():
                fut.set_exception(exc if isinstance(exc, Exception) else asyncio.CancelledError())
            raise
        finally:
            self._ohlcv_inflight.pop(key, None)

    # ------------------------------------------------------------------ funding
    async def get_funding_rates(self, symbols: Sequence[str]) -> Dict[str, Any]:
        """批量 fetch_funding_rates，缓存 60s。失败时返回已缓存内容或空 dict。"""
        symbol_list = [str(s) for s in symbols or []]
        now = time.monotonic()
        if self._funding_cache and now - self._funding_cache[0] < self.funding_ttl:
            return self._funding_cache[1]
        if not symbol_list:
            return {}
        try:
            exchange = await self._exchange()
            rates = await self.guardian.call(
                exchange.fetch_funding_rates, symbol_list, priority='NORMAL')
            result = rates or {}
            self._funding_cache = (time.monotonic(), result)
            return result
        except Exception as e:
            print(f"--- [WARNING] 批量获取资金费率失败（跳过本轮费率策略）: {e} ---")
            return self._funding_cache[1] if self._funding_cache else {}

    # ------------------------------------------------------------------ TopN
    async def get_top_symbols_by_volume(self, top_n: int = 100,
                                        exclude: Optional[Sequence[str]] = None) -> List[str]:
        """基于 tickers 按成交额选 TopN 永续合约。

        - 只考虑 Binance USDⓈ-M 形态（BASE/QUOTE:QUOTE，QUOTE ∈ {USDC, USDT}）；
        - 同 base 的 USDC/USDT 合约去重：USDC 优先，其次 USDT；
        - 排除稳定币 base 与显式 exclude 名单（base 或 full_symbol 均可）。
        """
        exclude_set = {str(x).upper() for x in (exclude or [])}
        tickers = await self.get_tickers()

        by_base: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for full_symbol, ticker in (tickers or {}).items():
            if ':' not in full_symbol or '/' not in full_symbol:
                continue
            base = full_symbol.split('/')[0].upper()
            quote = full_symbol.split('/')[1].split(':')[0].upper()
            if quote not in ('USDC', 'USDT'):
                continue
            if base in STABLE_BASES or base in exclude_set or full_symbol.upper() in exclude_set:
                continue
            quote_volume = ticker.get('quoteVolume') or 0.0
            try:
                quote_volume = float(quote_volume)
            except (TypeError, ValueError):
                quote_volume = 0.0
            by_base.setdefault(base, {})[quote] = {
                'full_symbol': full_symbol, 'quote_volume': quote_volume}

        ranked: List[Tuple[str, str, float]] = []
        for base, quotes in by_base.items():
            # USDC 优先，其次 USDT
            chosen = quotes.get('USDC') or quotes.get('USDT')
            if chosen:
                ranked.append((base, chosen['full_symbol'], chosen['quote_volume']))

        ranked.sort(key=lambda item: item[2], reverse=True)
        return [full_symbol for _, full_symbol, _ in ranked[:max(0, int(top_n))]]

    def clear_caches(self) -> None:
        """清空全部缓存（测试或配置热更新用）。"""
        self._tickers_cache = None
        self._ohlcv_cache.clear()
        self._funding_cache = None
