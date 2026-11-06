# backend/app/logic/utils.py
from typing import List, Optional, Tuple

import ccxt.async_support as ccxt

from ..config.config import STABLECOIN_PREFERENCE


def _market_to_symbol(market: object, fallback: str) -> str:
    """兼容 ccxt 市场对象与测试中使用的简化 dict。"""
    if isinstance(market, dict):
        symbol = market.get('symbol')
        if symbol:
            return str(symbol)
    return fallback


def resolve_symbol_details(exchange: ccxt.binanceusdm, base_coin: str) -> Tuple[Optional[str], Optional[str]]:
    """解析基础币种对应的最终交易对与报价币种。

    按 STABLECOIN_PREFERENCE（USDC 优先，其次 USDT）依次尝试
    BASE/QUOTE 与 BASE/QUOTE:QUOTE，返回 (full_symbol, quote)；
    都不存在时返回 (None, None)。
    """
    if not base_coin or not isinstance(base_coin, str):
        return None, None

    base_upper = base_coin.strip().upper()
    if not base_upper:
        return None, None
    # 允许调用方误传完整交易对（例如 BTC/USDT:USDT）时自动降级为基础币种
    if '/' in base_upper:
        base_upper = base_upper.split('/')[0].strip()
    if not base_upper:
        return None, None

    markets = getattr(exchange, 'markets', None) or {}
    for quote in STABLECOIN_PREFERENCE:
        for candidate in (f"{base_upper}/{quote}", f"{base_upper}/{quote}:{quote}"):
            if candidate in markets:
                return _market_to_symbol(markets[candidate], candidate), quote
    return None, None


def resolve_full_symbol(exchange: ccxt.binanceusdm, base_coin: str) -> Optional[str]:
    """返回基础币种对应的最终交易对（USDC 优先，其次 USDT），不存在时返回 None。"""
    full_symbol, _ = resolve_symbol_details(exchange, base_coin)
    return full_symbol


def extract_tradeable_coins(markets: Optional[dict]) -> List[str]:
    """从 ccxt markets 中提取全部可交易的 USDⓈ-M 永续基础币种（去重排序）。

    只保留 USDT/USDC 报价的线性永续（swap + linear）且未下架的合约；
    供手动交易页把可选币种扩展到「币种池 + 全交易所」。
    """
    coins = set()
    for market in (markets or {}).values():
        if not isinstance(market, dict):
            continue
        if not (market.get('swap') and market.get('linear')):
            continue
        if market.get('active') is False:
            continue
        if str(market.get('quote') or '').upper() not in ('USDT', 'USDC'):
            continue
        base = str(market.get('base') or '').strip().upper()
        if base:
            coins.add(base)
    return sorted(coins)
