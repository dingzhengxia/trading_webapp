"""连续移动止损（#5）与双轨接管（#4）离线测试。

覆盖：
- _continuous_trailing_stop 纯计算：模式开关、触发阈值、多空方向、盈利侧约束；
- _is_external_conditional_order 前缀识别：SL/TP/TS 命中、守护端 PM_WS_ 前缀不误伤；
- _take_over_external_stops：守护端 STOP 未就位时跳过；就位后只撤外部条件单。
"""
import asyncio

from app.protection import exits as exits_mod
from app.protection.stops import _continuous_trailing_stop


# ---------------------------------------------------------------------------
# _continuous_trailing_stop 纯计算
# ---------------------------------------------------------------------------
def _trail_conf(**overrides):
    conf = {
        "trailing_stop_mode": "continuous",
        "trailing_trigger_r": 1.0,
        "trailing_atr_multiple": 2.0,
    }
    conf.update(overrides)
    return conf


def _long_state(entry=100.0, risk=5.0):
    return {"tp_entry_price": entry, "tp_risk_distance": risk}


def test_trailing_disabled_in_step_mode():
    """默认 step 模式（阶梯）不启用连续追踪。"""
    stop, floating_r = _continuous_trailing_stop(
        _long_state(), "long", 110.0, 2.0, _trail_conf(trailing_stop_mode="step"))
    assert stop is None
    assert floating_r == 0.0


def test_trailing_requires_entry_and_risk():
    """缺少 tp_entry_price / tp_risk_distance 时不追踪（安全放弃）。"""
    stop, _ = _continuous_trailing_stop({}, "long", 110.0, 2.0, _trail_conf())
    assert stop is None
    stop, _ = _continuous_trailing_stop(_long_state(risk=0), "long", 110.0, 2.0, _trail_conf())
    assert stop is None


def test_trailing_requires_atr_and_price():
    """ATR/价格非法时不追踪。"""
    stop, _ = _continuous_trailing_stop(_long_state(), "long", 110.0, 0.0, _trail_conf())
    assert stop is None
    stop, _ = _continuous_trailing_stop(_long_state(), "long", 0.0, 2.0, _trail_conf())
    assert stop is None


def test_trailing_below_trigger_not_active():
    """浮盈未达 trailing_trigger_r 不追踪，但返回浮盈 R 供日志使用。"""
    stop, floating_r = _continuous_trailing_stop(
        _long_state(), "long", 103.0, 2.0, _trail_conf())
    assert stop is None
    assert floating_r == (103.0 - 100.0) / 5.0


def test_trailing_long_tracks_above_trigger():
    """多单：浮盈 2R 达标，追踪线 = price - mult*ATR。"""
    stop, floating_r = _continuous_trailing_stop(
        _long_state(), "long", 110.0, 2.0, _trail_conf())
    assert floating_r == 2.0
    assert stop == 110.0 - 2.0 * 2.0  # 106


def test_trailing_short_tracks_above_trigger():
    """空单：浮盈 2R 达标，追踪线 = price + mult*ATR。"""
    stop, floating_r = _continuous_trailing_stop(
        _long_state(), "short", 90.0, 2.0, _trail_conf())
    assert floating_r == (100.0 - 90.0) / 5.0
    assert stop == 90.0 + 2.0 * 2.0  # 94


def test_trailing_rejects_loss_side_line():
    """追踪线落在开仓价亏损侧（ATR 过大）时放弃，不允许把止损推到保本之下。"""
    stop, floating_r = _continuous_trailing_stop(
        _long_state(), "long", 105.0, 3.0, _trail_conf(trailing_trigger_r=0.5))
    # trail = 105 - 6 = 99 <= entry 100 → 放弃
    assert stop is None
    assert floating_r == 1.0


def test_trailing_short_rejects_loss_side_line():
    stop, _ = _continuous_trailing_stop(
        _long_state(), "short", 95.0, 3.0, _trail_conf(trailing_trigger_r=0.5))
    # trail = 95 + 6 = 101 >= entry 100 → 放弃
    assert stop is None


def test_trailing_min_multiple_clamped():
    """trailing_atr_multiple 过小被钳到 0.5。"""
    stop, _ = _continuous_trailing_stop(
        _long_state(), "long", 110.0, 10.0, _trail_conf(trailing_atr_multiple=0.0))
    assert stop == 110.0 - 0.5 * 10.0


# ---------------------------------------------------------------------------
# _is_external_conditional_order 前缀识别
# ---------------------------------------------------------------------------
def test_external_prefix_matches_open_side_orders():
    for prefix in ("SL", "TP", "TS"):
        order = {"clientOrderId": f"{prefix}lxk3j9BTC1"}
        assert exits_mod._is_external_conditional_order(order) is True


