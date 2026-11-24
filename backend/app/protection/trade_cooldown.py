# backend/app/protection/trade_cooldown.py
"""全局开仓冷静期：连亏两次操作自动停下，防止情绪化连续开仓。

口径（用户 2026-11-24 定义）：
- 「一次操作」不是一笔 income 事件：一次批量开仓/批量平仓算一次操作，
  系统自动止损（STOP 触发）算一次；止盈离场是盈利、不算做错。
  实现：把当日 REALIZED_PNL income 按时间窗口（默认 3 分钟）聚合成操作，
  同一窗口内的多笔 income（批量平仓多个币、分档止盈+止损同一回合）合计为该操作的盈亏。
- 连续 N 次（默认 2）操作级亏损 → 自动打开冷静开关。
- 冷静期内**直接拒绝开仓**（不是挂单排队等到期再开），到期自动解除；
  用户也可以随时在前端手动关掉提前恢复。

设置项（user settings）：
- trade_cooldown_enabled       冷静开关（true = 冷静中，拒绝开仓）
- trade_cooldown_minutes       冷静时长（分钟）
- trade_cooldown_loss_streak   触发连亏次数阈值
- trade_cooldown_until         冷静结束时间（ISO，打开开关时写入）
- trade_cooldown_triggered_by  'manual' | 'auto'

状态存 user settings（与开关同处），重启不丢、前端一个接口就能看到全貌。

铁律与 entry_gate 一致：闸门是为省钱，任何自身异常一律放行，绝不卡死交易。
"""
import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

# 同一「操作」的 income 时间窗口：批量平仓的任务循环里逐币下单，
# 前后间隔通常在分钟级；两个独立操作之间不会贴得这么近。
OPERATION_WINDOW_SECONDS = 180.0
# income 查询结果短缓存：一次批量开仓会并发过 N 次闸门，别重复拉当天流水
_INCOME_CACHE_TTL = 30.0

DEFAULTS: Dict[str, Any] = {
    'trade_cooldown_enabled': False,
    'trade_cooldown_minutes': 60,
    'trade_cooldown_loss_streak': 2,
    'trade_cooldown_until': None,
    'trade_cooldown_triggered_by': None,
}

_income_cache: Dict[str, Tuple[float, Any]] = {}
_income_lock = asyncio.Lock()


def _load_settings() -> Dict[str, Any]:
    from ..config.config import load_settings
    return load_settings() or {}


def _save(settings: Dict[str, Any]) -> None:
    from ..config.config import save_settings
    if not save_settings(settings):
        logger.warning('冷静期状态写库失败（下次开仓会重新判定）')


def _until_of(settings: Dict[str, Any]) -> Optional[datetime]:
    raw = settings.get('trade_cooldown_until')
    if not raw:
        return None
    try:
        until = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    if until.tzinfo is None:  # 兼容历史无时区数据
        until = until.replace(tzinfo=timezone.utc)
    return until


