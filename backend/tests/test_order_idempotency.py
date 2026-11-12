"""R-P0-1 下单幂等离线测试（fake exchange 全离线）。

验收要点（ARCH_REFACTOR_PHASE3 §7 T01）：
- fake 首次 create_order 抛 RequestTimeout 且订单已入簿 → 不重复下单、原单接管；
- 反查不到才允许下一轮重下（新 coid）；
- coid 格式合规（≤36、字符集）与唯一性断言。
"""
from __future__ import annotations

import asyncio
import re

import ccxt.async_support as ccxt
import pytest

from app.logic.exchange_logic_async import _execute_maker_order_with_retry_async
from app.logic.order_id import VALID_PREFIXES, make_client_order_id, order_client_id

SYMBOL = "BTC/USDC:USDC"
BINANCE_COID_RE = re.compile(r"^[.A-Za-z0-9_-]{1,36}$")


def _config(retries: int = 2) -> dict:
    return {"retries": retries}


# ------------------------------------------------------------------ coid 格式
def test_client_order_id_format_and_charset():
    for prefix in VALID_PREFIXES:
        coid = make_client_order_id(prefix, SYMBOL)
        assert len(coid) <= 36
        assert coid.startswith(prefix)
        assert BINANCE_COID_RE.match(coid), f"coid 不符合 Binance 合规集: {coid}"
        assert "BTC" in coid


def test_client_order_id_uniqueness():
    seen = {make_client_order_id('O', SYMBOL) for _ in range(200)}
    assert len(seen) == 200, "同刻生成的 coid 必须靠单调 seq 保证唯一"


def test_client_order_id_rejects_unknown_prefix():
    with pytest.raises(ValueError):
        make_client_order_id('X', SYMBOL)


# ------------------------------------------------------------------ 超时接管
def test_timeout_with_order_on_book_adopts_original_order(
    fake_exchange, async_logger, stop_event, fast_sleep,
):
    """create_order 抛 RequestTimeout 但订单已入簿 → 接管原单，不重下。"""
    state = {"raised": False, "fetches": 0}

    def _raise_after_booked(call):
        if not state["raised"]:
            state["raised"] = True
            raise ccxt.RequestTimeout("simulated timeout after order booked")

    fake_exchange.on_create_order = _raise_after_booked
    # 第一次 attempt 抛异常（订单已入簿）；接管后 fetch_order 第一次查到 open，第二次 closed
    fake_exchange._order_statuses = {"fake-1": [{"status": "open"}, {"status": "closed", "filled": 1.0}]}

    def _count_fetches(order_id, symbol=None, params=None):
        state["fetches"] += 1
        return None

    ok = asyncio.run(_execute_maker_order_with_retry_async(
        fake_exchange, SYMBOL, "buy", {}, 1, 2, async_logger, stop_event,
        value_to_trade=100.0,
    ))

    assert ok is True
    # 只下了 1 次单（原单被接管，没有重下）
    assert len(fake_exchange.create_order_calls) == 1
    first_params = fake_exchange.create_order_calls[0]["params"]
    assert first_params.get("newClientOrderId"), "开仓单必须带 newClientOrderId"
    assert first_params.get("postOnly") is True
    # 反查走了 open_orders 扫描（接管证据）
    assert fake_exchange.fetch_open_orders_calls, "接管路径必须先扫挂单簿反查"
    assert state["raised"], "expected simulated RequestTimeout to fire"


def test_timeout_without_order_on_book_retries_with_new_coid(
    fake_exchange, async_logger, stop_event, fast_sleep,
):
    """反查不到（请求根本没到达）→ 才允许下一轮重下，且新单用新 coid。"""
    state = {"raised": False}

    def _raise_immediately(call):
        if not state["raised"]:
            state["raised"] = True
            raise ccxt.RequestTimeout("request never reached the exchange")

    fake_exchange.on_create_order = _raise_immediately
    fake_exchange._order_statuses = {"fake-2": [{"status": "closed", "filled": 1.0}]}

    ok = asyncio.run(_execute_maker_order_with_retry_async(
        fake_exchange, SYMBOL, "buy", {}, 1, 1, async_logger, stop_event,
        value_to_trade=100.0,
    ))

    assert ok is True
    assert len(fake_exchange.create_order_calls) == 2, "反查不到时才允许重下"
    coids = [call["params"].get("newClientOrderId") for call in fake_exchange.create_order_calls]
    assert all(coids), "每轮 attempt 都必须带 newClientOrderId"
    assert len(set(coids)) == len(coids), "重下必须使用新 coid"


def test_close_orders_use_c_prefix(fake_exchange, async_logger, stop_event, fast_sleep):
    """reduceOnly 平仓路径的 coid 前缀为 C。"""
    fake_exchange._order_statuses = {"fake-1": [{"status": "closed", "filled": 1.0}]}

    ok = asyncio.run(_execute_maker_order_with_retry_async(
        fake_exchange, SYMBOL, "sell", {"reduceOnly": True}, 1, 0, async_logger, stop_event,
        contracts_to_trade=1.0,
    ))

    assert ok is True
    assert len(fake_exchange.create_order_calls) == 1
    coid = fake_exchange.create_order_calls[0]["params"]["newClientOrderId"]
    assert coid.startswith("C")


def test_recovery_via_fetch_order_when_not_in_open_orders(
    fake_exchange, async_logger, stop_event, fast_sleep,
):
    """挂单簿扫不到但按 origClientOrderId 查询命中（已成交历史单）→ 同样接管。"""
    state = {"raised": False}

    def _raise_after_booked(call):
        if not state["raised"]:
            state["raised"] = True
            raise ccxt.RequestTimeout("timeout")

    fake_exchange.on_create_order = _raise_after_booked
    fake_exchange._open_orders = []  # 挂单簿为空：走 fetch_order(origClientOrderId) 兜底
    fake_exchange._order_statuses = {"fake-1": [{"status": "closed", "filled": 1.0}]}

    ok = asyncio.run(_execute_maker_order_with_retry_async(
        fake_exchange, SYMBOL, "buy", {}, 1, 2, async_logger, stop_event,
        value_to_trade=100.0,
    ))

    assert ok is True
    assert len(fake_exchange.create_order_calls) == 1, "fetch_order 反查命中也必须接管，不重下"


def test_recover_order_by_client_id_returns_none_when_absent(fake_exchange):
    from app.logic.order_id import recover_order_by_client_id_async

    fake_exchange._open_orders = []
    result = asyncio.run(recover_order_by_client_id_async(
        fake_exchange, SYMBOL, "Odoes-not-exist"))
    assert result is None
