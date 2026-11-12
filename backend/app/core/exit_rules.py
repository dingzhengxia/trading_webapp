# backend/app/core/exit_rules.py
"""出场规则的唯一实现（实盘条件单、超时平仓、纸面跟踪共用）。

两种价格口径，由 `signal_exit_mode` 二选一：

- `percent`（默认，与原有止盈止损设置完全一致）：
  止损/止盈按「保证金百分比 ÷ 杠杆」折算成价格距离，读
  `enable_{side}_sl_tp` / `{side}_stop_loss_percentage` / `{side}_take_profit_percentage`。
  例：20 倍杠杆、long 止损 50% → 价格 -2.5%；止盈 100% → 价格 +5%。
- `atr`：止损 = `signal_paper_sl_atr × ATR`，止盈 = `signal_paper_tp_r × 止损距离`。
  实盘的 ATR 由 `signals.market_data.atr_at()` 取（周期 = `signal_live_exit_timeframe`），
  取不到时调用方回退 percent。

另有「时间出场」：`bars_held()` 给出持仓已走的完整根数，实盘
（`signals/exit_executor.py`）与纸面（`signals/tracker.py`）都用它判断是否该按
`signal_paper_max_bars` 超时平仓。

调用方：
- `logic/sl_tp_logic_async.set_tp_sl_for_position_async` —— 真实条件单挂单；
- `signals/exit_executor.LiveExitExecutor` —— 实盘超时平仓；
- `signals/tracker.OutcomeTracker` —— 纸面模拟出场。
三处用同一份计算，纸面结果才代表实盘。
"""
import time
from typing import Any, Dict, Optional

PERCENT_MODE = 'percent'
ATR_MODE = 'atr'

#: 周期 -> 毫秒（超时平仓按"持有多少根"判定，实盘与纸面用同一张表）
TIMEFRAME_MS = {
    '1m': 60_000, '3m': 180_000, '5m': 300_000, '15m': 900_000,
    '30m': 1_800_000, '1h': 3_600_000, '2h': 7_200_000,
    '4h': 14_400_000, '6h': 21_600_000, '12h': 43_200_000, '1d': 86_400_000,
}


def timeframe_ms(timeframe: str) -> Optional[int]:
    """周期字符串 -> 毫秒；未知周期返回 None（调用方应跳过超时判定而不是猜）。"""
    return TIMEFRAME_MS.get(str(timeframe or '').lower())


def bars_held(entry_ts_ms: Optional[int], timeframe: str, now_ms: Optional[int] = None) -> Optional[int]:
    """已持有的完整 K 线根数；参数缺失时返回 None。"""
    if entry_ts_ms is None:
        return None
    span = timeframe_ms(timeframe)
    if not span:
        return None
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    return max(0, int((int(now_ms) - int(entry_ts_ms)) // span))


def exit_mode(config: Dict[str, Any]) -> str:
    mode = str(config.get('signal_exit_mode') or PERCENT_MODE).lower()
    return ATR_MODE if mode == ATR_MODE else PERCENT_MODE


def _sign(direction: str) -> int:
    return 1 if str(direction).lower() == 'long' else -1


def exit_prices(entry_price: float, direction: str, config: Dict[str, Any],
                atr: Optional[float] = None, mode: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """返回 {stop_loss, take_profit, mode}；该方向未启用止盈止损或参数无效时返回 None。

    :param mode: 强制指定口径。实盘挂单传 'percent'——那边没有 K 线/ATR，
        若跟着 `signal_exit_mode` 切到 atr 就会算不出价格而**完全不挂止损**，属于不可接受的风险。
    """
    entry = float(entry_price or 0)
    if entry <= 0:
        return None
    side = 'long' if _sign(direction) > 0 else 'short'
    if not config.get(f'enable_{side}_sl_tp', False):
        return None

    if mode:
        mode = ATR_MODE if str(mode).lower() == ATR_MODE else PERCENT_MODE
    else:
        mode = exit_mode(config)
    if mode == ATR_MODE:
        if not atr or float(atr) <= 0:
            return None
        risk = float(config.get('signal_paper_sl_atr', 1.5) or 1.5) * float(atr)
        reward = float(config.get('signal_paper_tp_r', 2.0) or 2.0) * risk
    else:
        leverage = float(config.get('leverage', 1) or 1)
        if leverage <= 0:
            leverage = 1.0
        risk = entry * float(config.get(f'{side}_stop_loss_percentage', 0) or 0) / 100 / leverage
        reward = entry * float(config.get(f'{side}_take_profit_percentage', 0) or 0) / 100 / leverage

    if risk <= 0 and reward <= 0:
        return None
    sign = _sign(direction)
    return {
        'mode': mode,
        'stop_loss': round(entry - sign * risk, 8) if risk > 0 else None,
        'take_profit': round(entry + sign * reward, 8) if reward > 0 else None,
        'risk': round(risk, 8),
        'reward': round(reward, 8),
    }
