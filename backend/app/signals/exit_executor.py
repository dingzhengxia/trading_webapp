# backend/app/signals/exit_executor.py
"""实盘出场执行器：止盈止损巡检 + 超时平仓。

两个职责，边界不同（很重要）：

1. **止盈止损巡检**（`sltp_guard`，手动/自动仓一视同仁）：每 `guard_seconds` 拉一次
   全量挂单，对**完全没有止损**的仓位重新执行 `set_tp_sl_for_position_async` 补挂。
   开关 `signal_live_sltp_guard_enabled`（默认开）。它只补挂、不平仓，已有止损的仓位跳过。
2. **超时平仓**（只处理"信号自动开仓"的仓位）：手动开的仓不登记、不动，避免误平。
   默认关闭（`signal_live_exit_timeout_enabled=false`），开启后按 `signal_paper_max_bars`
   根 K 线强制平仓——回测显示这是唯一不拖累收益的出场口径。

价格止损/止盈的价格由交易所条件单负责（`logic/sl_tp_logic_async`，价格来自
`core/exit_rules`），这里不重复计算价格，避免两套逻辑互相撤单。
状态落 `signal_state` 表的 `live_exit_state` 键，重启不丢。
"""
import asyncio
import time
from typing import Any, Awaitable, Callable, Dict, Optional

from loguru import logger

from ..core import database, exit_rules

STATE_KEY = 'live_exit_state'
TICK_SECONDS = 60.0
GUARD_SECONDS = 300.0


def _timestamp_ms() -> int:
    return int(time.time() * 1000)