def cooldown_state(settings: Optional[Dict[str, Any]] = None,
                   now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """当前冷静状态；冷静中返回 {'until','remaining_sec','minutes','triggered_by'}，否则 None。"""
    settings = settings if settings is not None else _load_settings()
    if not bool(settings.get('trade_cooldown_enabled', False)):
        return None
    until = _until_of(settings)
    now = now or datetime.now(timezone.utc)
    if until is None or now >= until:
        return None  # 过期：由 open_gate 前的 release 负责落库解除
    return {
        'until': until,
        'remaining_sec': int((until - now).total_seconds()),
        'minutes': int(settings.get('trade_cooldown_minutes', DEFAULTS['trade_cooldown_minutes']) or 0),
        'triggered_by': str(settings.get('trade_cooldown_triggered_by') or 'manual'),
    }


def open_cooldown(triggered_by: str, minutes: Optional[int] = None,
                  settings: Optional[Dict[str, Any]] = None,
                  now: Optional[datetime] = None) -> Dict[str, Any]:
    """打开冷静开关并写库；minutes 缺省用配置值。返回写入后的状态。"""
    settings = settings if settings is not None else _load_settings()
    if minutes is None:
        minutes = int(settings.get('trade_cooldown_minutes', DEFAULTS['trade_cooldown_minutes']) or 60)
    minutes = max(1, int(minutes))
    start = now or datetime.now(timezone.utc)
    settings['trade_cooldown_enabled'] = True
    settings['trade_cooldown_minutes'] = minutes
    settings['trade_cooldown_until'] = (start + timedelta(minutes=minutes)).isoformat()
    settings['trade_cooldown_triggered_by'] = triggered_by
    _save(settings)
    return {'until': _until_of(settings), 'remaining_sec': minutes * 60,
            'minutes': minutes, 'triggered_by': triggered_by}


def release_cooldown() -> None:
    """解除冷静（到期惰性解除 / 用户手动关闭共用）。"""
    settings = _load_settings()
    if not bool(settings.get('trade_cooldown_enabled', False)):
        return
    settings['trade_cooldown_enabled'] = False
    settings['trade_cooldown_until'] = None
    settings['trade_cooldown_triggered_by'] = None
    _save(settings)
    logger.info('✅ 开仓冷静期已解除，恢复开仓')


# ------------------------------------------------------------------ 当日盈亏
async def _fetch_income_today(exchange: Any) -> List[Dict[str, Any]]:
    """当日 REALIZED_PNL income（按 time 升序）。30s 缓存，并发开仓共用一份。"""
    now = time.monotonic()
    cached = _income_cache.get('today')
    if cached and now - cached[0] < _INCOME_CACHE_TTL:
        return cached[1]

    async with _income_lock:
        cached = _income_cache.get('today')
        if cached and time.monotonic() - cached[0] < _INCOME_CACHE_TTL:
            return cached[1]

        from ..config.config import load_settings
        from ..core.rest_guardian import shared_guardian
        from ..core.guarded_exchange import raw_rest_method

        day_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        rows = await shared_guardian().call(
            raw_rest_method(exchange, 'fapiPrivateGetIncome'),
            {'incomeType': 'REALIZED_PNL', 'startTime': int(day_start.timestamp() * 1000),
             'limit': 1000},
            priority='LOW')
        rows = [r for r in (rows or []) if isinstance(r, dict)]
        rows.sort(key=lambda r: int(r.get('time') or 0))
        _income_cache['today'] = (time.monotonic(), rows)
        return rows


def aggregate_operations(rows: List[Dict[str, Any]],
                         window_seconds: float = OPERATION_WINDOW_SECONDS) -> List[Dict[str, Any]]:
    """把逐笔 income 聚合成「操作」：时间相邻（< window）的合并，盈亏合计。

    返回 [{'end_ts': 本操作最后一笔时间(ms), 'pnl': 合计盈亏, 'count': 笔数}]，按时间升序。
    """
    ops: List[Dict[str, Any]] = []
    last_ts: Optional[int] = None
    window_ms = window_seconds * 1000.0  # income.time 是毫秒
    for row in rows:
        ts = int(row.get('time') or 0)
        pnl = float(row.get('income') or 0.0)
        if last_ts is None or ts - last_ts > window_ms or not ops:
            ops.append({'end_ts': ts, 'pnl': pnl, 'count': 1})
        else:
            ops[-1]['pnl'] += pnl
            ops[-1]['count'] += 1
            ops[-1]['end_ts'] = ts
        last_ts = ts
    return ops


def consecutive_losses(operations: List[Dict[str, Any]], streak: int) -> Optional[List[Dict[str, Any]]]:
    """最近 streak 个操作是否全部亏损；是则返回这几笔，否则 None。"""
    if streak <= 0 or len(operations) < streak:
        return None
    tail = operations[-streak:]
    if all(op['pnl'] < 0 for op in tail):
        return tail
    return None


# ------------------------------------------------------------------ 闸门入口
async def blocking_reason(exchange: Any) -> Optional[str]:
    """开仓闸门（在 entry_gate 最先调用）。返回拒绝原因；允许开仓返回 None。

    - 冷静中 → 拒绝（直接拒，不排队：到期后下一次开仓自然放行）；
    - 未冷静 → 查当日操作盈亏，连续 N 次亏损则自动打开冷静并拒绝本单；
    - 任何异常放行：闸门不能因为自己挂掉而让交易停摆。
    """
    try:
        settings = _load_settings()
        state = cooldown_state(settings)
        if state:
            left_min = max(1, int(round(state['remaining_sec'] / 60)))
            who = '自动（连亏触发）' if state['triggered_by'] == 'auto' else '手动'
            return (f'冷静期中（{who}触发），期间拒绝开新仓，'
                    f'约 {left_min} 分钟后自动解除')
        # 到期未解除（过期后还没人开过仓）：先落库解除，避免状态一直挂着
        if bool(settings.get('trade_cooldown_enabled', False)):
            release_cooldown()

        streak = int(settings.get('trade_cooldown_loss_streak',
                                  DEFAULTS['trade_cooldown_loss_streak']) or 2)
        minutes = int(settings.get('trade_cooldown_minutes',
                                   DEFAULTS['trade_cooldown_minutes']) or 60)
        rows = await _fetch_income_today(exchange)
        tail = consecutive_losses(aggregate_operations(rows), streak)
        if not tail:
            return None

        amounts = '、'.join(f"{op['pnl']:+.2f}" for op in tail)
        open_cooldown('auto', minutes, settings)
        logger.warning(
            f'🧊 当日连续 {streak} 次操作亏损（{amounts} USDT），自动进入冷静期 {minutes} 分钟，'
            f'期间所有开仓请求将被拒绝')
        return (f'当日已连续 {streak} 次操作亏损（{amounts} USDT），'
                f'自动进入冷静期 {minutes} 分钟，本单被拒绝')
    except Exception as exc:  # noqa: BLE001 - 闸门故障不能阻断交易
        logger.warning(f'🧊 冷静期闸门检查异常（放行）: {exc}')
        return None
