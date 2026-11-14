"""开仓前置风控闸门：黑天鹅状态 / 冷却期内不开新仓。

为什么放在开仓前而不是靠平仓兜底：
  2026-11-14 ETH 两次「开仓 16 秒后被平」——开仓计划在 15m 本根 K 线已经跌 1.27%
  （位移 23.97 > 阈值 20.37 且跌破前 4 根低点）的时候买入，风控 3 秒后就按同一信号
  全平。技术上平仓是对的，错的是**在崩的中途建仓**：白付手续费+滑点，账面还显示
  「有过一笔亏损交易」。闸门把这种仓位挡在门外，并明确告诉用户原因。

判定顺序（都廉价，且任一异常一律放行，绝不因为风控自己出问题而卡住交易）：
  1. 同币黑天鹅冷却（cooldown.py）：刚被黑天鹅全平过的币，冷却期内直接拒；
  2. 当前是否正处于黑天鹅状态（与本模块平仓判定完全同一套口径，
     复用 market_data._emergency_signal，不另造标准）。
"""

from typing import Any, Dict, Optional, Tuple

from loguru import logger

from .cooldown import cooldown_remaining


def _norm_side(side: str) -> str:
    value = str(side or '').strip().lower()
    return 'short' if value in ('short', 'sell') else 'long'


def load_gate_config() -> Dict[str, Any]:
    """闸门用配置 = V2_DEFAULTS ∪ 用户覆盖（与 runner.load_config 同一口径）。

    单独实现而不 import runner：runner 依赖 engine，engine 又反向依赖交易/行情层，
    从开仓链路引它会把整条保护链拖进 import 图（易成环）。
    """
    from .config import load_protection_config
    from .risk_model import V2_DEFAULTS

    conf = dict(V2_DEFAULTS)
    raw = load_protection_config().get('position_protection', {}) or {}
    for key, value in raw.items():
        if value is not None:
            conf[key] = value
    return conf


async def check_entry_allowed(exchange, full_symbol: str, side: str,
                              conf: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    """开仓前闸门。返回 (是否允许, 拒绝原因)；允许时原因为空串。

    :param exchange: ccxt 交易所实例（与开仓同一份，复用连接与限流）
    :param full_symbol: 'ETH/USDC:USDC'
    :param side: 'buy'/'sell' 或 'long'/'short'
    """
    if conf is None:
        conf = load_gate_config()
    # 保护未接管时没有黑天鹅动作，冷却也就没有意义：直接放行（少一次 REST）
    if not bool(conf.get('enabled', False)) or not bool(conf.get('emergency_enabled', True)):
        return True, ''

    pos_side = _norm_side(side)

    try:
        left, why = cooldown_remaining(full_symbol, pos_side, conf)
    except Exception as exc:  # noqa: BLE001 - 冷却查询失败按无冷却处理
        logger.warning(f'[{full_symbol}] 查询黑天鹅冷却失败（放行）: {exc}')
        left, why = 0.0, ''
    if left > 0:
        minutes = max(1, int(round(left / 60)))
        return False, (f'该币 {minutes} 分钟前触发过黑天鹅全平（{why}），'
                       f'冷却中约剩 {minutes} 分钟，暂不开新仓')

    if not bool(conf.get('emergency_block_new_entries', True)):
        return True, ''

    try:
        from .market_data import _emergency_signal
        hit, details = await _emergency_signal(exchange, full_symbol, pos_side, conf)
    except Exception as exc:  # noqa: BLE001 - 行情取不到时放行（不能因风控自身故障停摆）
        logger.warning(f'[{full_symbol}] 开仓前黑天鹅预检失败（放行）: {exc}')
        return True, ''
    if not hit:
        return True, ''

    details = details or {}
    move = float(details.get('move') or 0.0)
    threshold = float(details.get('threshold') or 0.0)
    label = '放量加速' if details.get('volume_crash') else '结构性破位'
    return False, (f'当前正处于黑天鹅行情（{label}：本根位移 {move:.2f} / 阈值 {threshold:.2f}），'
                   f'暂不开{("多" if pos_side == "long" else "空")}仓')


async def first_blocker(exchange, full_symbol: str, side: str,
                        conf: Optional[Dict[str, Any]] = None) -> str:
    """便捷封装：允许返回空串，拒绝返回原因（供调用方直接拼日志）。"""
    allowed, reason = await check_entry_allowed(exchange, full_symbol, side, conf)
    return '' if allowed else reason
