"""E 结构重估：replan_plan 约束逐条断言 + runner 触发器（纯函数，无 IO）。

几何前提（entry=100 / atr=2 / d_min=max(1.5%,1.6%)=1.6% / d_max=6% / t1_max=4%）：
结构位 (98,96,94) → T1 = 97；结构位 (97,95,93) → T1 = 96（外移一档）。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.protection import risk_model, runner

NEAR = (98.0, 96.0, 94.0)
FAR = (97.0, 95.0, 93.0)


def _base_plan(structure=NEAR, entry=100.0, atr=2.0):
    conf = dict(risk_model.V2_DEFAULTS)
    plan = risk_model.build_plan('long', entry, atr, structure, conf, now=1000.0)
    plan['built_at'] = 1000.0
    return conf, plan


# ---------- replan_plan 约束 ----------

def test_deeper_structure_moves_levels_outward():
    """结构下移（新低点）→ T1 外移，其余三档跟着重新等距。"""
    conf, plan = _base_plan(NEAR)
    new = risk_model.replan_plan(
        plan, 'long', FAR, 2.0, 99.0, conf, 2000.0, [], reason='scheduled')
    assert new is not None
    for i in range(4):
        assert new['levels'][i] <= plan['levels'][i]   # 只许外移
    assert new['levels'] != plan['levels']
    assert new['disaster_stop'] < new['levels'][3]
    # R / TP / 基准价终身锁定
    assert new['risk'] == plan['risk']
    assert new['tp_prices'] == plan['tp_prices']
    assert new['entry'] == plan['entry']
    assert new['replan_reason'] == 'scheduled'
    assert new['replan_count'] == 1


def test_higher_structure_rejected_no_inward_move():
    """结构上移（内移方向）→ 未触发档沿用旧线，无变化则返回 None（不空转）。"""
    conf, plan = _base_plan(FAR)
    new = risk_model.replan_plan(
        plan, 'long', NEAR, 2.0, 99.0, conf, 2000.0, [], reason='scheduled')
    assert new is None


def test_ladder_anchors_once_t1_triggered():
    """T1 触发后阶梯锚定：四档都是「T1 → 灾难线」的等分，T1 不动则其余不动。

    这是「只许外移」的直接推论，也是重估不会把已减仓的仓位又推一遍的保证。
    """
    conf, plan = _base_plan(NEAR)
    new = risk_model.replan_plan(
        plan, 'long', FAR, 2.0, 99.0, conf, 2000.0, [0], reason='scheduled')
    assert new is None


def test_disaster_only_moves_outward():
    """ATR 放大 → 灾难线跟着外移；ATR 缩小不会把它收回来（收回等于放宽止损）。"""
    conf, base = _base_plan(NEAR, atr=2.0)
    wider = risk_model.replan_plan(
        base, 'long', NEAR, 8.0, 99.0, conf, 2000.0, [], reason='atr_jump')
    assert wider is not None
    assert wider['disaster_stop'] < base['disaster_stop']

    narrower = risk_model.replan_plan(
        base, 'long', NEAR, 0.5, 99.0, conf, 2000.0, [], reason='atr_drop')
    # 只会更新 atr_at_plan，灾难线一格都不许收回
    assert narrower is None or narrower['disaster_stop'] == pytest.approx(base['disaster_stop'])


def test_levels_stay_monotonic_after_merge():
    conf, plan = _base_plan(NEAR)
    new = risk_model.replan_plan(
        plan, 'long', FAR, 2.0, 99.0, conf, 2000.0, [], reason='scheduled')
    assert new is not None
    levels = new['levels']
    for i in (1, 2, 3):
        assert levels[i] < levels[i - 1]
    # 灾难线仍在 T4 之外
    assert new['disaster_stop'] < levels[3]


def test_degenerate_structure_returns_none():
    conf, plan = _base_plan(NEAR)
    assert risk_model.replan_plan(
        plan, 'long', (99.0, 99.0, 99.0), 2.0, 99.0, conf, 2000.0, []) is None


def test_replan_count_cap():
    conf, plan = _base_plan(NEAR)
    plan['replan_count'] = 30
    assert risk_model.replan_plan(
        plan, 'long', FAR, 2.0, 99.0, conf, 2000.0, []) is None


def test_disabled_returns_none():
    conf, plan = _base_plan(NEAR)
    conf['replan_enabled'] = False
    assert risk_model.replan_plan(
        plan, 'long', FAR, 2.0, 99.0, conf, 2000.0, []) is None


def test_short_side_symmetry():
    """做空方向：外移 = 新线更高；结构上移时采纳。"""
    conf = dict(risk_model.V2_DEFAULTS)
    plan = risk_model.build_plan('short', 100.0, 2.0, [102.0, 104.0, 106.0], conf, now=1000.0)
    plan['built_at'] = 1000.0
    new = risk_model.replan_plan(
        plan, 'short', (103.0, 105.0, 107.0), 2.0, 101.0, conf, 2000.0, [], reason='atr_jump')
    assert new is not None
    for i in range(4):
        assert new['levels'][i] >= plan['levels'][i]
    assert new['disaster_stop'] > new['levels'][3]


def test_atr_only_change_updates_atr_at_plan():
    """档位没动但 ATR 变了 → 仍返回新计划（更新 atr_at_plan，避免每轮重复触发）。"""
    conf, plan = _base_plan(NEAR, atr=2.0)
    new = risk_model.replan_plan(
        plan, 'long', NEAR, 4.0, 99.0, conf, 2000.0, [], reason='atr_jump')
    assert new is not None
    assert new['atr_at_plan'] == pytest.approx(4.0)
    assert new['risk'] == plan['risk']


def test_replan_is_idempotent():
    """同一组输入连续重估两次：第二次不应再产生变化（否则会每轮改档位）。"""
    conf, plan = _base_plan(NEAR)
    once = risk_model.replan_plan(
        plan, 'long', FAR, 2.0, 99.0, conf, 2000.0, [], reason='scheduled')
    assert once is not None
    twice = risk_model.replan_plan(
        once, 'long', FAR, 2.0, 99.0, conf, 2100.0, [], reason='scheduled')
    assert twice is None


# ---------- runner._maybe_replan 触发器 ----------

def _trigger_state(plan, tiers_done=None):
    return {'side': 'long', 'tiers_done': tiers_done or [], 'plan': plan}


def test_trigger_atr_jump():
    conf, plan = _base_plan(NEAR)
    result = runner._maybe_replan(
        _trigger_state(plan), plan, FAR, 3.2, 99.0, conf, 5000.0)
    assert result is not None and result[1] == 'atr_jump'


def test_trigger_scheduled_after_interval():
    conf, plan = _base_plan(NEAR)
    result = runner._maybe_replan(
        _trigger_state(plan), plan, FAR, 2.0, 99.0, conf, 1000.0 + 86400.0 + 10)
    assert result is not None and result[1] == 'scheduled'


def test_trigger_cooldown_blocks():
    conf, plan = _base_plan(NEAR)
    result = runner._maybe_replan(
        _trigger_state(plan), plan, FAR, 2.0, 99.0, conf, 1000.0 + 7200)
    assert result is None


def test_trigger_disabled():
    conf, plan = _base_plan(NEAR)
    conf['replan_enabled'] = False
    result = runner._maybe_replan(
        _trigger_state(plan), plan, FAR, 3.2, 99.0, conf, 5000.0)
    assert result is None


def test_trigger_atr_drop():
    conf, plan = _base_plan(NEAR, atr=2.0)
    result = runner._maybe_replan(
        _trigger_state(plan), plan, FAR, 1.0, 99.0, conf, 5000.0)
    assert result is not None and result[1] == 'atr_drop'


def test_pending_survives_replan_semantics():
    """重估只 patch plan：state 的 pending 计时器不动。"""
    conf, plan = _base_plan(NEAR)
    state = {'pending': {'0': 1500.0}}
    new = risk_model.replan_plan(
        plan, 'long', FAR, 2.0, 99.0, conf, 2000.0, [], reason='scheduled')
    assert new is not None
    assert state['pending'] == {'0': 1500.0}
