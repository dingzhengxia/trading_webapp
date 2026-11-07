# backend/app/signals/signal_store.py
"""线程安全的信号环形缓冲 + 扫描统计（MERGE_PLAN §3.3）。"""
import threading
from collections import deque
from typing import Any, Dict, List, Optional

MAX_SIGNALS = 200  # 环形缓冲上限，与前端展示上限一致


class SignalStore:
    """保存最近 MAX_SIGNALS 条结构化信号，以及扫描/自动开仓运行状态。"""

    def __init__(self, max_signals: int = MAX_SIGNALS):
        self._buffer: deque = deque(maxlen=max_signals)
        self._lock = threading.Lock()
        # 扫描统计
        self._stats: Dict[str, Any] = {
            'last_scan_at': None,
            'next_scan_at': None,
            'scanned_symbols': 0,
            'emitted_count': 0,
            'error_count': 0,
            'last_error': None,
            'running': False,
        }
        # 自动开仓状态
        self._auto: Dict[str, Any] = {
            'auto_trade_enabled': False,
            'last_auto_open': None,
        }

    # -------------------------------------------------------------- 信号缓冲
    def add(self, record: Dict[str, Any]) -> None:
        with self._lock:
            self._buffer.append(dict(record))
            self._stats['emitted_count'] += 1

    def recent(self, limit: int = 50, direction: Optional[str] = None) -> List[Dict[str, Any]]:
        """按时间倒序返回最近 limit 条信号（可按 direction 过滤）。"""
        with self._lock:
            items = list(self._buffer)
        if direction:
            items = [s for s in items if s.get('direction') == direction]
        items.reverse()
        return items[:max(0, int(limit))]

    def clear(self) -> int:
        """清空缓冲，返回被清除的条数。"""
        with self._lock:
            count = len(self._buffer)
            self._buffer.clear()
            return count

    def __len__(self) -> int:
        with self._lock:
            return len(self._buffer)

    # -------------------------------------------------------------- 统计状态
    def update_scan_status(self, **fields) -> None:
        with self._lock:
            for key, value in fields.items():
                if key in self._stats:
                    self._stats[key] = value

    def update_auto_status(self, **fields) -> None:
        with self._lock:
            for key, value in fields.items():
                if key in self._auto:
                    self._auto[key] = value

    def snapshot(self) -> Dict[str, Any]:
        """返回当前统计快照（status + auto 状态合并）。"""
        with self._lock:
            status = dict(self._stats)
            status.update(self._auto)
            return status
