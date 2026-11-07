"""Phase 3 离线测试：仓位保护引擎（配置合并 / TP 阶梯 / 灾难止损 / 状态持久化 / 静态审计）。

全部离线：不访问交易所，不读写真实 data/app.db。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.core import database
from app.protection import engine

SYMBOL = "BTC/USDC:USDC"


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """把 DB 路径指向临时目录（protection_state 表也在其中创建）。"""
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "USER_SETTINGS_FILE", tmp_path / "user_settings.json")
    monkeypatch.setattr(database, "COIN_LISTS_FILE", tmp_path / "coin_lists.json")
    database.init_db()
    return tmp_path


# ---------------------------------------------------------------------------
# 配置：默认值 + SQLite 覆盖深合并
# ---------------------------------------------------------------------------
def test_default_config_covers_all_risk_switches():
    conf = engine.DEFAULT_CONFIG["position_protection"]
    for key in ("enabled", "timeframe", "tp1_r_multiple", "tp2_r_multiple", "tp3_r_multiple",
                "t1_structure_lookback", "t2_structure_lookback", "t3_structure_lookback",
                "emergency_enabled", "exchange_hard_stop_enabled", "profit_protection_enabled"):
        assert key in conf, f"缺少风控配置项: {key}"
    assert conf["timeframe"] == "2h"


def test_load_config_merges_sqlite_override(monkeypatch):
    monkeypatch.setattr(engine, "load_settings",
                        lambda: {"position_protection": {"enabled": True, "tp1_r_multiple": 1.5}})
    conf = engine._load_config()["position_protection"]
    assert conf["enabled"] is True
    assert conf["tp1_r_multiple"] == 1.5
    # 未覆盖的字段仍使用默认值
    assert conf["tp2_r_multiple"] == engine.DEFAULT_CONFIG["position_protection"]["tp2_r_multiple"]
    assert conf["timeframe"] == "2h"


def test_load_config_falls_back_to_defaults_on_error(monkeypatch):
    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(engine, "load_settings", _boom)
    conf = engine._load_config()["position_protection"]
    assert conf["timeframe"] == "2h"
    assert conf["enabled"] == engine.DEFAULT_CONFIG["position_protection"]["enabled"]


def test_deep_merge_is_recursive():
    merged = engine._deep_merge_defaults({"a": {"b": 1, "c": 2}}, {"a": {"c": 3}})
    assert merged == {"a": {"b": 1, "c": 3}}


# ---------------------------------------------------------------------------
# 止盈阶梯：固定 R，按方向单调
# ---------------------------------------------------------------------------
def test_initialize_take_profit_levels_long():
    state = {}
    ok = engine._initialize_take_profit_levels(
        state, "long", entry_price=100.0, strategy_stop=96.0, conf={"take_profit_enabled": True})
    assert ok is True
    assert state["tp_risk_distance"] == pytest.approx(4.0)
    assert state["tp1_price"] == pytest.approx(104.0)
    assert state["tp2_price"] == pytest.approx(108.0)
    assert state["tp3_price"] == pytest.approx(112.0)


def test_initialize_take_profit_levels_short():
    state = {}
    ok = engine._initialize_take_profit_levels(
        state, "short", entry_price=100.0, strategy_stop=104.0, conf={"take_profit_enabled": True})
    assert ok is True
    assert state["tp1_price"] == pytest.approx(96.0)
    assert state["tp2_price"] == pytest.approx(92.0)
    assert state["tp3_price"] == pytest.approx(88.0)


def test_initialize_take_profit_rejects_wrong_side_stop():
    """止损在盈利方向（多单止损高于开仓价）时必须拒绝初始化，避免出现负风险。"""
    state = {}
    assert engine._initialize_take_profit_levels(
        state, "long", entry_price=100.0, strategy_stop=101.0,
        conf={"take_profit_enabled": True}) is False
    assert state == {}


def test_initialize_take_profit_disabled():
    state = {}
    assert engine._initialize_take_profit_levels(
        state, "long", entry_price=100.0, strategy_stop=96.0,
        conf={"take_profit_enabled": False}) is False


def test_initialize_take_profit_rejects_bad_r_multiples():
    with pytest.raises(ValueError):
        engine._initialize_take_profit_levels(
            {}, "long", entry_price=100.0, strategy_stop=96.0,
            conf={"take_profit_enabled": True, "tp1_r_multiple": 2.0,
                  "tp2_r_multiple": 1.0, "tp3_r_multiple": 3.0})


def test_take_profit_hit_levels_for_long():
    state = {}
    engine._initialize_take_profit_levels(
        state, "long", entry_price=100.0, strategy_stop=96.0, conf={"take_profit_enabled": True})
    assert engine._take_profit_hit(state, "long", 103.9) == 0
    assert engine._take_profit_hit(state, "long", 104.0) == 1
    assert engine._take_profit_hit(state, "long", 108.0) == 2
    assert engine._take_profit_hit(state, "long", 112.0) == 3


def test_take_profit_hit_levels_for_short():
    state = {}
    engine._initialize_take_profit_levels(
        state, "short", entry_price=100.0, strategy_stop=104.0, conf={"take_profit_enabled": True})
    assert engine._take_profit_hit(state, "short", 96.5) == 0
    assert engine._take_profit_hit(state, "short", 96.0) == 1
    assert engine._take_profit_hit(state, "short", 92.0) == 2
    assert engine._take_profit_hit(state, "short", 88.0) == 3


def test_take_profit_hit_rejects_dirty_state():
    """脏状态（TP 跑到开仓价错误一侧）绝不能触发平仓。"""
    dirty = {
        "tp_risk_distance": 4.0,
        "tp_entry_price": 100.0,
        "tp1_price": 104.0,
        "tp2_price": 108.0,
        "tp3_price": 88.0,  # 多单的躺平价低于开仓价 → 非法
    }
    assert engine._take_profit_hit(dirty, "long", 120.0) == 0


def test_take_profit_hit_requires_initialized_state():
    assert engine._take_profit_hit({}, "long", 200.0) == 0


# ---------------------------------------------------------------------------
# 灾难止损：按 ATR 与最小距离取较大者
# ---------------------------------------------------------------------------
def test_calculate_disaster_stop_uses_atr_distance(fake_exchange):
    stop, distance = engine._calculate_disaster_stop(
        fake_exchange, SYMBOL, "long", 100.0, atr_value=2.0,
        conf={"hard_stop_min_distance_pct": 0.05, "hard_stop_atr_multiplier": 6.0})
    assert distance == pytest.approx(0.12)  # 2*6/100 = 12% > 5%
    assert stop == pytest.approx(88.0)


def test_calculate_disaster_stop_respects_min_distance(fake_exchange):
    stop, distance = engine._calculate_disaster_stop(
        fake_exchange, SYMBOL, "short", 100.0, atr_value=0.1,
        conf={"hard_stop_min_distance_pct": 0.05, "hard_stop_atr_multiplier": 6.0})
    assert distance == pytest.approx(0.05)
    assert stop == pytest.approx(105.0)


# ---------------------------------------------------------------------------
# 状态持久化：SQLite protection_state 表
# ---------------------------------------------------------------------------
def test_state_roundtrip_uses_sqlite(tmp_db):
    state = {"BTC/USDC:USDC_long": {"tp1_price": 104.0, "tp1_triggered": False}}
    assert engine._save_state(state) is True
    assert engine._load_state() == state
    assert database.get_value("protection_state", "state") == state


def test_load_state_returns_empty_when_missing(tmp_db):
    assert engine._load_state() == {}


# ---------------------------------------------------------------------------
# 静态审计：仓位保护只做「平仓/保护」，永远不会开仓
# ---------------------------------------------------------------------------
def test_protection_engine_never_calls_create_order():
    path = Path(engine.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"create_order", "createOrder"}:
                offenders.append(node.lineno)
    assert not offenders, f"仓位保护引擎不得包含开仓调用: {path}:{offenders}"


def test_protection_engine_has_no_plain_market_entry():
    """所有市价调用必须是 reduceOnly 减仓/止损，且不用于开仓。"""
    source = Path(engine.__file__).read_text(encoding="utf-8")
    # 市价只允许出现在 create_market_order 的减仓函数里
    assert source.count("create_market_order") == 1


# ---------------------------------------------------------------------------
# 条件单兼容层：旧版 ccxt 退回标准 STOP_MARKET（closePosition=True）
# ---------------------------------------------------------------------------
class _FakeRest:
    """直接执行调用，不走限流（测试专用）。"""

    async def call(self, func, *args, priority="NORMAL", conf=None, **kwargs):
        return await func(*args, **kwargs)


def test_algo_compat_detects_missing_algo_api(fake_exchange):
    from app.protection import algo_compat
    assert algo_compat.supports_algo(fake_exchange) is False


def test_algo_compat_creates_close_position_stop(fake_exchange):
    import asyncio
    from app.protection import algo_compat

    order = asyncio.run(algo_compat.create_close_position_stop(
        fake_exchange, SYMBOL, "long", "BOTH", 95000.0, "PM_WS_SL_TEST", {}, _FakeRest()))

    assert order["type"] == "STOP_MARKET"
    call = fake_exchange.create_order_calls[-1]
    assert call["type"] == "STOP_MARKET"
    assert call["side"] == "sell"  # 多单用卖出止损
    assert call["amount"] is None  # closePosition 模式不指定数量
    assert call["params"]["closePosition"] is True
    assert call["params"]["stopPrice"] == "95000.0"
    assert call["params"]["newClientOrderId"] == "PM_WS_SL_TEST"


def test_algo_compat_fetches_and_normalizes_legacy_orders(fake_exchange):
    import asyncio
    from app.protection import algo_compat

    fake_exchange._open_orders = [{
        "id": "123", "clientOrderId": "PM_WS_SL_BTCUSDCUSDC_L_abc",
        "symbol": SYMBOL, "type": "STOP_MARKET", "side": "sell",
        "status": "open", "stopPrice": 95000.0,
    }]
    orders = asyncio.run(algo_compat.fetch_open_algo_orders(fake_exchange, SYMBOL, {}, _FakeRest()))
    assert fake_exchange.fetch_open_orders_calls[-1][1] == {"stop": True}
    assert orders[0]["algoId"] == "123"
    assert orders[0]["orderType"] == "STOP_MARKET"
    assert orders[0]["side"] == "SELL"


def test_algo_compat_cancels_legacy_order(fake_exchange):
    import asyncio
    from app.protection import algo_compat

    asyncio.run(algo_compat.cancel_algo_order(fake_exchange, SYMBOL, "123", {}, _FakeRest()))
    assert fake_exchange.cancel_order_calls[-1] == ("123", SYMBOL)


# ---------------------------------------------------------------------------
# monitor 引擎日志转发到 UI 日志抽屉（ui_log_sink）
# ---------------------------------------------------------------------------
# 说明：loguru 的过滤器按「调用日志的模块名」判定，测试文件里的 logger.info
# 调用点不在 app.signals/app.protection 命名空间下，因此这里直接构造
# loguru 记录对象驱动 _forward，验证转发路径与过滤规则本身。
def test_ui_log_sink_forwards_engine_logs():
    import asyncio
    from types import SimpleNamespace

    from app.core.ui_log_sink import _forward, install_ui_log_sink
    from app.core.websocket_manager import LOG_HISTORY

    install_ui_log_sink()

    def make_record(name, text, level="INFO"):
        return SimpleNamespace(
            record={"name": name, "message": text, "level": SimpleNamespace(name=level)}
        )

    async def scenario():
        before = len(LOG_HISTORY)
        _forward(make_record("app.signals.scanner", "信号扫描循环已启动，间隔 60 秒。"))
        await asyncio.sleep(0.05)  # _forward 内部 create_task，让出一轮让任务执行
        return before

    before = asyncio.run(scenario())
    entries = list(LOG_HISTORY)[before:]
    assert entries, "引擎日志未转发到 UI"
    payload = entries[-1]["payload"]
    assert "📡 [信号]" in payload["message"]
    assert "间隔 60 秒" in payload["message"]
    assert payload["level"] == "info"


def test_ui_log_sink_skips_other_modules_and_duplicates():
    import asyncio
    from types import SimpleNamespace

    from app.core.ui_log_sink import _forward, install_ui_log_sink
    from app.core.websocket_manager import LOG_HISTORY

    install_ui_log_sink()

    def make_record(name, text, level="INFO"):
        return SimpleNamespace(
            record={"name": name, "message": text, "level": SimpleNamespace(name=level)}
        )

    async def scenario():
        before = len(LOG_HISTORY)
        _forward(make_record("app.core.trading_service", "普通日志不转发"))
        _forward(make_record("app.protection.engine", "[BTC] 🛡️ [仓位保护] 已由 notifier 推送"))
        _forward(make_record("app.signals.scanner", "DEBUG 级别跳过", level="DEBUG"))
        await asyncio.sleep(0.05)
        return before

    before = asyncio.run(scenario())
    new_texts = [e["payload"]["message"] for e in list(LOG_HISTORY)[before:]]
    assert not new_texts, f"不应有新转发: {new_texts}"


def test_ui_log_sink_install_is_idempotent():
    from loguru import logger

    from app.core.ui_log_sink import install_ui_log_sink

    install_ui_log_sink()
    sinks_before = len(logger._core.handlers)
    install_ui_log_sink()
    install_ui_log_sink()
    assert len(logger._core.handlers) == sinks_before  # 重复安装不新增 sink
