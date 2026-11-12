# backend/app/core/open_history.py
"""开仓记录：把「控制面板选的币种」与每笔开仓结果持久化到 SQLite。

用户需求（2026-11-12）：在控制面板选好币种、点「开始开仓」后，
选了哪些币、按什么权重分配、每笔开仓成功/失败/跳过，都要留下可回看的记录，
而不是只存在于滚动的 WebSocket 日志里（重启即丢、无法回看）。

- record_batch：一次开仓任务写一条批次记录，四个开仓入口共用：
  plan（控制面板自动开仓）/ signal（信号自动开仓）/ manual（手动交易）/ rebalance（再平衡执行）；
- get_history：倒序返回最近 N 条，供前端「开仓记录」面板展示；
- 存储：open_history 表单键 JSON list（key='batches'），环形上限 MAX_RECORDS；
- 铁律：记录失败只打日志，绝不影响交易主流程。
"""
import time
import uuid

from loguru import logger
from typing import Any, Dict, List, Optional

from .database import get_value, set_value

HISTORY_KEY = 'batches'
MAX_RECORDS = 200


def record_batch(source: str, trigger: str, items: List[Dict[str, Any]],
                 snapshot: Optional[Dict[str, Any]] = None,
                 allocations: Optional[Dict[str, Any]] = None,
                 record_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """写入一条开仓批次记录并返回记录内容；items 为空时不写。

    item 约定字段（多余字段原样保留）：
      coin / side / target_value / success / error / skip_reason
      success 为 None 表示「进行中」（长任务开始时先落一条，跑完带 record_id 更新）。
    snapshot 为当时的选币配置快照（币种池、权重、总价值）；
    allocations 为计算出的每币目标分配 {'long': {...}, 'short': {...}}。
    传 record_id 时为更新既有记录（同一条被复写，不新增）。
    """
    try:
        clean_items = [dict(x) for x in (items or []) if isinstance(x, dict)]
        if not clean_items:
            return None
        success = sum(1 for x in clean_items if x.get('success') is True)
        pending = sum(1 for x in clean_items if x.get('success') is None)
        summary = {'total': len(clean_items), 'success': success,
                   'failed': len(clean_items) - success - pending, 'pending': pending}

        batches = get_value('open_history', HISTORY_KEY, [])
        if not isinstance(batches, list):
            batches = []

        if record_id:
            for idx, old in enumerate(batches):
                if isinstance(old, dict) and old.get('id') == record_id:
                    old['items'] = clean_items
                    old['summary'] = summary
                    if allocations is not None:
                        old['allocations'] = allocations
                    if snapshot:
                        old['snapshot'] = snapshot
                    if trigger:
                        old['trigger'] = trigger
                    batches[idx] = old
                    set_value('open_history', HISTORY_KEY, batches)
                    return old
            # 找不到旧记录（例如被环形清理掉）：按新增处理

        record = {
            'id': record_id or uuid.uuid4().hex,
            'ts': int(time.time() * 1000),
            'source': str(source or 'plan'),
            'trigger': str(trigger or ''),
            'snapshot': snapshot or {},
            'allocations': allocations or {},
            'items': clean_items,
            'summary': summary,
        }
        batches.append(record)
        if len(batches) > MAX_RECORDS:
            batches = batches[-MAX_RECORDS:]
        set_value('open_history', HISTORY_KEY, batches)
        return record
    except Exception as e:  # noqa: BLE001 - 记录失败绝不影响交易主流程
        logger.error("写入开仓记录失败: {}", e)
        return None


def _batch_ts(batch: Dict[str, Any]) -> int:
    try:
        return int(batch.get('ts') or 0)
    except (TypeError, ValueError):
        return 0


def get_history(limit: int = 50) -> List[Dict[str, Any]]:
    """倒序返回最近 limit 条批次记录。"""
    try:
        limit = max(1, min(int(limit or 50), MAX_RECORDS))
    except (TypeError, ValueError):
        limit = 50
    batches = get_value('open_history', HISTORY_KEY, [])
    if not isinstance(batches, list):
        return []
    batches = [b for b in batches if isinstance(b, dict)]
    batches.sort(key=_batch_ts, reverse=True)
    return batches[:limit]
