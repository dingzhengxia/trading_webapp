"""Shared fixtures for the offline acceptance test-suite.

Rules for this suite (see REFACTORING_REPORT.md sections 4/5):
- completely offline: no ccxt network calls, every exchange is a FakeExchange;
- no pytest-asyncio: async code is driven with asyncio.run;
- runnable with "python -m pytest backend/tests -q" from the repository root.
"""
from __future__ import annotations

import asyncio
import copy
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.schemas import Position  # noqa: E402


# ---------------------------------------------------------------------------
# Fake exchange
# ---------------------------------------------------------------------------
def _market_entry(symbol: str, min_amount: float = 0.001) -> dict:
    return {"symbol": symbol, "limits": {"amount": {"min": min_amount}}}


def default_markets() -> dict:
    """Minimal USD-M style markets used by fake exchange by default."""
    return {
        "BTC/USDC:USDC": _market_entry("BTC/USDC:USDC", 0.0001),
        "ETH/USDC:USDC": _market_entry("ETH/USDC:USDC", 0.0001),
        "SOL/USDC:USDC": _market_entry("SOL/USDC:USDC", 0.01),
        "XRP/USDC:USDC": _market_entry("XRP/USDC:USDC", 1.0),
        "BTC/USDT:USDT": _market_entry("BTC/USDT:USDT", 0.0001),
        "ETH/USDT:USDT": _market_entry("ETH/USDT:USDT", 0.0001),
        "ADA/USDT:USDT": _market_entry("ADA/USDT:USDT", 1.0),
        "DOT/USDT:USDT": _market_entry("DOT/USDT:USDT", 0.1),
    }


class FakeExchange:
    """Deterministic in-memory replacement for ccxt.binanceusdm.

    Every call that the production code may make is recorded so tests can
    assert on it.  Nothing here touches the network.
    """

    def __init__(
        self,
        markets: dict | None = None,
        order_book: dict | None = None,
        positions: list | object | None = None,
        order_statuses: dict | None = None,
        tickers: dict | None = None,
    ) -> None:
        self.markets = markets if markets is not None else default_markets()
        self._order_book = order_book if order_book is not None else {
            "bids": [[100.0, 10.0]], "asks": [[100.5, 10.0]]
        }
        self._positions = positions if positions is not None else []
        self._order_statuses = order_statuses or {}
        self._tickers = tickers or {}
        self._open_orders: list[dict] = []

        self.create_order_calls: list[dict] = []
        self.cancel_order_calls: list[tuple] = []
        self.cancel_all_orders_calls: list[tuple] = []
        self.fetch_order_calls: list[tuple] = []
        self.fetch_order_book_calls: list[tuple] = []
        self.fetch_positions_calls: list = []
        self.fetch_open_orders_calls: list = []
        self.fetch_tickers_calls: list = []
        self.set_leverage_calls: list[tuple] = []
        self.load_markets_calls = 0
        self.closed = False

        self.orders: dict[str, dict] = {}
        self._fetch_counts: dict[str, int] = {}
        self.on_create_order = None  # optional sync hook(call) for stateful tests

    # -- market metadata ---------------------------------------------------
    def market(self, symbol: str) -> dict:
        return self.markets.get(symbol) or _market_entry(symbol)

    def amount_to_precision(self, symbol: str, amount) -> str:
        return str(round(float(amount), 8))

    def price_to_precision(self, symbol: str, price) -> str:
        return str(round(float(price), 8))

    # -- lifecycle ---------------------------------------------------------
    async def load_markets(self) -> dict:
        self.load_markets_calls += 1
        return self.markets

    async def close(self) -> None:
        self.closed = True

    async def set_leverage(self, leverage, symbol=None):
        self.set_leverage_calls.append((symbol, leverage))
        return {"leverage": leverage, "symbol": symbol}

    # -- orders ------------------------------------------------------------
    async def fetch_order_book(self, symbol: str, limit: int = 5) -> dict:
        self.fetch_order_book_calls.append((symbol, limit))
        book = self._order_book(symbol) if callable(self._order_book) else self._order_book
        return copy.deepcopy(book)

    def _status_snapshot(self, order_id: str, fetch_index: int) -> dict:
        spec = self._order_statuses.get(order_id)
        if spec is None:
            return {}
        if callable(spec):
            return dict(spec(order_id, fetch_index) or {})
        if isinstance(spec, (list, tuple)):
            return dict(spec[min(fetch_index, len(spec) - 1)])
        return dict(spec)

    async def create_order(self, symbol, type=None, side=None, amount=None, price=None,
                           params=None, **kwargs):
        self.create_order_calls.append({
            "symbol": symbol,
            "type": type,
            "side": side,
            "amount": amount,
            "price": price,
            "params": dict(params or {}),
            "kwargs": dict(kwargs),
        })
        if callable(self.on_create_order):
            self.on_create_order(self.create_order_calls[-1])

        order_id = "fake-%d" % len(self.create_order_calls)
        snapshot = self._status_snapshot(order_id, 0)
        order = {
            "id": order_id,
            "symbol": symbol,
            "type": type,
            "side": side,
            "amount": float(amount) if amount is not None else None,
            "price": price,
            "params": dict(params or {}),
            "status": snapshot.get("status", "open"),
            "filled": float(snapshot.get("filled", 0.0)),
        }
        self.orders[order_id] = order
        return copy.deepcopy(order)

    async def fetch_order(self, order_id, symbol=None):
        self.fetch_order_calls.append((order_id, symbol))
        index = self._fetch_counts.get(order_id, 0)
        self._fetch_counts[order_id] = index + 1
        order = copy.deepcopy(self.orders.get(order_id, {"id": order_id, "symbol": symbol}))
        order.update(self._status_snapshot(order_id, index))
        return order

    async def cancel_order(self, order_id, symbol=None):
        self.cancel_order_calls.append((order_id, symbol))
        if order_id in self.orders:
            self.orders[order_id]["status"] = "canceled"
        return {"id": order_id, "status": "canceled"}

    async def cancel_all_orders(self, symbol=None, params=None):
        self.cancel_all_orders_calls.append((symbol, params))
        return []

    async def fetch_open_orders(self, symbol=None, since=None, limit=None, params=None):
        self.fetch_open_orders_calls.append((symbol, params))
        orders = self._open_orders
        if callable(orders):
            orders = orders(symbol)
        orders = list(orders or [])
        if symbol is not None:
            orders = [order for order in orders if order.get("symbol") == symbol]
        return copy.deepcopy(orders)

    # -- positions / tickers ----------------------------------------------
    async def fetch_positions(self, symbols=None):
        self.fetch_positions_calls.append(list(symbols) if symbols is not None else None)
        positions = self._positions
        if callable(positions):
            positions = positions(symbols)
        return copy.deepcopy(list(positions or []))

    async def fetch_tickers(self, symbols=None):
        self.fetch_tickers_calls.append(list(symbols) if symbols is not None else None)
        if callable(self._tickers):
            return copy.deepcopy(self._tickers(symbols))
        return copy.deepcopy(self._tickers)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_async_logger():
    """Return an async logger double that records (level, message) tuples."""

    async def _logger(message: str, level: str = "normal"):
        _logger.calls.append((level, message))

    _logger.calls = []  # type: ignore[attr-defined]
    return _logger


