"""人工加减仓：识别 → 状态演化 → 数量/止损/止盈的连锁反应（纯函数，无 IO）。

这一组测试对应 2026-11-15 的三次事故：
· ETH/BNB 减仓后加仓回补，仓位仍小于「初始仓位」，旧逻辑完全看不见 → 计划一直按
  旧均价算，兜底 STOP 落到真实开仓价之下；
· BTC 加仓后按「旧初始仓位」比例减仓 → 标称 25%、实际砍掉剩余 79%；
· 人工减仓后「已完成档」被重置 → 同一段行情卖两次。
"""
from __future__ import annotations

import pytest

from app.protection import risk_model

CONF = dict(risk_model.V2_DEFAULTS)


def _state(entry=100.0, qty=10.0, atr=2.0, structure=(97.0, 95.0, 92.0)):
    plan = risk_model.build_plan('long', entry, atr, structure, CONF)
    state = risk_model.new_state('c1', 'long', entry, qty, plan, 1000.0)
    state['contracts'] = qty
    return state


def _snap(state, price, contracts, entry=None, atr=2.0, now=1000.0, rebased=False):
    plan = state['plan']
    return risk_model.Snapshot(
        symbol='ETH/USDC:USDC', side='long',
        entry=float(plan['entry'] if entry is None else entry),
        price=price, last_close=price, contracts=contracts, atr=atr,
        structure=(97.0, 95.0, 92.0), closed_ts=0, now=now, rebased=rebased,
    )


# ---------------------------------------------------------------------------
# 识别
# ---------------------------------------------------------------------------
def test_detect_add_when_entry_moves_even_below_original_base():
    """ETH 现场：0.733 → TP3 后剩 0.112 → 加仓到 0.333，仍小于初始仓位。"""
    state = _state(entry=1804.84, qty=0.733)
    state['q_seen'] = 0.112
    state['e_seen'] = 1804.84

    hit = risk_model.detect_intervention(state, 'long', 0.333, 1849.0, CONF)
    assert hit is not None and hit['kind'] == 'add'
    assert hit['delta_qty'] == pytest.approx(0.221)
    # 反解的成交价必须能还原出交易所均价（这就是「哪一笔把均价推上去」的唯一解）
    rebuilt = (1804.84 * 0.112 + hit['implied_price'] * 0.221) / 0.333
    assert rebuilt == pytest.approx(1849.0)
    assert hit['implied_price'] > 1849.0   # 加在均价之上，所以均价被抬高


def test_detect_add_when_added_at_same_price():
    """加在均价上：entryPrice 不动，但数量变多。"""
    state = _state(entry=100.0, qty=10.0)
    hit = risk_model.detect_intervention(state, 'long', 14.0, 100.0, CONF)
    assert hit is not None and hit['kind'] == 'add'
    assert hit['implied_price'] == pytest.approx(100.0)


def test_detect_reduce_when_only_qty_drops():
    state = _state(entry=100.0, qty=10.0)
    hit = risk_model.detect_intervention(state, 'long', 6.0, 100.0, CONF)
    assert hit is not None and hit['kind'] == 'reduce'
    assert hit['qty_pct'] == pytest.approx(-0.4)


def test_detect_ignores_rounding_drift():
    """交易所四舍五入造成的万分之一抖动不能算干预。"""
    state = _state(entry=100.0, qty=10.0)
    assert risk_model.detect_intervention(state, 'long', 10.001, 100.001, CONF) is None
    assert risk_model.detect_intervention(state, 'long', 10.0, 100.0, CONF) is None


# ---------------------------------------------------------------------------
# 加仓：重基准，但进度不变
# ---------------------------------------------------------------------------
def test_rebase_keeps_progress_and_moves_anchor():
    state = _state(entry=100.0, qty=10.0)
    state['tiers_done'] = [0]
    state['tp_done'] = [0]
    old = state['plan']

    fresh = risk_model.rebase_plan(old, 'long', 104.0, 2.0, (97.0, 95.0, 92.0), CONF, 2000.0)
    assert fresh is not None
    assert fresh['entry'] == pytest.approx(104.0)
    assert fresh['entry_prev'] == pytest.approx(100.0)
    assert fresh['rebase_count'] == 1
    # 止盈阶梯按新均价重算：TP1 必须高于旧 TP1，否则等于没有止盈
    assert fresh['tp_prices'][0] > old['tp_prices'][0]
    # 灾难线跟着新均价走，永远在均价下方
    assert fresh['disaster_stop'] < 104.0
    # 进度字段不由 rebase_plan 触碰（调用方只清 tp_armed）
    assert state['tiers_done'] == [0] and state['tp_done'] == [0]


