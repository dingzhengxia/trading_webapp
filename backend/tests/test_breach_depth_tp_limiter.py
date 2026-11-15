# tests/test_breach_depth_tp_limiter.py
"""A 破位深度分级确认：纯决策层单测（无 IO）。

几何前提：entry=100 / atr=0.5% / 结构 (98.5,97,95)
→ T1 = 98.25（结构位 1.5% + 0.5ATR 0.25%，在 [1.5%, 4%] 区间内）
→ 灾难线 94，四档 98.25 / 97.19 / 96.13 / 95.06，1 ATR = 0.5。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.protection import risk_model

ATR = 0.5
STRUCT = (98.5, 97.0, 95.0)


def _mk(entry=100.0, atr=ATR):
    conf = dict(risk_model.V2_DEFAULTS)
    plan = risk_model.build_plan('long', entry, atr, STRUCT, conf)
    state = risk_model.new_state('c1', 'long', entry, 10.0, plan, 1000.0)
    return conf, plan, state


def _snap(plan, price, now, atr=ATR):
    return risk_model.Snapshot(
        symbol='TEST/USDT:USDT', side='long',
        entry=float(plan['entry']), price=price, last_close=price,
        contracts=10.0, atr=atr, structure=STRUCT, closed_ts=0, now=now,
    )


def _reduce_actions(result):
    return [a for a in result['actions'] if a['type'] == 'reduce']


def test_geometry_precondition():
    _, plan, _ = _mk()
    assert plan['levels'][0] == 98.25
    assert plan['disaster_stop'] == 94.0


def test_deep_breach_skips_confirm():
    """深度 >= 1.5 ATR：跳过确认，立即出减仓动作。"""
    conf, plan, state = _mk()
    t1 = plan['levels'][0]
    price = t1 - 1.5 * ATR  # 深度正好 1.5 ATR，仍在 T2 之上
    result = risk_model.decide(state, _snap(plan, price, 1000.0), conf)
    acts = _reduce_actions(result)
    assert acts and acts[0].get('tiers') == [0]
    assert '0' not in (result['patch'].get('pending') or {})


def test_shallow_breach_keeps_full_confirm():
    """浅破位（<0.5 ATR）：维持完整确认秒数，首轮只登记 pending。"""
    conf, plan, state = _mk()
    price = plan['levels'][0] - 0.1  # 深度 0.2 ATR
    result = risk_model.decide(state, _snap(plan, price, 1000.0), conf)
    assert not _reduce_actions(result)
    assert result['patch']['pending'].get('0') == 1000.0


def test_depth_decay_shortens_confirm():
    """破位过程中变深：确认秒数按深度衰减（30s × 0.5 = 15s），提前触发。"""
    conf, plan, state = _mk()
    t1 = plan['levels'][0]
    r1 = risk_model.decide(state, _snap(plan, t1 - 0.1, 1000.0), conf)
    state.update(r1['patch'])
    # 16s 后深度 0.8 ATR → confirm 30*0.5=15s → 16s 已达标
    price = t1 - 0.8 * ATR
    r2 = risk_model.decide(state, _snap(plan, price, 1016.0), conf)
    acts = _reduce_actions(r2)
    assert acts and acts[0].get('tiers') == [0]


def test_pending_clears_when_price_recovers():
    conf, plan, state = _mk()
    t1 = plan['levels'][0]
    r1 = risk_model.decide(state, _snap(plan, t1 - 0.1, 1000.0), conf)
    state.update(r1['patch'])
    r2 = risk_model.decide(state, _snap(plan, t1 + 1.0, 1100.0), conf)  # 回到线上
    assert r2['patch']['pending'] == {}


def test_take_profit_waits_for_pullback():
    """价格越过全部 TP 的那一轮只登记突破，不出减仓动作（止盈见 test_tp_pullback）。"""
    conf, plan, state = _mk()
    tp3 = plan['tp_prices'][2]
    result = risk_model.decide(state, _snap(plan, tp3 + 0.5, 1000.0), conf)
    assert _reduce_actions(result) == []
    assert result['patch']['tp_armed'] == [0, 1, 2]
