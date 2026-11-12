# backend/app/signals/tracker.py
"""信号结果跟踪（P6 闭环）：纸面持仓 + 前视收益。

两个能力共用一个 tick 循环，按 (full_symbol, timeframe) 聚合后**只请求一次 K 线**，
所有请求经 MarketDataService -> RestGuardian，不额外占用限流额度：

1. **纸面持仓**：复用 SignalAutoTrader 的过滤链（开关/方向/策略/周期/确认数/冷却/持仓上限），
   只把「下单」换成「记录」。因此纸面结果 ≈ 打开自动开仓后的真实行为，但永远不碰交易所。
   出场由 outcomes.simulate_exit 决定：ATR 止损 / R 倍数止盈 / 超时平仓。
2. **前视收益**：每条方向性信号记录 +N 根 K 线（默认 4/12）的方向性收益，
   用于按策略统计「信号发出后到底赚不赚」，是后续调参唯一的客观依据。

状态全部落在 signal_state 表（键见下方常量），进程重启不丢。
"""
import asyncio
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from loguru import logger

from ..core import database, exit_rules
from ..core.tasks import cancel_task
from . import outcomes
from .analysis.trend import timeframe_to_minutes
from .auto_trader import SignalAutoTrader

PAPER_POSITIONS_KEY = 'paper_positions'
PAPER_TRADES_KEY = 'paper_trades'
FORWARD_RESULTS_KEY = 'signal_forward_results'

MAX_TRADES = 300        # 已平仓纸面记录上限
MAX_FORWARD = 800       # 前视结果上限（约等于几千条信号里最近的一部分）
MIN_TICK_SECONDS = 60
DEFAULT_INTERVAL_SECONDS = 300
DEFAULT_FORWARD_BARS = [4, 12]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(key: str, default):
    try:
        value = database.get_value('signal_state', key, default)
        return value if isinstance(value, type(default)) else default
    except Exception as e:  # DB 不可用时不阻塞信号链路
        logger.warning(f"读取 {key} 失败（使用默认值）: {e}")
        return default


def _save(key: str, value) -> None:
    try:
        database.set_value('signal_state', key, value)
    except Exception as e:
        logger.warning(f"保存 {key} 失败: {e}")