def test_after_add_stop_is_rebuilt_from_new_basis():
    """加仓后均价 104，旧止损 103 贴在均价上：本轮必须重算，允许下移。"""
    state = _state(entry=100.0, qty=10.0)
    plan = risk_model.rebase_plan(state['plan'], 'long', 104.0, 2.0, (97.0, 95.0, 92.0), CONF, 2000.0)
    state['plan'] = plan
    state['stop'] = 103.0

    snap = risk_model.Snapshot(
        symbol='ETH/USDC:USDC', side='long', entry=104.0, price=105.0,
        last_close=105.0, contracts=14.0, atr=2.0,
        structure=(97.0, 95.0, 92.0), closed_ts=0, now=2000.0,
        exchange_stop=103.0, exchange_checked=True, rebased=True)

    result = risk_model.decide(state, snap, CONF)
    stops = [a for a in result['actions'] if a['type'] == 'stop']
    assert stops and stops[0]['tag'] == 'stop:rebase'
    assert stops[0]['price'] < 103.0
    # 下移后的止损仍必须比灾难线更靠内（不能比预算线还远）
    assert stops[0]['price'] >= plan['disaster_stop'] - 1e-9


def test_size_anchor_grows_with_add_so_later_tiers_sell_more():
    state = _state(entry=100.0, qty=10.0)
    assert risk_model.sell_qty(state, 10.0, 0.20, 0.25) == pytest.approx(2.0)

    state['size_anchor'] = 20.0          # 加仓后规模锚抬到 20
    assert risk_model.sell_qty(state, 20.0, 0.20, 0.25) == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# 减仓：进度不变，卖出量自动被剩余仓位夹住
# ---------------------------------------------------------------------------
def test_manual_reduce_does_not_reset_progress():
    state = _state(entry=100.0, qty=10.0)
    state['tiers_done'] = [0]
    state['tp_done'] = [0]
    before = (list(state['tiers_done']), list(state['tp_done']))

    # 人工减到 4，均价不变；decide 不应改动进度
    snap = _snap(state, price=101.0, contracts=4.0)
    state.update(risk_model.decide(state, snap, CONF)['patch'])
    assert (state['tiers_done'], state['tp_done']) == before


def test_tp_after_manual_reduce_cannot_clear_the_position():
    """人工把仓砍到 2，TP 依然只能卖「规模锚 10 × 20%」与「剩余 75%」取小。"""
    state = _state(entry=100.0, qty=10.0)
    state['tp_armed'] = [0]
    snap = _snap(state, price=105.9, contracts=2.0)   # TP1 = 106，已突破后回落
    result = risk_model.decide(state, snap, CONF)
    tps = [a for a in result['actions'] if a.get('tps')]
    assert tps and tps[0]['qty'] == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# 加仓后止盈：已完成档不重复卖，未完成档按新阶梯重新确认
# ---------------------------------------------------------------------------
def test_add_clears_armed_but_keeps_done():
    """加仓后 tp_armed 清空（新阶梯要重新确认突破），tp_done 保留（卖过的不再卖）。

    runner 负责清 tp_armed；这里固化「清空之后不会再卖已完成档」这一行为。
    """
    state = _state(entry=100.0, qty=10.0)
    plan = risk_model.rebase_plan(state['plan'], 'long', 104.0, 2.0, (97.0, 95.0, 92.0), CONF, 2000.0)
    state['plan'] = plan
    state['tp_done'] = [0]
    state['tp_armed'] = []

    tp1 = plan['tp_prices'][0]
    # 价格冲过 TP1 再回落：TP1 已完成，不能产生动作
    up = _snap(state, price=tp1 * 1.01, contracts=14.0, entry=104.0, now=3000.0)
    risk_model.decide(state, up, CONF)
    down = _snap(state, price=tp1 * 0.999, contracts=14.0, entry=104.0, now=3001.0)
    result = risk_model.decide(state, down, CONF)
    assert [a for a in result['actions'] if a.get('tps')] == []
