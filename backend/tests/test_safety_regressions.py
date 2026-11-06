"""资金安全回归测试（2026-11-06 代码审计后的修复）。

覆盖点：
1. breakEvenPrice 返回 "0" 时入场价回退到 entryPrice（否则 SL/TP 会被静默跳过）；
2. 关闭止盈止损时不得撤销现有挂单（历史缺陷：一键同步会清空保护）；
3. 无持仓/数量为 0 时平仓返回 False（历史缺陷：返回 True 导致前端误删仓位）；
4. 配置数值校验与密钥掩码（服务端校验，防止绕过前端写入非法杠杆/止损）。
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.api.settings import MASK_MARK, _mask_secret, _validate_numeric_settings
from app.logic.exchange_logic_async import close_position_async, fetch_positions_with_pnl_async
from app.logic.sl_tp_logic_async import set_tp_sl_for_position_async


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- 入场价回退
def test_entry_price_falls_back_when_break_even_is_zero(fake_exchange, raw_position_factory):
    raw = raw_position_factory("BTC/USDC:USDC", "long", 1.0, entry_price=100.0)
    raw["info"]["breakEvenPrice"] = "0"  # Binance 实际会返回字符串 "0"
    fake_exchange._positions = [raw]

    positions = _run(fetch_positions_with_pnl_async(fake_exchange, 20))

    assert len(positions) == 1
    assert positions[0].entry_price == pytest.approx(100.0)


# ---------------------------------------------------------------- SL/TP 顺序
def test_disabled_sl_tp_does_not_cancel_existing_orders(
    fake_exchange, async_logger, stop_event, position_factory
):
    config = {"enable_long_sl_tp": False, "enable_long_trailing_stop": False, "leverage": 20}
    position = position_factory("BTC", "BTC/USDC:USDC", "long", contracts=1.0, entry_price=100.0)

    result = _run(set_tp_sl_for_position_async(fake_exchange, position, config, async_logger, stop_event))

    assert result is True
    # 关闭保护时不得触碰任何挂单，更不允许“先撤单再发现开关是关的”
    assert fake_exchange.cancel_all_orders_calls == []
    assert fake_exchange.create_order_calls == []


# ---------------------------------------------------------------- 平仓语义
def test_close_position_without_position_returns_false(fake_exchange, async_logger, stop_event):
    fake_exchange._positions = []

    result = _run(close_position_async(
        fake_exchange, "BTC/USDC:USDC", 1.0, async_logger, stop_event))

    # False 才会阻止上层广播 position_closed / 反向开仓
    assert result is False
    assert fake_exchange.create_order_calls == []


# ---------------------------------------------------------------- 配置校验
@pytest.mark.parametrize("bad_value", [0, -5, 126, "abc", "", None, True])
def test_leverage_validation_rejects_invalid_values(bad_value):
    with pytest.raises(HTTPException) as exc_info:
        _validate_numeric_settings({"leverage": bad_value})
    assert exc_info.value.status_code == 400


def test_leverage_validation_accepts_valid_value():
    payload = {"leverage": "20"}
    _validate_numeric_settings(payload)
    assert payload["leverage"] == 20
    assert isinstance(payload["leverage"], int)


@pytest.mark.parametrize("bad_value", [-1, 1200])
def test_stop_loss_percentage_range(bad_value):
    with pytest.raises(HTTPException):
        _validate_numeric_settings({"long_stop_loss_percentage": bad_value})


def test_secret_masking_keeps_prefix_and_suffix():
    masked = _mask_secret("ABCDEFGHIJKLMNOP")
    assert masked.startswith("ABCD") and masked.endswith("MNOP")
    assert MASK_MARK in masked
    assert _mask_secret("") == ""
    assert _mask_secret("short") == MASK_MARK
