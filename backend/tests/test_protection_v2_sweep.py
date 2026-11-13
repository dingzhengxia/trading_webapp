"""v2 幽灵行对账 + 连续移动止损防抖（离线测试）。

修复背景：_sweep_lifecycle 旧版依赖进程内存 previous_active 对账，
引擎重启后内存集合丢失，平仓后的账本行永久残留（前端守护列表越积越多）。
"""
import asyncio

import pytest

from app.core import database
from app.protection import ledger, risk_model, runner


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "USER_SETTINGS_FILE", tmp_path / "user_settings.json")
    monkeypatch.setattr(database, "COIN_LISTS_FILE", tmp_path / "coin_lists.json")
    database.init_db()
    return tmp_path


@pytest.fixture
def clean_v2():
    """v2 全局运行时状态隔离（V2 是模块级单例）。"""
    runner.V2.disappeared_since.clear()
    runner.V2.active.clear()
    runner.V2.recent_actions.clear()
    yield
    runner.V2.disappeared_since.clear()
    runner.V2.active.clear()


@pytest.fixture
def no_cleanup_orders(monkeypatch):
    """清理旧挂单动作替换为 no-op（对账测试不触交易所）。"""

    async def _noop(*args, **kwargs):
        return 0

    monkeypatch.setattr(runner.engine, "_cancel_program_stops_for_flat", _noop)
    monkeypatch.setattr(runner.engine, "_cancel_bot_reduce_orders", _noop)


CONF = dict(risk_model.V2_DEFAULTS)
CONF["flat_confirm_sec"] = 0  # 测试不做确认期缓冲


# ---------------------------------------------------------------------------
# 账本对账：幽灵行清理（重启后也生效）
# ---------------------------------------------------------------------------
def test_sweep_deletes_ghost_rows(tmp_db, clean_v2, no_cleanup_orders):
    """账本里有、本轮真实持仓里没有 → 直接删除（不依赖 previous_active）。"""
    ledger.save("GHOST/USDC:USDC", "long", {"contracts": 5.0})
    ledger.save("ALIVE/USDC:USDC", "long", {"contracts": 3.0})
    active = {("ALIVE/USDC:USDC", "long")}

    asyncio.run(runner._sweep_lifecycle(object(), CONF, active))

    assert ledger.load("GHOST/USDC:USDC", "long") is None
    assert ledger.load("ALIVE/USDC:USDC", "long") is not None


def test_sweep_clears_stale_rows_simulating_restart(tmp_db, clean_v2, no_cleanup_orders):
    """模拟引擎重启：V2.active/disappeared_since 已被清空，账本残留旧仓行。"""
    for symbol in ("OLD1/USDC:USDC", "OLD2/USDC:USDC", "OLD3/USDC:USDC"):
        ledger.save(symbol, "long", {"contracts": 1.0})

    # 重启后第一轮：没有任何真实持仓（全平了）
    asyncio.run(runner._sweep_lifecycle(object(), CONF, set()))

    assert ledger.all_positions() == {}


def test_sweep_keeps_live_positions(tmp_db, clean_v2, no_cleanup_orders):
    """真实持仓的账本行绝不能被对账误删。"""
    ledger.save("BTC/USDC:USDC", "long", {"contracts": 0.003})
    ledger.save("ETH/USDC:USDC", "short", {"contracts": 2.0})
    active = {("BTC/USDC:USDC", "long"), ("ETH/USDC:USDC", "short")}

    asyncio.run(runner._sweep_lifecycle(object(), CONF, active))

    assert ledger.load("BTC/USDC:USDC", "long") is not None
    assert ledger.load("ETH/USDC:USDC", "short") is not None


def test_status_filters_zero_contract_rows(tmp_db):
    """status() 兜底过滤 contracts<=0 的幽灵行。"""
    ledger.save("GHOST/USDC:USDC", "long", {"contracts": 0, "plan": {"entry": 1.0}})
    ledger.save("ALIVE/USDC:USDC", "long", {
        "contracts": 1.5, "plan": {"entry": 100.0, "risk": 3.0,
                                   "levels": [95.0, 94.0, 93.0, 92.0],
                                   "tp_prices": [103.0, 106.0, 109.0]},
        "last_price": 101.0, "stop": 96.0})

    rows = runner.status()["positions"]
    symbols = [r["symbol"] for r in rows]
    assert "GHOST/USDC:USDC" not in symbols
    assert "ALIVE/USDC:USDC" in symbols


# ---------------------------------------------------------------------------
# v2 连续移动止损：触发 / 防抖 / 模式开关
# ---------------------------------------------------------------------------
def _trail_snap(price=110.0):
    return risk_model.Snapshot(
        symbol="BTC/USDC:USDC", side="long", entry=100.0, price=price,
        last_close=price, contracts=10.0, base_contracts=10.0,
        atr=2.0, structure=(97.0, 95.0, 92.0), closed_ts=0, now=1000.0,
    )


def _trail_state(stop=None):
    state = {"plan": {"entry": 100.0, "risk": 5.0}}
    if stop is not None:
        state["stop"] = stop
    return state


def _trail_conf(**overrides):
    conf = dict(risk_model.V2_DEFAULTS)
    conf.update({
        "trailing_stop_mode": "continuous",
        "trailing_trigger_r": 1.0,
        "trailing_atr_multiple": 2.0,
    })
    conf.update(overrides)
    return conf


def test_v2_trailing_disabled_in_step_mode():
    """默认 step 模式不追踪（阶梯保护照旧）。"""
    assert runner._v2_trailing_stop(_trail_state(), "long", _trail_snap(), 2.0,
                                    dict(risk_model.V2_DEFAULTS)) is None


def test_v2_trailing_first_stop_uses_trail_line():
    """账本还没有 STOP：首个兜底单直接用追踪线（110 - 2×2 = 106）。"""
    result = runner._v2_trailing_stop(_trail_state(stop=None), "long",
                                      _trail_snap(), 2.0, _trail_conf())
    assert result == 106.0


def test_v2_trailing_debounce_blocks_small_move():
    """追踪线相对已挂 STOP 推进不足 min_move 时不更新（防撤单重挂刷请求）。"""
    # trail=106，已挂 105.98 → 推进 0.02 < min_move（max(110*0.0005, 2*0.05)=0.1）
    result = runner._v2_trailing_stop(_trail_state(stop=105.98), "long",
                                      _trail_snap(), 2.0, _trail_conf())
    assert result is None


def test_v2_trailing_passes_material_move():
    """有效推进（价格回撤后重新上移）→ 返回新追踪线。"""
    # 已挂 100 → trail 106，推进 6 >= 0.1
    result = runner._v2_trailing_stop(_trail_state(stop=100.0), "long",
                                      _trail_snap(), 2.0, _trail_conf())
    assert result == 106.0


def test_v2_trailing_never_widens_short_stop():
    """空单：追踪线只许下移；价格回撤导致 trail 劣于已挂 STOP 时不更新。"""
    snap = risk_model.Snapshot(
        symbol="BTC/USDC:USDC", side="short", entry=100.0, price=90.0,
        last_close=90.0, contracts=10.0, base_contracts=10.0,
        atr=2.0, structure=(103.0, 105.0, 108.0), closed_ts=0, now=1000.0,
    )
    state = {"plan": {"entry": 100.0, "risk": 5.0}, "stop": 93.0}
    # trail = 90 + 4 = 94 > 已挂 93（恶化方向）→ 不更新
    assert runner._v2_trailing_stop(state, "short", snap, 2.0, _trail_conf()) is None
