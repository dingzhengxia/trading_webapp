# backend/app/protection/lots.py
"""每笔开仓（lot）独立账本：本地计划与进度完全隔离。

币安对同币种同方向的仓位强制按平均成本合并，交易所只给我们 (q, E) 两个事实；
但「这一笔自己的开仓价、四档减仓线、止盈阶梯、峰值、兜底 STOP」必须在本地
各自独立，不能被新开仓/加仓 rebase 掉。这里把 v2 的一仓一行状态升级成
「一仓一行 + 行内 lots 列表」：

    state = {
        version: 3,
        side, contracts, q_seen, e_seen, size_anchor,   # 聚合事实，供展示/干预识别
        lots: [
            {id, entry, contracts, size_anchor, plan,
             tiers_done, tp_done, tp_armed, pending, stop,
             peak, trough, attempts, interventions, ...},
            ...
        ],
    }

不变量
1. 加仓只用反解出的本笔成交价建一个新 lot，老 lot 的 plan / 进度 / 止损一字不动；
2. 人工减仓按各 lot 当前剩余数量**按比例**分摊，各 lot 的 TP/SL 价格不变，
   数量与规模锚同比缩小；
3. 程序自身减仓只扣对应 lot，其它 lot 完全不受影响；
4. 决策函数 `risk_model.decide` 仍然只认「扁平 state」，这里提供 view / writeback
   适配，不复制任何决策逻辑。
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from .risk_model import _f, _ints

STATE_VERSION = 3

# 这些字段属于单个 lot，决策时从 lot 提升到 view，决策后原样写回。
LOT_FIELDS = (
    'plan', 'contracts', 'size_anchor', 'tiers_done', 'tp_done', 'tp_armed',
    'pending', 'stop', 'peak', 'trough', 'attempts', 'interventions',
    'opened_at_ms', 'created_at', 'last_action_ts', 'position_version',
)


def new_lot(side: str, entry: float, contracts: float, plan: Dict[str, Any],
            now: float, opened_ms: int = 0, lot_id: Optional[str] = None) -> Dict[str, Any]:
    """用本笔自己的成交价与风险计划建一个独立 lot。"""
    return {
        # 8 位：交易所 clientAlgoId 总长上限 36，尾部要留得下完整 lot id
        'id': str(lot_id or uuid.uuid4().hex[:8]),
        'side': side,
        'entry': float(entry),
        'contracts': float(contracts),
        'size_anchor': float(contracts),
        'plan': plan,
        'tiers_done': [],
        'tp_done': [],
        'tp_armed': [],
        'pending': {},
        'stop': None,
        'peak': float(entry),
        'trough': float(entry),
        'opened_at_ms': int(opened_ms),
        'created_at': float(now),
        'last_action_ts': 0.0,
        'position_version': 1,
        'attempts': {},
        'interventions': [],
    }


def _from_legacy(state: Dict[str, Any]) -> Dict[str, Any]:
    """把 v2 扁平状态整体搬进一个 lot；历史均价只能作为这一笔的近似开仓价。"""
    plan = state.get('plan') or {}
    entry = _f(plan.get('entry')) or _f(state.get('exchange_entry')) or _f(state.get('e_seen'))
    contracts = _f(state.get('contracts')) or _f(state.get('q_seen'))
    lot = new_lot(
        str(state.get('side') or plan.get('side') or 'long'), entry, contracts, plan,
        _f(state.get('created_at')), opened_ms=int(_f(state.get('opened_at_ms'))),
        lot_id='legacy',
    )
    for key in LOT_FIELDS:
        if key in state:
            lot[key] = state[key]
    lot['entry'] = entry
    lot['contracts'] = contracts
    lot['size_anchor'] = _f(state.get('size_anchor')) or contracts
    state['lots'] = [lot]
    state['version'] = STATE_VERSION
    return state


def migrate(state: Optional[Dict[str, Any]], side: str, entry: float,
            contracts: float, now: float) -> Dict[str, Any]:
    """读取旧账本并升级到 v3；状态缺失时按当前交易所事实建一个空壳。"""
    if not isinstance(state, dict) or not state:
        state = {
            'version': STATE_VERSION, 'side': side, 'contracts': float(contracts),
            'q_seen': float(contracts), 'e_seen': float(entry),
            'size_anchor': float(contracts), 'created_at': float(now),
        }
    if int(_f(state.get('version'))) < STATE_VERSION or not isinstance(state.get('lots'), list) \
            or not state.get('lots'):
        _from_legacy(state)
    # 兼容手工改坏的行：空 lots 兜底成当前仓位的一笔（plan 由调用方补齐）
    if not state['lots']:
        state['lots'] = [new_lot(side, entry, contracts, {}, now)]
    state['version'] = STATE_VERSION
    return state


def add_lot(state: Dict[str, Any], side: str, price: float, qty: float,
            plan: Dict[str, Any], now: float, opened_ms: int = 0) -> Dict[str, Any]:
    """把反解出的这一笔加仓作为独立 lot 追加；已存在的 lot 一律不动。"""
    lot = new_lot(side, price, qty, plan, now, opened_ms=opened_ms)
    state.setdefault('lots', []).append(lot)
    resync(state)
    return lot


def allocate_reduce(state: Dict[str, Any], reduce_qty: float) -> List[Dict[str, Any]]:
    """把外部减仓按比例分摊到各 lot，返回被清空的 lot 列表。

    各 lot 的 plan（含 TP/SL 价格）不动；contracts 与 size_anchor 同比例缩小，
    保证后续按比例的档位减仓仍以「这一笔剩下的量」为分母。
    """
    lots = [lot for lot in state.get('lots', []) if _f(lot.get('contracts')) > 0]
    total = sum(_f(lot.get('contracts')) for lot in lots)
    if total <= 0 or reduce_qty <= 0:
        return []
    cut = min(float(reduce_qty), total)
    removed: List[Dict[str, Any]] = []
    allocated = 0.0
    for index, lot in enumerate(lots):
        q = _f(lot.get('contracts'))
        share = cut - allocated if index == len(lots) - 1 else cut * q / total
        share = min(share, q)
        allocated += share
        remain = q - share
        anchor = _f(lot.get('size_anchor')) or q
        lot['size_anchor'] = max(0.0, anchor * (remain / q))
        lot['contracts'] = remain
        lot.setdefault('interventions', []).append({
            'ts': 0, 'kind': 'external_reduce', 'delta_qty': -share,
            'qty_pct': -share / q if q > 0 else 0.0,
        })
        lot['interventions'] = lot['interventions'][-20:]
        if remain <= max(1e-9, total * 1e-6):
            removed.append(lot)
    removed_ids = {id(lot) for lot in removed}
    state['lots'] = [lot for lot in state.get('lots', []) if id(lot) not in removed_ids]
    resync(state)
    return removed


def apply_owned_reduce(state: Dict[str, Any], lot_id: Optional[str], sold_qty: float,
                       tiers: List[int], tps: List[int], now: float) -> bool:
    """程序自身减仓成交后只扣对应 lot；返回是否清空了该 lot。"""
    # 老账本（尚未迁移）沿用扁平字段，保证升级过程中不会漏记成交
    if not state.get('lots'):
        q = _f(state.get('contracts'))
        state['contracts'] = max(0.0, q - float(sold_qty))
        if tiers:
            state['tiers_done'] = sorted(set(_ints(state.get('tiers_done'))) | set(tiers))
        if tps:
            state['tp_done'] = sorted(set(_ints(state.get('tp_done'))) | set(tps))
        state['last_action_ts'] = float(now)
        state['position_version'] = int(_f(state.get('position_version'), 1)) + 1
        return state['contracts'] <= 1e-9

    lot = find_lot(state, lot_id)
    if lot is None or sold_qty <= 0:
        return False
    q = _f(lot.get('contracts'))
    remain = max(0.0, q - float(sold_qty))
    anchor = _f(lot.get('size_anchor')) or q
    lot['size_anchor'] = max(0.0, anchor * (remain / q)) if q > 0 else 0.0
    lot['contracts'] = remain
    if tiers:
        lot['tiers_done'] = sorted(set(_ints(lot.get('tiers_done'))) | set(tiers))
    if tps:
        lot['tp_done'] = sorted(set(_ints(lot.get('tp_done'))) | set(tps))
    lot['last_action_ts'] = float(now)
    lot['position_version'] = int(_f(lot.get('position_version'), 1)) + 1
    cleared = remain <= max(1e-9, q * 1e-6)
    if cleared:
        state['lots'] = [x for x in state.get('lots', []) if x is not lot]
    resync(state)
    return cleared


def sync_total(state: Dict[str, Any], total: float) -> None:
    """把各 lot 的数量校准到交易所真值（比例不变），消除精度漂移。"""
    items = [x for x in state.get('lots', []) if _f(x.get('contracts')) > 0]
    current = sum(_f(x.get('contracts')) for x in items)
    if current <= 0 or total <= 0 or abs(current - total) <= max(1e-9, total * 1e-6):
        return
    for lot in items:
        q = _f(lot.get('contracts'))
        ratio = total / current
        lot['contracts'] = q * ratio
        lot['size_anchor'] = _f(lot.get('size_anchor')) * ratio
    resync(state)


def find_lot(state: Dict[str, Any], lot_id: Optional[str]) -> Optional[Dict[str, Any]]:
    lots = state.get('lots') or []
    if lot_id is None:
        return lots[0] if len(lots) == 1 else None
    return next((x for x in lots if str(x.get('id')) == str(lot_id)), None)


def lot_view(state: Dict[str, Any], lot: Dict[str, Any]) -> Dict[str, Any]:
    """给 risk_model.decide 用的扁平视图（不复制状态，patch 由 writeback 写回 lot）。"""
    view = dict(state)
    for key in LOT_FIELDS:
        if key in lot:
            view[key] = lot[key]
    view['id'] = lot.get('id')
    return view


def writeback(lot: Dict[str, Any], patch: Dict[str, Any]) -> bool:
    """把决策 patch 写回 lot，返回是否真的有变化。"""
    changed = False
    for key, value in (patch or {}).items():
        if key in LOT_FIELDS and lot.get(key) != value:
            lot[key] = value
            changed = True
    return changed


def resync(state: Dict[str, Any]) -> None:
    """刷新聚合字段（只供展示与干预识别，不参与每笔决策）。"""
    lots = state.get('lots') or []
    state['contracts'] = sum(_f(x.get('contracts')) for x in lots)
    state['size_anchor'] = max(
        sum(_f(x.get('size_anchor')) for x in lots), _f(state.get('size_anchor')),
        _f(state.get('contracts')))
    if lots:
        state['plan'] = lots[0].get('plan', {})


def algo_lot_id(client_algo_id: Any) -> Optional[str]:
    """从 clientAlgoId 尾部解析 lot id；老单没有 lot id，返回 None。"""
    text = str(client_algo_id or '')
    if not text.startswith('PM_WS_SL_'):
        return None
    tail = text.rsplit('_', 1)[-1]
    return tail if len(tail) == 8 else None


def group_stops_by_lot(stops: List[Dict[str, Any]], lots: List[Dict[str, Any]]) -> Dict[Optional[str], List[Dict[str, Any]]]:
    """把交易所 STOP 归到对应 lot；无法归属的旧单先给唯一 lot 兜底。"""
    grouped: Dict[Optional[str], List[Dict[str, Any]]] = {}
    known = {str(x.get('id')) for x in lots}
    legacy: List[Dict[str, Any]] = []
    for order in stops or []:
        lot_id = algo_lot_id(order.get('clientAlgoId') or order.get('clientOrderId'))
        if lot_id in known:
            grouped.setdefault(lot_id, []).append(order)
        else:
            legacy.append(order)
    if legacy and len(lots) == 1:
        grouped.setdefault(str(lots[0].get('id')), []).extend(legacy)
    elif legacy:
        grouped.setdefault(None, []).extend(legacy)
    return grouped
