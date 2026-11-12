# backend/app/core/exit_rules.py
"""出场规则的唯一实现（实盘条件单与纸面跟踪共用）。

两种模式，二选一（`signal_exit_mode`）：

- `percent`（默认，与原有止盈止损设置完全一致）：
  止损/止盈按「保证金百分比 ÷ 杠杆」折算成价格距离，读
  `enable_{side}_sl_tp` / `{side}_stop_loss_percentage` / `{side}_take_profit_percentage`。
  例：20 倍杠杆、long 止损 50% → 价格 -2.5%；止盈 100% → 价格 +5%。
- `atr`：止损 = `signal_paper_sl_atr × ATR`，止盈 = `signal_paper_tp_r × 止损距离`。

调用方：`logic/sl_tp_logic_async.set_tp_sl_for_position_async`（真实挂单）与
`signals/tracker.OutcomeTracker`（纸面出场）。两者用同一份计算，纸面结果才代表实盘。
"""
from typing import Any, Dict, Optional

PERCENT_MODE = 'percent'
ATR_MODE = 'atr'


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
