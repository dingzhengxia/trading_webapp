"""Offline acceptance tests: USDC-first trading-pair resolution (report 3.3 / 4.1)."""
from __future__ import annotations

from app.logic.utils import extract_tradeable_coins, resolve_full_symbol


def _markets(*symbols: str) -> dict:
    return {symbol: {"symbol": symbol} for symbol in symbols}


def _use_markets(fake_exchange, *symbols: str) -> None:
    fake_exchange.markets = _markets(*symbols)


def test_prefers_usdc_when_both_usdc_and_usdt_exist(fake_exchange):
    _use_markets(fake_exchange, "BTC/USDC:USDC", "BTC/USDT:USDT")
    resolved = resolve_full_symbol(fake_exchange, "BTC")
    assert resolved == "BTC/USDC:USDC"
    assert "/USDC" in resolved


def test_prefers_simple_usdc_market_when_present(fake_exchange):
    _use_markets(fake_exchange, "ETH/USDC", "ETH/USDT", "ETH/USDC:USDC")
    resolved = resolve_full_symbol(fake_exchange, "ETH")
    assert resolved is not None
    assert "/USDC" in resolved


def test_falls_back_to_usdt_when_usdc_missing(fake_exchange):
    _use_markets(fake_exchange, "SOL/USDT:USDT", "SOL/USDT")
    assert resolve_full_symbol(fake_exchange, "SOL") in {"SOL/USDT", "SOL/USDT:USDT"}


def test_returns_none_when_no_preferred_quote_market(fake_exchange):
    _use_markets(fake_exchange, "DOGE/BTC", "DOGE/ETH", "NOTCOIN/USDT")
    assert resolve_full_symbol(fake_exchange, "DOGE") is None
    assert resolve_full_symbol(fake_exchange, "DOGEUSDT") is None


def test_symbol_input_is_case_insensitive(fake_exchange):
    _use_markets(fake_exchange, "ADA/USDC:USDC")
    assert resolve_full_symbol(fake_exchange, "ada") == "ADA/USDC:USDC"
    assert resolve_full_symbol(fake_exchange, "ADA") == "ADA/USDC:USDC"


def test_empty_markets_returns_none(fake_exchange):
    fake_exchange.markets = {}
    assert resolve_full_symbol(fake_exchange, "BTC") is None


# ---------------------------------------------------------------------------
# extract_tradeable_coins：手动交易页「全交易所币种」数据源
# ---------------------------------------------------------------------------
def _market(base, quote, *, swap=True, linear=True, active=None):
    market = {"base": base, "quote": quote, "swap": swap, "linear": linear}
    if active is not None:
        market["active"] = active
    return market


def test_extract_keeps_only_usdt_usdc_linear_swap():
    markets = {
        "BTC/USDC:USDC": _market("BTC", "USDC"),
        "ETH/USDT:USDT": _market("ETH", "USDT"),
        "BTC/USDT:USDT": _market("BTC", "USDT"),  # 与 USDC 版去重
        "SOL/BUSD": _market("SOL", "BUSD"),        # 非法报价币种
        "DOGE/BTC": _market("DOGE", "BTC"),        # 非稳定币对
        "SPOT/USDT": _market("SPOT", "USDT", swap=False),   # 现货
        "INV/USDT:USDT": _market("INV", "USDT", linear=False),  # 反向合约
        "DEL/USDT:USDT": _market("DEL", "USDT", active=False),  # 已下架
        " BAD /USDT:USDT": _market(" bad ", "USDT"),  # 大小写/空白归一化
    }
    assert extract_tradeable_coins(markets) == ["BAD", "BTC", "ETH"]


def test_extract_handles_empty_or_invalid_markets():
    assert extract_tradeable_coins(None) == []
    assert extract_tradeable_coins({}) == []
    assert extract_tradeable_coins({"X": "not-a-dict"}) == []