def make_position(
    symbol: str,
    full_symbol: str,
    side: str,
    contracts: float = 1.0,
    notional: float = 100.0,
    entry_price: float = 100.0,
    mark_price: float = 100.0,
) -> Position:
    """Build a Position model with sensible defaults for offline tests."""
    signed = contracts if side == "long" else -contracts
    return Position(
        symbol=symbol.upper(),
        full_symbol=full_symbol,
        side=side,
        contracts=abs(contracts),
        notional=notional,
        pnl=(mark_price - entry_price) * signed,
        pnl_percentage=0.0,
        entry_price=entry_price,
        mark_price=mark_price,
    )


def make_raw_position(
    symbol: str,
    side: str,
    contracts: float,
    entry_price: float = 100.0,
    mark_price: float = 100.0,
    notional: float = 100.0,
    initial_margin: float = 5.0,
) -> dict:
    """Build a ccxt-like raw position dict as returned by fetch_positions."""
    signed = contracts if str(side).lower() == "long" else -contracts
    return {
        "symbol": symbol,
        "side": side,
        "contracts": contracts,
        "contractSize": 1.0,
        "entryPrice": entry_price,
        "markPrice": mark_price,
        "notional": notional,
        "initialMargin": initial_margin,
        "info": {
            "symbol": symbol,
            "positionAmt": str(signed),
            "markPrice": str(mark_price),
            "breakEvenPrice": str(entry_price),
            "unRealizedProfit": str((mark_price - entry_price) * signed),
            "notional": str(notional),
            "initialMargin": str(initial_margin),
        },
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def fake_exchange() -> FakeExchange:
    return FakeExchange()


@pytest.fixture
def async_logger():
    return make_async_logger()


@pytest.fixture
def stop_event() -> asyncio.Event:
    return asyncio.Event()


@pytest.fixture
def position_factory():
    return make_position


@pytest.fixture
def raw_position_factory():
    return make_raw_position


@pytest.fixture
def fast_sleep(monkeypatch):
    """Make asyncio.sleep a no-op so retry/cleanup loops are fast."""

    async def _fast_sleep(_delay, *args, **kwargs):
        return None

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)
    yield
