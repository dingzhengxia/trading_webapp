from typing import Optional

import ccxt.async_support as ccxt

from ..config.config import STABLECOIN_PREFERENCE


def resolve_full_symbol(exchange: ccxt.binanceusdm, base_coin: str) -> Optional[str]:
    """
    一个独立的、可被任何模块安全导入的工具函数。
    """
    base_upper = base_coin.upper()
    quote_preferences = STABLECOIN_PREFERENCE

    for quote in quote_preferences:
        simple_symbol = f"{base_upper}/{quote}"
        if simple_symbol in exchange.markets:
            return exchange.markets[simple_symbol]['symbol']

        suffixed_symbol = f"{simple_symbol}:{quote}"
        if suffixed_symbol in exchange.markets:
            return exchange.markets[suffixed_symbol]['symbol']

    return None