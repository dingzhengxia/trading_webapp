# tests/test_protection_replan.py
"""E 结构重估：replan_plan 约束逐条断言 + runner 触发器（纯函数，无 IO）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.protection import risk_model, runner


def _base_plan(entry=100.0, atr=2.0):
    conf = dict(risk_model.V2_DEFAULTS)
    plan = risk_model.build_plan('long', entry, atr, [95.0, 90.0, 80.0], conf, now=1000.0)
    state = risk_model.new_state('c1', 'long', entry, 10.0, plan, 1000.0)
    state['plan']['built_at'] = 1000.0
    return conf, plan, state


# ---------- replan_plan 约束 ----------

def test_deeper_structure_moves_levels_outward():
    """结构下移（新低点）→ 未触发档位外移采纳。"""
    conf, plan, state = _base_plan()
    new = risk_model.replan_plan(
        plan, 'long', (94.0, 88.0, 78.0), 2.0, 99.0, conf, 2000.0, [], reason='scheduled')
    assert new is not None
    for i in range(4):
        assert new['levels'][i] <= plan['levels'][i]
        assert new['levels'][i] == plan['levels'][i] or new['levels'][i] > 0
    # 至少有一档真的外移了
    assert new['levels'] != plan['levels']
    # 灾难线跟着 T4 走且仍在 T4 之外
    assert new['disaster_stop'] < new['levels'][3]
    # R/TP 锁定
    assert new['risk'] == plan['risk']
    assert new['tp_prices'] == plan['tp_prices']
    assert new['entry'] == plan['entry']
    assert new['replan_reason'] == 'scheduled'
    assert new['replan_count'] == 1


def test_higher_structure_rejected_no_inward_move():
    """结构上移（内移方向）→ 未触发档沿用旧线，无变化则返回 None（不空转）。"""
    conf, plan, state = _base_plan()
    new = risk_model.replan_plan(
        plan, 'long', (97.0, 92.0, 85.0), 2.0, 99.0, conf, 2000.0, [], reason='scheduled')
    assert new is None  # 档位/灾难线全没动、ATR 没变 → 无需重估


def test_triggered_tiers_frozen():
    """已触发档位冻结：T1 已减仓后，即使新结构更浅也保持旧值。"""
    conf, plan, state = _base_plan()
    old_t1 = plan['levels'][0]
    new = risk_model.replan_plan(
        plan, 'long', (94.0, 88.0, 78.0), 2.0, 99.0, conf, 2000.0, [0], reason='scheduled')
    assert new is not None
    assert new['levels'][0] == old_t1


def test_disaster_keeps_distance_from_price():
    """灾难线与现价保持 disaster_atr_buffer * ATR 的最小距离。"""
    conf, plan, state = _base_plan()
    price = 75.0  # 价格已贴近旧四档区域
    new = risk_model.replan_plan(
        plan, 'long', (94.0, 88.0, 78.0), 2.0, price, conf, 2000.0, [], reason='atr_jump')
    assert new is not None
    assert new['disaster_stop'] <= price - 2.0 * 1.5


def test_levels_stay_monotonic_with_min_gap():
    """合并后四档严格单调且满足最小间距。"""
    conf, plan, state = _base_plan()
    new = risk_model.replan_plan(
        plan, 'long', (94.0, 88.0, 78.0), 2.0, 99.0, conf, 2000.0, [1], reason='scheduled')
    assert new is not None
    levels = new['levels']
    unit = 2.0 * 0.8
    for i in (1, 2, 3):
        assert levels[i] < levels[i - 1]
        assert levels[i - 1] - levels[i] >= unit * 0.5 - 1e-9
    # T2 已触发冻结在旧值
    assert new['levels'][1] == plan['levels'][1]


def test_degenerate_structure_returns_none():
    """结构退化（三值相同，ATR 兜底路径）→ 不重估。"""
    conf, plan, state = _base_plan()
    assert risk_model.replan_plan(
        plan, 'long', (99.0, 99.0, 99.0), 2.0, 99.0, conf, 2000.0, []) is None


def test_replan_count_cap():
    """replan_count 达上限 → 拒绝重估。"""
    conf, plan, state = _base_plan()
    plan['replan_count'] = 30
    assert risk_model.replan_plan(
        plan, 'long', (94.0, 88.0, 78.0), 2.0, 99.0, conf, 2000.0, []) is None


def test_disabled_returns_none():
    conf, plan, state = _base_plan()
    conf['replan_enabled'] = False
    assert risk_model.replan_plan(
        plan, 'long', (94.0, 88.0, 78.0), 2.0, 99.0, conf, 2000.0, []) is None


def test_short_side_symmetry():
    """做空方向：外移 = 新线更高；结构上移时采纳。"""
    conf = dict(risk_model.V2_DEFAULTS)
    plan = risk_model.build_plan('short', 100.0, 2.0, [105.0, 110.0, 120.0], conf, now=1000.0)
    plan['built_at'] = 1000.0
    new = risk_model.replan_plan(
        plan, 'short', (106.0, 112.0, 122.0), 2.0, 101.0, conf, 2000.0, [], reason='atr_jump')
    assert new is not None
    for i in range(4):
        assert new['levels'][i] >= plan['levels'][i]
    assert new['disaster_stop'] > new['levels'][3]
    assert new['disaster_stop'] >= 101.0 + 2.0 * 1.5


def test_atr_only_change_updates_atr_at_plan():
    """档位没动但 ATR 剧变 → 仍重估（更新 atr_at_plan 供深度分级使用）。"""
    conf, plan, state = _base_plan()
    new = risk_model.replan_plan(
        plan, 'long', (95.0, 90.0, 80.0), 4.0, 99.0, conf, 2000.0, [], reason='atr_jump')
    assert new is not None
    assert new['atr_at_plan'] == 4.0


# ---------- runner._maybe_replan 触发器 ----------

def _mk_trigger_state(plan, tiers_done=None):
    return {'side': 'long', 'tiers_done': tiers_done or [], 'plan': plan}


def test_trigger_atr_jump():
    conf, plan, state = _base_plan()
    plan['built_at'] = 1000.0
    result = runner._maybe_replan(
        _mk_trigger_state(plan), plan, (94.0, 88.0, 78.0), 3.2, 99.0, conf, 5000.0)
    assert result is not None and result[1] == 'atr_jump'


def test_trigger_scheduled_after_interval():
    conf, plan, state = _base_plan()
    plan['built_at'] = 1000.0
    result = runner._maybe_replan(
        _mk_trigger_state(plan), plan, (94.0, 88.0, 78.0), 2.0, 99.0, conf,
        1000.0 + 86400.0 + 10)
    assert result is not None and result[1] == 'scheduled'


def test_trigger_cooldown_blocks():
    """冷却期内（距 built_at 2h < cooldown 1h 之外但 < interval）不触发。"""
    conf, plan, state = _base_plan()
    plan['built_at'] = 1000.0
    # 距建仓 2h：过了 cooldown(1h) 但远未到 interval(24h)，ATR 也没变
    result = runner._maybe_replan(
        _mk_trigger_state(plan), plan, (94.0, 88.0, 78.0), 2.0, 99.0, conf, 1000.0 + 7200)
    assert result is None


def test_trigger_disabled():
    conf, plan, state = _base_plan()
    conf['replan_enabled'] = False
    result = runner._maybe_replan(
        _mk_trigger_state(plan), plan, (94.0, 88.0, 78.0), 3.2, 99.0, conf, 5000.0)
    assert result is None


def test_trigger_atr_drop():
    conf, plan, state = _base_plan()
    plan['built_at'] = 1000.0
    result = runner._maybe_replan(
        _mk_trigger_state(plan), plan, (94.0, 88.0, 78.0), 1.0, 99.0, conf, 5000.0)
    assert result is not None and result[1] == 'atr_drop'


def test_pending_survives_replan_semantics():
    """重估只 patch plan：state 的 pending 计时器不动（decide 自然续时/清零）。"""
    conf, plan, state = _base_plan()
    state['pending'] = {'0': 1500.0}
    new = risk_model.replan_plan(
        plan, 'long', (94.0, 88.0, 78.0), 2.0, 99.0, conf, 2000.0, [], reason='scheduled')
    assert new is not None
    assert state['pending'] == {'0': 1500.0}  # replan 不触碰 state
