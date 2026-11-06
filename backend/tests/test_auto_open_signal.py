"""信号自动开仓静态审计（MERGE_PLAN §8.7）：
auto_open_from_signal 复用 process_order_with_sl_tp_async —— fake exchange 断言
limit + postOnly、USDC 优先、无 'market' 开仓；与全局任务锁互斥。
"""
from __future__ import annotations

import asyncio
import contextlib
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import trading_service as trading_service_module  # noqa: E402
from app.core.trading_service import TradingService  # noqa: E402
from tests.conftest import FakeExchange, make_raw_position  # noqa: E402

USDC_SYMBOL = "BTC/USDC:USDC"


def _config():
    return {
        "leverage": 10,
        "signal_auto_trade_value_usd": 100.0,
        "open_order_fill_timeout_seconds": 5,
        "open_maker_retries": 0,
        "enable_long_sl_tp": True,
        "long_stop_loss_percentage": 10.0,
        "long_take_profit_percentage": 20.0,
        "enable_long_trailing_stop": False,
        "enable_short_sl_tp": False,
        "enable_short_trailing_stop": False,
    }


def _signal(direction="long"):
    return {"symbol": "BTC", "full_symbol": USDC_SYMBOL, "timeframe": "1h",
            "strategy": "ema_cross", "strategy_index": 0, "direction": direction,
            "price": 100.0, "title": "t", "message": "m", "dedupe_key": "k"}


@pytest.fixture
def patched_exchange(monkeypatch):
    """把 get_exchange_for_task 替换为 fake exchange 的上下文。"""
    exchange = FakeExchange()
    exchange.markets = {USDC_SYMBOL: {"symbol": USDC_SYMBOL,
                                      "limits": {"amount": {"min": 0.0001}}}}
    exchange._order_statuses = {"fake-1": {"status": "closed", "filled": 1.0}}
    exchange._positions = [
        make_raw_position(USDC_SYMBOL, "long", 1.0, entry_price=100.0,
                          mark_price=100.0, notional=100.0),
    ]

    @contextlib.asynccontextmanager
    async def fake_ctx():
        yield exchange

    monkeypatch.setattr(trading_service_module, "get_exchange_for_task", fake_ctx)
    return exchange


async def _drain_background_tasks():
    """等待 schedule_task 创建的后台任务全部结束（消除测试竞态）。"""
    current = asyncio.current_task()
    pending = [t for t in asyncio.all_tasks() if t is not current]
    if pending:
        await asyncio.gather(*pending)


def test_auto_open_uses_limit_postonly_usdc_first(patched_exchange, fast_sleep):
    service = TradingService()

    async def run():
        ok = await service.auto_open_from_signal(_signal(), _config())
        await _drain_background_tasks()
        return ok

    ok = asyncio.run(run())
    assert ok is True

    open_calls = [c for c in patched_exchange.create_order_calls if c["type"] == "limit"]
    assert len(open_calls) == 1
    call = open_calls[0]
    assert call["symbol"] == USDC_SYMBOL, "USDC 合约优先"
    assert call["side"] == "buy"
    assert call["params"].get("postOnly") is True, "开仓必须是 post-only 限价单"
    assert call["price"] == pytest.approx(100.0)

    # 无任何 'market' 类型开仓（STOP_MARKET/TAKE_PROFIT_MARKET 条件单除外）
    market_opens = [c for c in patched_exchange.create_order_calls
                    if c["type"] == "market"]
    assert market_opens == []

    # SL/TP 条件单挂在新开的 USDC 仓位上
    conditional = [c for c in patched_exchange.create_order_calls
                   if str(c["type"]).upper() in {"STOP_MARKET", "TAKE_PROFIT_MARKET"}]
    assert conditional
    assert {c["symbol"] for c in conditional} == {USDC_SYMBOL}


def test_auto_open_skips_when_task_running(patched_exchange):
    service = TradingService()
    service._is_running = True

    async def run():
        return await service.auto_open_from_signal(_signal(), _config())

    ok = asyncio.run(run())
    assert ok is False
    assert patched_exchange.create_order_calls == []


def test_schedule_task_mutual_exclusion():
    service = TradingService()
    service._is_running = True

    async def noop():
        pass

    async def run():
        # schedule_task 在 _is_running 时返回 None（不抛 HTTPException）
        return service.schedule_task("测试任务", noop())

    assert asyncio.run(run()) is None


def test_auto_open_short_direction(patched_exchange, fast_sleep):
    """short 信号 -> sell 限价 post-only。"""
    exchange = patched_exchange
    exchange._order_statuses = {"fake-1": {"status": "closed", "filled": 1.0}}
    exchange._positions = [
        make_raw_position(USDC_SYMBOL, "short", 1.0, entry_price=100.0,
                          mark_price=100.0, notional=100.0),
    ]
    service = TradingService()

    async def run():
        ok = await service.auto_open_from_signal(_signal(direction="short"), _config())
        await _drain_background_tasks()
        return ok

    assert asyncio.run(run()) is True
    open_calls = [c for c in exchange.create_order_calls if c["type"] == "limit"]
    assert open_calls[0]["side"] == "sell"
    assert open_calls[0]["params"].get("postOnly") is True