class LiveExitExecutor:
    """按持有根数超时平仓的实盘执行器（依赖注入，便于测试）。"""

    def __init__(self, settings_loader: Callable[[], Dict[str, Any]],
                 position_provider: Callable[[], Awaitable[Any]],
                 close_callback: Callable[[str], Awaitable[bool]],
                 tick_seconds: float = TICK_SECONDS,
                 sltp_guard: Optional[Callable[[], Awaitable[Dict[str, int]]]] = None,
                 guard_seconds: float = GUARD_SECONDS):
        """
        :param settings_loader: 返回 user settings（含 signal_* 键）
        :param position_provider: 异步 callable，返回当前持仓（Position 列表）
        :param close_callback: 异步 callable(full_symbol) -> bool，执行市价全平
        :param sltp_guard: 异步 callable() -> dict，巡检所有持仓的止盈止损（缺止损补挂）
        :param guard_seconds: 巡检间隔（秒），与超时平仓的 60s tick 解耦，避免频繁拉挂单
        """
        self._settings_loader = settings_loader
        self._position_provider = position_provider
        self._close_callback = close_callback
        self._tick_seconds = max(10.0, float(tick_seconds))
        self._sltp_guard = sltp_guard
        self._guard_seconds = max(30.0, float(guard_seconds))
        self._last_guard_ms: Optional[int] = None
        self._task: Optional[asyncio.Task] = None
        self._positions: Dict[str, Dict[str, Any]] = {}
        self._load_state()

    # ------------------------------------------------------------ 状态持久化
    def _load_state(self) -> None:
        try:
            raw = database.get_value('signal_state', STATE_KEY, {}) or {}
            saved = raw.get('positions') if isinstance(raw, dict) else None
            if isinstance(saved, dict):
                self._positions = {str(k): v for k, v in saved.items() if isinstance(v, dict)}
        except Exception as e:  # noqa: BLE001 - 状态损坏不应阻断交易
            logger.warning(f"加载实盘出场登记失败（忽略）: {e}")

    def _save_state(self) -> None:
        try:
            database.set_value('signal_state', STATE_KEY, {'positions': self._positions})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"保存实盘出场登记失败: {e}")

    # ------------------------------------------------------------ 登记
    def register(self, signal: Dict[str, Any], entry_ts_ms: Optional[int] = None) -> None:
        """开仓成功后登记，供超时平仓判定。同一 base symbol 只保留最新一条。"""
        symbol = str(signal.get('symbol') or '').upper()
        if not symbol:
            return
        self._positions[symbol] = {
            'symbol': symbol,
            'full_symbol': str(signal.get('full_symbol') or ''),
            'side': str(signal.get('direction') or '').lower(),
            'timeframe': str(signal.get('timeframe') or ''),
            'strategy': str(signal.get('strategy') or ''),
            'entry_ts': int(entry_ts_ms if entry_ts_ms is not None else _timestamp_ms()),
        }
        self._save_state()

    def unregister(self, symbol: str) -> None:
        if str(symbol or '').upper() in self._positions:
            self._positions.pop(str(symbol).upper(), None)
            self._save_state()

    def snapshot(self) -> Dict[str, Any]:
        settings = self._settings_loader() or {}
        max_bars = int(settings.get('signal_paper_max_bars', 6) or 6)
        rows = []
        for rec in self._positions.values():
            held = exit_rules.bars_held(rec.get('entry_ts'), rec.get('timeframe'), now_ms=_timestamp_ms())
            rows.append({**rec, 'bars_held': held, 'max_bars': max_bars})
        return {'enabled': bool(settings.get('signal_live_exit_timeout_enabled', False)),
                'guard_enabled': bool(settings.get('signal_live_sltp_guard_enabled', True)),
                'max_bars': max_bars, 'positions': rows}

    # ------------------------------------------------------------ 循环
    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop(), name='live-exit-executor')
        logger.info('⏱️ 实盘出场执行器已启动（超时平仓开关见 signal_live_exit_timeout_enabled）')

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - 单轮失败不能停止循环
                logger.warning(f'实盘出场执行器本轮异常: {e}')
            await asyncio.sleep(self._tick_seconds)

    async def _run_guard(self) -> int:
        """按 `guard_seconds` 节流执行止盈止损巡检，返回本轮补挂数量。"""
        if self._sltp_guard is None:
            return 0
        now = _timestamp_ms()
        if self._last_guard_ms is not None and now - self._last_guard_ms < self._guard_seconds * 1000:
            return 0
        self._last_guard_ms = now
        try:
            result = await self._sltp_guard() or {}
            return int(result.get('guarded', 0) or 0)
        except Exception as e:  # noqa: BLE001 - 巡检失败不能中断超时平仓
            logger.warning(f'止盈止损巡检失败（不影响超时平仓）: {e}')
            return 0

    async def tick(self) -> Dict[str, int]:
        """跑一轮：止盈止损巡检 + 对账 + 到期平仓。

        返回 {'closed': n, 'dropped': n, 'kept': n, 'guarded': n}。
        """
        guarded = await self._run_guard()
        if not self._positions:
            return {'closed': 0, 'dropped': 0, 'kept': 0, 'guarded': guarded}
        settings = self._settings_loader() or {}
        try:
            positions = await self._position_provider() or []
        except Exception as e:  # noqa: BLE001
            logger.warning(f'实盘出场执行器获取持仓失败，本轮跳过: {e}')
            return {'closed': 0, 'dropped': 0, 'kept': 0, 'guarded': guarded}

        live = {str(getattr(p, 'symbol', '') or '').upper(): p for p in positions}
        enabled = bool(settings.get('signal_live_exit_timeout_enabled', False))
        max_bars = int(settings.get('signal_paper_max_bars', 6) or 6)
        stats = {'closed': 0, 'dropped': 0, 'kept': 0, 'guarded': guarded}

        for symbol, rec in list(self._positions.items()):
            pos = live.get(symbol)
            if pos is None:
                # 已被止盈止损/手动平掉：登记失效
                self._positions.pop(symbol, None)
                stats['dropped'] += 1
                continue
            held = exit_rules.bars_held(rec.get('entry_ts'), rec.get('timeframe'), now_ms=_timestamp_ms())
            if not enabled or held is None or held < max_bars:
                stats['kept'] += 1
                continue
            full_symbol = str(getattr(pos, 'full_symbol', '') or rec.get('full_symbol') or '')
            if not full_symbol:
                stats['kept'] += 1
                continue
            try:
                ok = await self._close_callback(full_symbol)
            except Exception as e:  # noqa: BLE001
                logger.error(f'超时平仓 {full_symbol} 失败: {e}')
                ok = False
            if ok:
                self._positions.pop(symbol, None)
                stats['closed'] += 1
                logger.info(f'⏱️ 实盘超时平仓 {full_symbol}（持有 {held} 根 ≥ {max_bars}）')
            else:
                stats['kept'] += 1
        if stats['closed'] or stats['dropped']:
            self._save_state()
        return stats
