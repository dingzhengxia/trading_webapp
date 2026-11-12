# backend/app/signals/runtime.py
"""信号运行时：冷却状态持久化、热门币种缓存、信号发射队列与时间工具。

- 冷却状态持久化改用任务 A 的 SQLite signal_state 表（替代 monitor 的
  signal_cooldown.json），单行键 'alerted_states'，value 为 {alert_key: ISO 时间} 字典。
- emit_signal 可被任意线程调用（策略在线程池中执行）：线程安全入队，
  由 SignalStore 的异步消费 task 落库并触发自动开仓。
"""
import queue
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from uuid import uuid4

from ..core import database

ALERT_STATES_KEY = 'alerted_states'

# 全局共享状态：dict 单项读写靠 GIL 原子，但遍历/清理需要锁（策略在线程池并发执行）
_alert_states_lock = threading.Lock()
alerted_states: Dict[str, datetime] = {}
cached_top_symbols: List[str] = []

# 信号发射队列：emit_signal（任意线程） -> SignalStore 异步消费
signal_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()


# ------------------------------------------------------------------ 冷却状态持久化
def load_alert_states() -> None:
    """从 SQLite signal_state 表加载冷却状态，丢弃已过期条目（原地更新，保持引用稳定）。"""
    now_utc = datetime.now(timezone.utc)
    loaded: Dict[str, datetime] = {}
    try:
        raw = database.get_value('signal_state', ALERT_STATES_KEY, {})
        if isinstance(raw, dict):
            for key, iso in raw.items():
                try:
                    dt = datetime.fromisoformat(str(iso))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt > now_utc:
                        loaded[key] = dt
                except (ValueError, TypeError):
                    continue
    except Exception as e:
        print(f"--- [WARNING] 加载信号冷却状态失败（安全降级为空）: {e} ---")
    alerted_states.clear()
    alerted_states.update(loaded)
    print(f"--- [INFO] 已加载信号冷却状态，有效条目: {len(alerted_states)} ---")


def save_alert_states() -> None:
    """把未过期的冷却状态写回 SQLite（单行原子写；原地清理过期条目）。"""
    try:
        now_utc = datetime.now(timezone.utc)
        with _alert_states_lock:
            expired = [k for k, v in alerted_states.items() if v <= now_utc]
            for key in expired:
                del alerted_states[key]
            payload = {k: v.isoformat() for k, v in alerted_states.items()}
        database.set_value('signal_state', ALERT_STATES_KEY, payload)
    except Exception as e:
        print(f"--- [ERROR] 保存信号冷却状态失败: {e} ---")


# ------------------------------------------------------------------ 时间工具
def timeframe_to_minutes(tf_str) -> int:
    """'1h' -> 60 / '4h' -> 240 / '1d' -> 1440，非法输入返回 0。"""
    try:
        if not tf_str or len(tf_str) < 2:
            return 0
        num = int(tf_str[:-1])
        unit = tf_str[-1].lower()
        if unit == 'm':
            return num
        if unit == 'h':
            return num * 60
        if unit == 'd':
            return num * 24 * 60
        if unit == 'w':
            return num * 7 * 24 * 60
        return 0
    except (ValueError, TypeError):
        return 0


def calculate_cooldown_time(minutes, align_to_period_end=True) -> datetime:
    """计算冷却到期时间。

    align_to_period_end=True 时对齐到当前 K 线周期结束（minutes 代表周期分钟数）；
    否则从现在起加 minutes 分钟。
    """
    now_utc = datetime.now(timezone.utc)

    if not align_to_period_end:
        if minutes <= 0:
            return now_utc + timedelta(minutes=1)
        return now_utc + timedelta(minutes=minutes)

    period_minutes = int(minutes)
    if period_minutes <= 0:
        return now_utc + timedelta(minutes=1)

    if period_minutes >= 1440:
        # 日线及以上：对齐到 UTC 午夜
        return (now_utc + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    total_minutes_of_day = now_utc.hour * 60 + now_utc.minute
    start_minute_of_period = (total_minutes_of_day // period_minutes) * period_minutes
    period_start_time = now_utc.replace(hour=start_minute_of_period // 60,
                                        minute=start_minute_of_period % 60,
                                        second=0, microsecond=0)
    period_end_time = period_start_time + timedelta(minutes=period_minutes)
    if period_end_time < now_utc:
        period_end_time += timedelta(minutes=period_minutes)
    return period_end_time


# ------------------------------------------------------------------ 信号发射
def emit_signal(*, symbol: str, full_symbol: str, timeframe: str, strategy: str,
                strategy_index: int, direction: str, price, title: str, message: str,
                dedupe_key: str, volume_ratio=None) -> None:
    """构造结构化信号记录并入队（线程安全，可被任意线程调用）。

    由 SignalStore 的异步消费 task 消费：落库 + 触发自动开仓过滤链。
    volume_ratio：当前量/动态基准的倍数（按周期进度调整），推送层用它做
    「非静态币放量达标才推」的过滤；无法计算时为 None。
    """
    base = str(symbol).split('/')[0].split(':')[0].upper()
    try:
        ratio_value = float(volume_ratio) if volume_ratio is not None else None
        if ratio_value is not None and ratio_value != ratio_value:  # NaN 防御
            ratio_value = None
    except (TypeError, ValueError):
        ratio_value = None
    record = {
        'id': uuid4().hex,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'symbol': base,
        'full_symbol': str(full_symbol or symbol),
        'timeframe': str(timeframe),
        'strategy': str(strategy),
        'strategy_index': int(strategy_index or 0),
        'direction': str(direction or 'neutral'),
        'price': float(price) if price is not None else None,
        'volume_ratio': ratio_value,
        'title': str(title or ''),
        'message': str(message or ''),
        'dedupe_key': str(dedupe_key),
    }
    signal_queue.put(record)
