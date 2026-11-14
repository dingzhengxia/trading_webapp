"""黑天鹅平仓后的同币冷却：避免「开了就被平、平了又开」的无效往返。

2026-11-14 ETH 事故复盘：
  15m 的 22:00 那根 K 线一路下跌（位移 23.97 > 阈值 20.37，且跌破前 4 根低点），
  22:02:08 触发黑天鹅全平；3 分半后开仓计划又买入 ETH，22:06:04 **同一根 K 线的同一个
  信号**再次全平——两次都是 -0.06% 的往返，白付双边手续费与滑点。

根因是判定口径：黑天鹅是**状态型**信号而不是事件型。一根 15m K 线只要跌够幅度，
在它走完之前每次开仓都会立刻满足条件，等于「在这根 K 线的剩余时间里禁止建仓」。

因此需要两件事（本模块负责第 2 件，第 1 件见 entry_gate）：
  1. 开仓前闸门：处于黑天鹅状态 → 不开；
  2. 平仓后冷却：黑天鹅全平过的币，冷却一段时间内禁止再开（防 AI 立刻追回来）。

状态落 signal_state 表（与信号冷却同一份 KV），进程重启不丢。
"""

import time
from typing import Any, Dict, Optional, Tuple

from loguru import logger

from ..core import database

_TABLE = 'signal_state'
_KEY = 'protection_emergency_cooldown'


def base_coin(symbol: str) -> str:
    """'ETH/USDC:USDC' / 'ETHUSDC' / 'ETH' → 'ETH'（统一成基础币种做键）。"""
    text = str(symbol or '').strip().upper()
    if '/' in text:
        text = text.split('/', 1)[0]
    return text.split(':', 1)[0]


def _norm_side(side: str) -> str:
    value = str(side or '').strip().lower()
    return 'short' if value in ('short', 'sell') else 'long'


def _key_of(symbol: str, side: str) -> str:
    return f'{base_coin(symbol)}|{_norm_side(side)}'


def _load() -> Dict[str, Any]:
    try:
        raw = database.get_value(_TABLE, _KEY, {}) or {}
    except Exception as exc:  # noqa: BLE001 - 读不到就当作没有冷却（不停开仓）
        logger.warning(f'读取黑天鹅冷却状态失败（按无冷却处理）: {exc}')
        return {}
    return raw if isinstance(raw, dict) else {}


def _save(data: Dict[str, Any]) -> None:
    try:
        database.set_value(_TABLE, _KEY, data)
    except Exception as exc:  # noqa: BLE001 - 写失败只是冷却丢失，不应影响交易
        logger.warning(f'保存黑天鹅冷却状态失败: {exc}')


def _prune(data: Dict[str, Any], ttl: float, now: float) -> bool:
    """丢掉过期条目，返回是否有改动。"""
    stale = [k for k, v in data.items()
             if not isinstance(v, dict) or now - float(v.get('ts') or 0) >= ttl]
    for key in stale:
        data.pop(key, None)
    return bool(stale)


def note_emergency_flat(symbol: str, side: str, reason: str,
                        conf: Optional[Dict[str, Any]] = None) -> None:
    """记录一次黑天鹅全平，开启同币冷却（0 或负数表示不冷却）。"""
    ttl = max(0.0, float((conf or {}).get('emergency_cooldown_sec', 1800.0) or 0.0))
    if ttl <= 0:
        return
    now = time.time()
    data = _load()
    _prune(data, ttl, now)
    key = _key_of(symbol, side)
    data[key] = {'ts': now, 'reason': str(reason or '黑天鹅')[:120], 'symbol': str(symbol)}
    _save(data)
    logger.info(f'[{symbol}/{_norm_side(side)}] 🧊 黑天鹅冷却 {ttl / 60:.0f} 分钟'
                f'（{str(reason or "黑天鹅")[:40]}）')


def cooldown_remaining(symbol: str, side: str,
                       conf: Optional[Dict[str, Any]] = None) -> Tuple[float, str]:
    """返回 (剩余秒数, 当初触发原因)；无冷却返回 (0.0, '')。"""
    ttl = max(0.0, float((conf or {}).get('emergency_cooldown_sec', 1800.0) or 0.0))
    if ttl <= 0:
        return 0.0, ''
    data = _load()
    now = time.time()
    if _prune(data, ttl, now):
        _save(data)
    entry = data.get(_key_of(symbol, side))
    if not isinstance(entry, dict):
        return 0.0, ''
    left = ttl - (now - float(entry.get('ts') or 0))
    if left <= 0:
        return 0.0, ''
    return left, str(entry.get('reason') or '黑天鹅')


def snapshot(conf: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """当前所有生效中的冷却（供状态接口/前端展示）。"""
    ttl = max(0.0, float((conf or {}).get('emergency_cooldown_sec', 1800.0) or 0.0))
    now = time.time()
    data = _load()
    out: Dict[str, Any] = {}
    for key, entry in data.items():
        if not isinstance(entry, dict):
            continue
        left = ttl - (now - float(entry.get('ts') or 0))
        if left > 0:
            out[key] = {'remaining_sec': round(left, 1),
                        'reason': str(entry.get('reason') or ''),
                        'symbol': str(entry.get('symbol') or '')}
    return out
