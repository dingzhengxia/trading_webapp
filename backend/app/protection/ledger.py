# backend/app/protection/ledger.py
"""仓位保护 v2：仓位账本（每仓一行 + 动作审计）。

为什么不再沿用 v1 的 protection_state
- v1 把「所有仓位」写进同一个 key，每轮 `_load_state()` 读出整个 dict、
  改完再整体 `set_value` 写回。两个协程并发时后写的会把先写的成果覆盖掉
  （A 币刚标记 T1 已执行，被 B 币用旧副本写回去 → 下一轮 T1 又来一次）。
- 这里改成一行一仓：key = `symbol|side`，写入只影响自己这一行。

事件表是纯追加的审计轨迹：谁在什么时候、因为什么线、减了多少。
出问题不用再翻容器日志，直接查最近的保护事件即可。
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from ..core.database import delete_value, get_all, get_value, set_value

POSITIONS_TABLE = 'protection_positions'
EVENTS_TABLE = 'protection_events'
EVENT_KEEP = 5000          # 事件环形上限，超出后删最旧的
_PRUNE_EVERY = 200         # 每写入这么多次才做一次清理，避免每次都全表扫
_event_writes = 0


def make_key(symbol: str, side: str) -> str:
    return f'{symbol}|{side}'


def split_key(key: str) -> tuple:
    symbol, _, side = str(key).partition('|')
    return symbol, side


def load(symbol: str, side: str) -> Optional[Dict[str, Any]]:
    """读取单个仓位的风险周期状态；不存在或损坏时返回 None。"""
    try:
        data = get_value(POSITIONS_TABLE, make_key(symbol, side), None)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def save(symbol: str, side: str, state: Dict[str, Any]) -> bool:
    """写入单个仓位状态。失败返回 False（调用方继续用内存状态跑）。"""
    if not isinstance(state, dict):
        return False
    state['updated_at'] = time.time()
    try:
        set_value(POSITIONS_TABLE, make_key(symbol, side), state)
        return True
    except Exception:
        return False


def delete(symbol: str, side: str) -> None:
    """仓位已平（或无仓）时删除记录，避免旧周期被下一次开仓继承。"""
    try:
        delete_value(POSITIONS_TABLE, make_key(symbol, side))
    except Exception:
        pass


def all_positions() -> Dict[str, Dict[str, Any]]:
    """整表读取，仅用于状态接口展示；决策路径永远只读自己那一行。"""
    try:
        data = get_all(POSITIONS_TABLE)
    except Exception:
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def log_event(symbol: str, side: str, kind: str, message: str,
              level: str = 'info', **extra: Any) -> None:
    """追加一条审计事件。写失败不影响风控主流程。"""
    global _event_writes
    event = {
        'ts': time.time(),
        'symbol': symbol,
        'side': side,
        'kind': kind,
        'level': level,
        'message': message,
    }
    if extra:
        event.update(extra)
    key = f'{int(event["ts"] * 1000):013d}:{uuid.uuid4().hex[:8]}'
    try:
        set_value(EVENTS_TABLE, key, event)
        _event_writes += 1
        if _event_writes % _PRUNE_EVERY == 0:
            prune_events()
    except Exception:
        pass


def prune_events(keep: int = EVENT_KEEP) -> int:
    """只保留最近 keep 条事件，返回删除条数。"""
    try:
        data = get_all(EVENTS_TABLE)
    except Exception:
        return 0
    keys = sorted(data.keys())
    overflow = len(keys) - max(1, int(keep))
    if overflow <= 0:
        return 0
    removed = 0
    for key in keys[:overflow]:
        try:
            delete_value(EVENTS_TABLE, key)
            removed += 1
        except Exception:
            pass
    return removed


def recent_events(limit: int = 100, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
    """按时间倒序返回最近事件，可按币种过滤。"""
    try:
        data = get_all(EVENTS_TABLE)
    except Exception:
        return []
    events = [v for v in data.values() if isinstance(v, dict)]
    if symbol:
        events = [e for e in events if e.get('symbol') == symbol]
    events.sort(key=lambda e: float(e.get('ts') or 0), reverse=True)
    try:
        limit = max(1, min(int(limit), 1000))
    except (TypeError, ValueError):
        limit = 100
    return events[:limit]