class OutcomeTracker:
    """纸面持仓 + 前视收益的后台跟踪器。"""

    def __init__(self, settings_loader, market_data, store,
                 interval_seconds: int = DEFAULT_INTERVAL_SECONDS):
        self._settings_loader = settings_loader
        self._market = market_data
        self._store = store
        self._interval = max(MIN_TICK_SECONDS, int(interval_seconds))

        self._positions: List[Dict[str, Any]] = _load(PAPER_POSITIONS_KEY, [])
        self._trades: List[Dict[str, Any]] = _load(PAPER_TRADES_KEY, [])
        self._forward: Dict[str, Dict[str, Any]] = _load(FORWARD_RESULTS_KEY, {})
        # 通过过滤链、等待用 K 线计算 ATR 后建仓的信号
        self._pending: List[Dict[str, Any]] = []

        self._chain = SignalAutoTrader(
            settings_loader=self._paper_settings,
            position_provider=self._open_positions,
            open_callback=self._accept,
            state_key='paper_state',
            label='纸面跟踪',
        )
        self._task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------ 配置视图
    def _paper_settings(self) -> Dict[str, Any]:
        """把纸面开关映射到过滤链读取的 signal_auto_trade_enabled 键上。"""
        settings = dict(self._settings_loader() or {})
        settings['signal_auto_trade_enabled'] = bool(settings.get('signal_paper_enabled', False))
        return settings

    def _params(self, settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        s = settings if settings is not None else (self._settings_loader() or {})
        bars = [int(b) for b in (s.get('signal_forward_bars') or DEFAULT_FORWARD_BARS)
                if isinstance(b, int) or str(b).isdigit()]
        return {
            'enabled': bool(s.get('signal_paper_enabled', False)),
            'exit_mode': exit_rules.exit_mode(s),
            'sl_atr': float(s.get('signal_paper_sl_atr', 1.5) or 1.5),
            'tp_r': float(s.get('signal_paper_tp_r', 2.0) or 2.0),
            'max_bars': int(s.get('signal_paper_max_bars', 6) or 6),
            'value_usd': float(s.get('signal_auto_trade_value_usd', 100) or 100),
            'forward_bars': bars or list(DEFAULT_FORWARD_BARS),
        }

    # ------------------------------------------------------------ 生命周期
    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_loop())
            logger.info("📈 [跟踪] 纸面/前视跟踪循环已启动")

    async def stop(self) -> None:
        task, self._task = self._task, None
        await cancel_task(task)

    async def _run_loop(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # 单轮失败不影响下一轮
                logger.error(f"📈 [跟踪] tick 异常: {e}")
            await asyncio.sleep(self._interval)

    # ------------------------------------------------------------ 信号入口
    async def on_signal(self, signal: Dict[str, Any]) -> None:
        """分发器每条信号调用一次；未启用纸面跟踪时只做前视记录（由 tick 补算）。"""
        if not self._settings_loader().get('signal_paper_enabled', False):
            return
        try:
            await self._chain.on_signal(signal)
        except Exception as e:
            logger.error(f"📈 [跟踪] 纸面过滤链异常 {signal.get('symbol')}: {e}")

    async def _open_positions(self) -> List[SimpleNamespace]:
        """给过滤链看的「当前持仓」（只有 symbol 会被读取）。"""
        return [SimpleNamespace(symbol=p['symbol']) for p in self._positions]

    async def _accept(self, signal: Dict[str, Any]) -> bool:
        """过滤链通过后不立刻建仓：先入队，等 tick 用该周期 K 线算 ATR。"""
        self._pending.append(dict(signal))
        return True

    # ------------------------------------------------------------ tick
    async def tick(self) -> Dict[str, int]:
        """一轮跟踪：先补前视收益，再结算持仓，最后处理待建仓信号。"""
        settings = self._settings_loader() or {}
        params = self._params(settings)
        self._drop_stale_pending()

        work = defaultdict(lambda: {'signals': [], 'positions': [], 'pending': []})
        for record in self._needs_forward(params['forward_bars']):
            work[(record.get('full_symbol') or record.get('symbol'), record['timeframe'])]['signals'].append(record)
        for position in self._positions:
            work[(position['full_symbol'], position['timeframe'])]['positions'].append(position)
        for signal in list(self._pending):
            key = (signal.get('full_symbol') or signal.get('symbol'), signal.get('timeframe'))
            work[key]['pending'].append(signal)

        if not work:
            return {'keys': 0, 'forward': 0, 'closed': 0, 'opened': 0}

        stats = {'keys': 0, 'forward': 0, 'closed': 0, 'opened': 0}
        for (full_symbol, timeframe), items in work.items():
            try:
                raw = await self._market.get_ohlcv(full_symbol, timeframe, 300)
                if not raw:
                    continue
                df = outcomes.to_frame(raw)
            except Exception as e:
                logger.warning(f"📈 [跟踪] 拉取 {full_symbol} {timeframe} K 线失败: {e}")
                continue
            stats['keys'] += 1
            stats['forward'] += self._record_forward(items['signals'], df, params)
            stats['closed'] += self._settle_positions(items['positions'], df)
            stats['opened'] += self._open_pending(items['pending'], df, params, settings)

        if stats['forward'] or stats['closed'] or stats['opened']:
            _save(PAPER_POSITIONS_KEY, self._positions)
            _save(PAPER_TRADES_KEY, self._trades[-MAX_TRADES:])
            _save(FORWARD_RESULTS_KEY, dict(list(self._forward.items())[-MAX_FORWARD:]))
            logger.info(f"📈 [跟踪] 前视 +{stats['forward']} / 平仓 {stats['closed']} / 开仓 {stats['opened']}")
        return stats

    # ------------------------------------------------------------ 前视收益
    def _drop_stale_pending(self) -> None:
        """超过 1 天还没拿到 K 线的待建仓信号直接丢弃，避免队列无限增长。"""
        if not self._pending:
            return
        keep = []
        for signal in self._pending:
            try:
                created = datetime.fromisoformat(str(signal.get('created_at')))
            except (TypeError, ValueError):
                continue
            if (datetime.now(timezone.utc) - created).total_seconds() < 86400:
                keep.append(signal)
        self._pending = keep

    def _needs_forward(self, horizons: List[int]) -> List[Dict[str, Any]]:
        """最近信号中，还没记全所有持有期的方向性信号。"""
        result = []
        for record in self._store.recent(200):
            if record.get('direction') not in ('long', 'short') or record.get('price') is None:
                continue
            done = self._forward.get(record['id'], {}).get('bars') or {}
            if all(str(h) in done for h in horizons):
                continue
            result.append(record)
        return result

    def _record_forward(self, signals: List[Dict[str, Any]], df, params: Dict[str, Any]) -> int:
        count = 0
        for record in signals:
            index = outcomes.bar_index(df, self._bar_ts(record))
            if index is None:
                continue
            entry = self._forward.setdefault(record['id'], {
                'symbol': record.get('symbol'), 'timeframe': record.get('timeframe'),
                'strategy': record.get('strategy'), 'direction': record.get('direction'),
                'ts': record.get('created_at'), 'bars': {},
            })
            for horizon in params['forward_bars']:
                if str(horizon) in entry['bars']:
                    continue
                value = outcomes.forward_return(df, index, horizon, record.get('direction'))
                if value is None:
                    continue
                entry['bars'][str(horizon)] = round(value * 100, 3)  # 存百分数，便于前端直读
                count += 1
        return count

    @staticmethod
    def _bar_ts(record: Dict[str, Any]) -> int:
        """信号对应的 K 线开盘时间（毫秒）。

        优先用扫描时写入的 bar_ts；老记录/外部来源没有它时，把 created_at 向下
        取整到周期起点，保证仍能和 K 线对齐。
        """
        if record.get('ts'):
            return int(record['ts'])
        try:
            created = int(datetime.fromisoformat(str(record.get('created_at'))).timestamp() * 1000)
        except (TypeError, ValueError):
            return 0
        minutes = timeframe_to_minutes(str(record.get('timeframe') or '1h')) or 60
        step = minutes * 60_000
        return created - created % step

    # ------------------------------------------------------------ 纸面持仓
    def _open_pending(self, signals: List[Dict[str, Any]], df, params: Dict[str, Any],
                      settings: Dict[str, Any]) -> int:
        opened = 0
        for signal in signals:
            key = (signal.get('full_symbol') or signal.get('symbol'), signal.get('timeframe'))
            index = outcomes.bar_index(df, self._bar_ts(signal))
            atr = outcomes.atr_at(df, index) if index is not None else None
            entry = float(signal.get('price') or 0) or (
                float(df['close'].iloc[index]) if index is not None else 0.0)
            if index is None or atr is None or entry <= 0:
                # K 线里找不到该信号（太旧或周期不匹配）：丢弃，避免脏数据
                if signal in self._pending:
                    self._pending.remove(signal)
                continue

            direction = signal['direction']
            prices = exit_rules.exit_prices(entry, direction, settings, atr=atr)
            if prices is None:
                # 该方向未启用止盈止损（或参数无效）：只按时间止损跟踪
                prices = {'mode': 'none', 'stop_loss': None, 'take_profit': None}
            self._positions.append({
                'id': uuid.uuid4().hex[:12],
                'symbol': signal.get('symbol'),
                'full_symbol': key[0],
                'timeframe': key[1],
                'strategy': signal.get('strategy'),
                'direction': direction,
                'entry_price': round(entry, 8),
                'entry_ts': int(df['timestamp'].iloc[index]),
                'atr': round(atr, 8),
                'stop_loss': prices['stop_loss'],
                'take_profit': prices['take_profit'],
                'exit_mode': prices['mode'],
                'max_bars': params['max_bars'],
                'value_usd': params['value_usd'],
                'opened_at': _now_iso(),
            })
            if signal in self._pending:
                self._pending.remove(signal)
            opened += 1
        return opened

    def _settle_positions(self, positions: List[Dict[str, Any]], df) -> int:
        closed = 0
        for position in list(positions):
            index = outcomes.bar_index(df, position['entry_ts'])
            if index is None:
                continue
            result = outcomes.simulate_exit(
                df, index, position['direction'], position['entry_price'],
                position['stop_loss'], position['take_profit'], position['max_bars'])
            if result is None:
                continue
            sign = 1 if position['direction'] == 'long' else -1
            pnl_pct = sign * (result['exit_price'] / position['entry_price'] - 1) * 100
            trade = {**position, **result, 'pnl_pct': round(pnl_pct, 3),
                     'closed_at': _now_iso(), 'status': 'closed'}
            self._trades.append(trade)
            self._positions.remove(position)
            closed += 1
        return closed

    # ------------------------------------------------------------ 对外快照
    def snapshot(self) -> Dict[str, Any]:
        """给 API 的视图：参数 + 未平仓 + 前视结果 + 汇总统计。"""
        params = self._params()
        return {
            'params': params,
            'open_positions': sorted(self._positions, key=lambda p: p['opened_at'], reverse=True),
            'trades': self._trades[-100:][::-1],
            'paper_stats': self._paper_stats(),
            'forward_stats': self._forward_stats(params['forward_bars']),
        }

    def decorate(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """把前视收益挂到信号记录上（原地修改并返回），供前端直接显示。"""
        for signal in signals:
            entry = self._forward.get(signal.get('id')) or {}
            signal['fwd'] = entry.get('bars') or None
        return signals

    def _paper_stats(self) -> Dict[str, Any]:
        trades = self._trades
        if not trades:
            return {'total': 0, 'win_rate': None, 'avg_pnl_pct': None,
                    'avg_bars': None, 'sum_pnl_pct': None, 'by_reason': {}}
        pnls = [t['pnl_pct'] for t in trades]
        by_reason: Dict[str, int] = {}
        for trade in trades:
            by_reason[trade['reason']] = by_reason.get(trade['reason'], 0) + 1
        return {
            'total': len(trades),
            'win_rate': round(sum(1 for p in pnls if p > 0) / len(pnls) * 100, 1),
            'avg_pnl_pct': round(sum(pnls) / len(pnls), 3),
            'avg_bars': round(sum(t['bars_held'] for t in trades) / len(trades), 1),
            'sum_pnl_pct': round(sum(pnls), 2),
            'by_reason': by_reason,
        }

    def _forward_stats(self, horizons: List[int]) -> List[Dict[str, Any]]:
        """按 周期×策略 聚合前视收益：样本数、各持有期均值与胜率。"""
        groups: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
        for entry in self._forward.values():
            groups[(entry.get('timeframe'), entry.get('strategy'))].append(entry)

        rows = []
        for (timeframe, strategy), items in groups.items():
            row: Dict[str, Any] = {'timeframe': timeframe, 'strategy': strategy, 'samples': len(items)}
            for horizon in horizons:
                values = [e['bars'][str(horizon)] for e in items if str(horizon) in (e.get('bars') or {})]
                key = f'h{horizon}'
                row[f'{key}_samples'] = len(values)
                row[key] = round(sum(values) / len(values), 3) if values else None
                row[f'{key}_win'] = round(sum(1 for v in values if v > 0) / len(values) * 100, 1) if values else None
            rows.append(row)
        rows.sort(key=lambda r: (-r['samples'], r.get('timeframe') or ''))
        return rows
