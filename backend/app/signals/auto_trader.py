# backend/app/signals/auto_trader.py
"""信号过滤器 + 自动开仓调度（MERGE_PLAN §5）。

过滤顺序（全部满足才开仓）：
1. signal_auto_trade_enabled 为 True；
2. direction in signal_auto_trade_directions（neutral 永不开仓）；
3. strategy in signal_auto_trade_strategies（方向性入场策略白名单）；
4. timeframe in signal_auto_trade_timeframes；
5. 确认数：时间窗口内同 symbol + 同 direction 的不同策略数 >= signal_auto_trade_confirmations；
6. 冷却：同 symbol 距上次自动开仓 < signal_auto_trade_cooldown_seconds -> skip；
7. 当前持仓数 < signal_auto_trade_max_positions；该 symbol 已有持仓（任意方向）skip；
8. 调用 open_callback(signal)，成功/失败记录 last_auto_open。
"""
import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from ..core import database

AUTO_TRADE_STATE_KEY = 'auto_trade_state'


class SignalAutoTrader:
    """信号 -> 自动开仓过滤链调度器。"""

    def __init__(self, settings_loader: Callable[[], Dict[str, Any]],
                 position_provider: Callable[[], Any],
                 open_callback: Callable[[Dict[str, Any]], Any]):
        """
        :param settings_loader: 返回 user settings（含 signal_* 键）
        :param position_provider: 异步 callable，返回当前持仓列表（Position 模型）
        :param open_callback: 异步 callable(signal) -> bool，由 TradingService.auto_open_from_signal 实现
        """
        self._settings_loader = settings_loader
        self._position_provider = position_provider
        self._open_callback = open_callback
        # 近期信号窗口：(ts_seconds, symbol, direction, strategy)
        self._recent: deque = deque(maxlen=500)
        # 同 symbol 上次自动开仓时间（秒级 monotonic）
        self._last_open: Dict[str, float] = {}
        self._load_state()

    # -------------------------------------------------------------- 状态持久化
    def _load_state(self) -> None:
        try:
            raw = database.get_value('signal_state', AUTO_TRADE_STATE_KEY, {}) or {}
            last_open = raw.get('last_open') or {}
            if isinstance(last_open, dict):
                # 存的是 wall-clock 秒，恢复后与新的 monotonic 无可比性时会被视为"很久以前"
                self._last_open = {str(k): float(v) for k, v in last_open.items() if
                                   time.time() - float(v) < 86400 * 7}
        except Exception as e:
            logger.warning(f"加载自动开仓冷却状态失败（安全降级）: {e}")

    def _save_state(self) -> None:
        try:
            database.set_value('signal_state', AUTO_TRADE_STATE_KEY,
                               {'last_open': {k: v for k, v in self._last_open.items()}})
        except Exception as e:
            logger.warning(f"保存自动开仓冷却状态失败: {e}")

    # -------------------------------------------------------------- 过滤链
    def _confirmation_count(self, symbol: str, direction: str,
                            window_seconds: int) -> int:
        """时间窗口内同 symbol + 同 direction 的不同策略数。"""
        now = time.time()
        strategies = set()
        for ts, sym, dirn, strat in self._recent:
            if now - ts <= window_seconds and sym == symbol and dirn == direction:
                strategies.add(strat)
        return len(strategies)

    async def on_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """信号入口：返回 {'action': 'skip'|'open'|'error', 'reason': str}。"""
        settings = self._settings_loader()
        symbol = str(signal.get('symbol') or '').upper()
        direction = str(signal.get('direction') or 'neutral').lower()
        strategy = str(signal.get('strategy') or '')
        timeframe = str(signal.get('timeframe') or '')

        # 记录到确认窗口（无论后续是否通过，信号本身计入）
        self._recent.append((time.time(), symbol, direction, strategy))

        # 1. 总开关
        if not settings.get('signal_auto_trade_enabled', False):
            return {'action': 'skip', 'reason': '自动开仓未启用'}

        # 2. 方向白名单（neutral 永不开仓）
        allowed_directions = [str(d).lower() for d in (settings.get('signal_auto_trade_directions') or [])]
        if direction == 'neutral' or direction not in allowed_directions:
            return {'action': 'skip', 'reason': f'方向 {direction} 不在允许列表'}

        # 3. 策略白名单
        allowed_strategies = [str(s) for s in (settings.get('signal_auto_trade_strategies') or [])]
        if strategy not in allowed_strategies:
            return {'action': 'skip', 'reason': f'策略 {strategy} 不在白名单'}

        # 4. 时间框架白名单
        allowed_timeframes = [str(tf) for tf in (settings.get('signal_auto_trade_timeframes') or [])]
        if timeframe not in allowed_timeframes:
            return {'action': 'skip', 'reason': f'时间框架 {timeframe} 不在允许列表'}

        # 5. 确认数：窗口内同 symbol+direction 的不同策略数
        window = int(settings.get('signal_auto_trade_confirmation_window_seconds', 300) or 300)
        required = max(1, int(settings.get('signal_auto_trade_confirmations', 1) or 1))
        confirmations = self._confirmation_count(symbol, direction, window)
        if confirmations < required:
            return {'action': 'skip', 'reason': f'确认数不足 ({confirmations}/{required})'}

        # 6. 冷却
        cooldown = int(settings.get('signal_auto_trade_cooldown_seconds', 900) or 900)
        last = self._last_open.get(symbol)
        if last is not None and time.time() - last < cooldown:
            remaining = int(cooldown - (time.time() - last))
            return {'action': 'skip', 'reason': f'{symbol} 冷却中，剩余 {remaining} 秒'}

        # 7. 持仓约束：最大持仓数 / 该 symbol 已有持仓（任意方向不叠加）
        try:
            positions = await self._position_provider() or []
        except Exception as e:
            logger.error(f"自动开仓前获取持仓失败: {e}")
            return {'action': 'error', 'reason': f'获取持仓失败: {e}'}

        max_positions = int(settings.get('signal_auto_trade_max_positions', 5) or 5)
        if len(positions) >= max_positions:
            return {'action': 'skip', 'reason': f'持仓数已达上限 ({len(positions)}/{max_positions})'}

        if any(str(getattr(p, 'symbol', '') or '').upper() == symbol for p in positions):
            return {'action': 'skip', 'reason': f'{symbol} 已有持仓，不叠加'}

        # 8. 开仓
        logger.info(f"⚡ 信号触发自动开仓: {symbol} {direction} ({strategy} @ {timeframe})")
        try:
            opened = await self._open_callback(signal)
        except Exception as e:
            logger.error(f"自动开仓回调异常: {e}")
            return {'action': 'error', 'reason': str(e)}

        if opened:
            self._last_open[symbol] = time.time()
            self._save_state()
            self._set_last_auto_open()
            return {'action': 'open', 'reason': '已提交自动开仓任务'}
        return {'action': 'error', 'reason': '开仓回调返回失败'}

    def _set_last_auto_open(self) -> None:
        """last_auto_open 由 TradingService 在任务结束时更新更准确；
        这里先记录提交时间作为兜底（快照字段）。"""
        from datetime import datetime, timezone
        # 由 store 更新；auto_trader 不持有 store 引用时静默跳过
        store = getattr(self, '_store', None)
        if store is not None:
            store.update_auto_status(last_auto_open=datetime.now(timezone.utc).isoformat())
