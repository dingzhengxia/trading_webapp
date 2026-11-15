# tests/test_breach_depth_tp_limiter.py
"""A 破位深度分级确认：纯决策层单测（无 IO）。

止盈已从决策层整体迁到「交易所预挂 post-only 限价单」（见 tp_orders.py 与
test_tp_passive.py），decide 不再产生 tps 动作，所以原来的单轮单档/多档合并
测试随之作废。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.protection import risk_model


def _mk(entry=100.0, atr=2.0):
    conf = dict(risk_model.V2_DEFAULTS)
    conf['risk_min_pct'] = 0.015
    conf['risk_max_pct'] = 0.08
    plan = risk_model.build_plan('long', entry, atr, [95.0, 93.0, 91.0], conf)
    state = risk_model.new_state('c1', 'long', entry, 10.0, plan, 1000.0)
    return conf, plan, state


def _snap(state, price, now, atr=2.0):
    plan = state['plan']
    return risk_model.Snapshot(
        symbol='TEST/USDT:USDT', side='long',
        entry=float(plan['entry']), price=price, last_close=price,
        contracts=10.0, base_contracts=10.0, atr=atr,
        structure=(95.0, 93.0, 91.0), closed_ts=0, now=now,
    )


def _reduce_actions(result):
    return [a for a in result['actions'] if a['type'] == 'reduce']


def test_deep_breach_skips_confirm():
    """深度 >= 1.5 ATR：跳过确认，立即出减仓动作。"""
    conf, plan, state = _mk()
    t1 = float(plan['levels'][0])
    atr = 2.0
    # 深度 = (t1 - price)/atr >= 1.5 → price <= t1 - 3.0
    price = t1 - 3.1
    result = risk_model.decide(state, _snap(state, price, 1000.0, atr), conf)
    acts = _reduce_actions(result)
    assert acts and acts[0].get('tiers') == [0]
    # T2 未被深破（0.45 ATR < 0.5），走正常确认计时；T0 必须不进入 pending（已直接触发）
    assert '0' not in (result['patch'].get('pending') or {})


def test_shallow_breach_keeps_full_confirm():
    """浅破位（<0.5 ATR）：维持完整确认秒数，首轮只登记 pending。"""
    conf, plan, state = _mk()
    t1 = float(plan['levels'][0])
    price = t1 - 0.1  # 深度 0.05 ATR
    result = risk_model.decide(state, _snap(state, price, 1000.0), conf)
    assert not _reduce_actions(result)
    assert result['patch']['pending'].get('0') == 1000.0


def test_depth_decay_shortens_confirm():
    """破位过程中变深：确认秒数按深度衰减（30s × 0.5 = 15s），提前触发。"""
    conf, plan, state = _mk()
    t1 = float(plan['levels'][0])
    # 第 1 轮浅破位登记 pending
    r1 = risk_model.decide(state, _snap(state, t1 - 0.1, 1000.0), conf)
    state.update(r1['patch'])
    # 第 2 轮（16s 后）深度 0.75 ATR → confirm 30*0.5=15s → 16s 已达标
    price = t1 - 0.75 * 2.0
    r2 = risk_model.decide(state, _snap(state, price, 1016.0), conf)
    acts = _reduce_actions(r2)
    assert acts and acts[0].get('tiers') == [0]


def test_depth_decay_disabled_by_shallow_depth():
    """破位后价格回到线内：pending 清零，确认重新计时。"""
    conf, plan, state = _mk()
    t1 = float(plan['levels'][0])
    r1 = risk_model.decide(state, _snap(state, t1 - 0.1, 1000.0), conf)
    state.update(r1['patch'])
    r2 = risk_model.decide(state, _snap(state, t1 + 1.0, 1100.0), conf)  # 回到线上
    assert r2['patch']['pending'] == {}


def test_take_profit_waits_for_pullback():
    """价格越过全部 TP 的那一轮只登记突破，不出减仓动作（止盈见 test_tp_pullback）。"""
    conf, plan, state = _mk()
    tp3 = float(plan['tp_prices'][2])
    result = risk_model.decide(state, _snap(state, tp3 + 0.5, 1000.0), conf)
    assert _reduce_actions(result) == []
    assert result['patch']['tp_armed'] == [0, 1, 2]
