"""交易所保护 STOP 的事实核对与补挂（离线）。

背景（2026-11-15 用户反馈）：在币安 App 里手动撤掉守护引擎挂的 STOP 之后，
引擎从不补挂，止损上移也照旧拿账本里的旧价比较——等于仓位在交易所侧裸奔。
根因：v2 决策只读账本 state['stop']（=「我们上次挂了什么」），从不核对交易所。
修复：每 stop_verify_interval_sec 秒查一次真实挂单，缺失即补挂、改价即纠正账本。
"""
from __future__ import annotations

import asyncio

import pytest

from app.protection import runner


def _conf(**over):
    conf = {'exchange_hard_stop_enabled': True, 'stop_verify_interval_sec': 15.0}
    conf.update(over)
    return conf


@pytest.fixture(autouse=True)
def _clear_cache():
    runner.LAST_STOP_VERIFY.clear()
    yield
    runner.LAST_STOP_VERIFY.clear()


def _patch_orders(monkeypatch, orders):
    """让 _find_stop_orders 返回给定挂单，并记录调用次数。"""
    calls = []

    async def fake_find(exchange, symbol, side, pos, price, conf, force=False):
        calls.append(symbol)
        return list(orders)

    monkeypatch.setattr(runner.engine, '_find_stop_orders', fake_find)
    return calls


def test_disabled_hard_stop_skips_lookup(monkeypatch):
    """关掉「交易所灾难止损单」就不该查、更不该补挂。"""
    calls = _patch_orders(monkeypatch, [])
    result = asyncio.run(runner._exchange_stop_price(
        None, _conf(exchange_hard_stop_enabled=False), 'ETH/USDC', 'long', {}, 100.0, 1000.0))
    assert result is None
    assert calls == []


def test_missing_stop_returns_zero(monkeypatch):
    """交易所没有我们的 STOP → 返回 0.0（决策据此补挂），与「本轮没查」(None) 区分开。"""
    _patch_orders(monkeypatch, [])
    result = asyncio.run(runner._exchange_stop_price(
        None, _conf(), 'ETH/USDC', 'long', {}, 100.0, 1000.0))
    assert result == 0.0


def test_reads_trigger_price_from_exchange(monkeypatch):
    _patch_orders(monkeypatch, [{'triggerPrice': '1889.5'}])
    result = asyncio.run(runner._exchange_stop_price(
        None, _conf(), 'ETH/USDC', 'long', {}, 1900.0, 1000.0))
    assert result == pytest.approx(1889.5)


def test_throttled_within_interval(monkeypatch):
    """节流窗口内不再打交易所：返回 None（决策退回账本口径）。"""
    calls = _patch_orders(monkeypatch, [{'triggerPrice': '1889.5'}])
    first = asyncio.run(runner._exchange_stop_price(
        None, _conf(), 'ETH/USDC', 'long', {}, 1900.0, 1000.0))
    second = asyncio.run(runner._exchange_stop_price(
        None, _conf(), 'ETH/USDC', 'long', {}, 1900.0, 1005.0))
    assert first == pytest.approx(1889.5)
    assert second is None
    assert len(calls) == 1
    third = asyncio.run(runner._exchange_stop_price(
        None, _conf(), 'ETH/USDC', 'long', {}, 1900.0, 1020.0))
    assert third == pytest.approx(1889.5)
    assert len(calls) == 2


def test_lookup_failure_falls_back_to_ledger(monkeypatch):
    """查询异常不能让整轮守护挂掉：返回 None，决策继续用账本口径。"""
    async def boom(*args, **kwargs):
        raise RuntimeError('boom')

    monkeypatch.setattr(runner.engine, '_find_stop_orders', boom)
    result = asyncio.run(runner._exchange_stop_price(
        None, _conf(), 'ETH/USDC', 'long', {}, 1900.0, 1000.0))
    assert result is None