def test_external_prefix_ignores_program_orders():
    """守护端自己的 PM_WS_SL_ / PM_WS_R_ 前缀绝不能被误伤。"""
    assert exits_mod._is_external_conditional_order(
        {"clientOrderId": "PM_WS_SL_BTCUSDT_L_ab12cd34"}) is False
    assert exits_mod._is_external_conditional_order(
        {"clientOrderId": "PM_WS_R_ab12cd34abcd12345678"}) is False


def test_external_prefix_reads_info_fallback():
    order = {"info": {"origClientOrderId": "TP123abcBTC9"}}
    assert exits_mod._is_external_conditional_order(order) is True


def test_external_prefix_handles_garbage():
    assert exits_mod._is_external_conditional_order(None) is False
    assert exits_mod._is_external_conditional_order({}) is False
    assert exits_mod._is_external_conditional_order({"clientOrderId": "OPEN_ORDER"}) is False


# ---------------------------------------------------------------------------
# _take_over_external_stops 集成（monkeypatch 模块级依赖）
# ---------------------------------------------------------------------------
class _RestRecorder:
    def __init__(self, open_orders):
        self.open_orders = open_orders
        self.canceled = []

    async def __call__(self, exchange, method, *args, **kwargs):
        if method == "fetch_open_orders":
            return list(self.open_orders)
        if method == "cancel_order":
            self.canceled.append(args[0])
            return {"id": args[0], "status": "canceled"}
        raise AssertionError(f"unexpected REST method: {method}")


def _patch_take_over(monkeypatch, program_stops, open_orders, algo_orders):
    """接管函数依赖全部替换为可观测 fake。"""
    async def fake_find_stops(exchange, symbol, side, pos, price, conf, force=False):
        return program_stops

    rest = _RestRecorder(open_orders)

    async def fake_algo_orders(exchange, symbol, conf, force=False):
        return algo_orders

    algo_canceled = []

    async def fake_cancel_algo(exchange, symbol, algo_id, conf):
        algo_canceled.append(algo_id)
        return {"id": algo_id}

    monkeypatch.setattr(exits_mod, "_find_stop_orders", fake_find_stops)
    monkeypatch.setattr(exits_mod, "_rest", rest)
    monkeypatch.setattr(exits_mod, "_get_open_algo_orders", fake_algo_orders)
    monkeypatch.setattr(exits_mod, "_cancel_algo", fake_cancel_algo)
    return rest, algo_canceled


def test_take_over_skips_when_program_stop_missing(monkeypatch):
    """守护端保护 STOP 未就位：不撤任何单（防止裸仓）。"""
    rest, algo_canceled = _patch_take_over(
        monkeypatch, program_stops=[],
        open_orders=[{"id": "1", "clientOrderId": "SL123"}], algo_orders=[])
    canceled = asyncio.run(exits_mod._take_over_external_stops(
        object(), "BTC/USDT:USDT", "long", {"symbol": "BTC/USDT:USDT"}, {}))
    assert canceled == 0
    assert rest.canceled == []
    assert algo_canceled == []


def test_take_over_cancels_external_only(monkeypatch):
    """STOP 已就位：只撤 SL/TP/TS 前缀且方向匹配的单，守护端单与反向单不动。"""
    program_stops = [{"clientAlgoId": "PM_WS_SL_BTCUSDT_L_ab12cd34"}]
    open_orders = [
        {"id": "sl", "clientOrderId": "SLlxk3j9BTC1", "side": "sell"},
        {"id": "tp", "clientOrderId": "TPlxk3j9BTC1", "side": "sell"},
        {"id": "pm", "clientOrderId": "PM_WS_R_ab12cd34abcd12345678", "side": "sell"},
        {"id": "open", "clientOrderId": "Olxk3j9BTC1", "side": "buy"},
    ]
    algo_orders = [{"algoId": "ts-algo", "clientAlgoId": "TSlxk3j9BTC1", "side": "sell"}]
    rest, algo_canceled = _patch_take_over(monkeypatch, program_stops, open_orders, algo_orders)

    canceled = asyncio.run(exits_mod._take_over_external_stops(
        object(), "BTC/USDT:USDT", "long", {"symbol": "BTC/USDT:USDT"}, {}))

    assert canceled == 3
    assert rest.canceled == ["sl", "tp"]          # SL/TP 撤销；PM_WS_R_ 与开仓单不动
    assert algo_canceled == ["ts-algo"]           # algo 里的 TS 移动止盈撤销


def test_take_over_ignores_wrong_side(monkeypatch):
    """方向不符（多单的 BUY 方向条件单）不撤，防止误撤开仓方向的挂单。"""
    open_orders = [{"id": "bad", "clientOrderId": "SLlxk3j9BTC1", "side": "buy"}]
    rest, _ = _patch_take_over(
        monkeypatch, program_stops=[{"clientAlgoId": "PM_WS_SL_X"}],
        open_orders=open_orders, algo_orders=[])
    canceled = asyncio.run(exits_mod._take_over_external_stops(
        object(), "BTC/USDT:USDT", "long", {"symbol": "BTC/USDT:USDT"}, {}))
    assert canceled == 0
    assert rest.canceled == []
