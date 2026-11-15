"""止盈被动挂单：把 reduceOnly 限价单提前挂到交易所，全程 post-only，永不吃单。

为什么单独一层
- 「挂哪一档、挂多少、挂什么价」是纯计算，放在 risk_model（可单测、可回放）；
- 「挂单 / 核对成交 / 撤单」是 IO，集中在这里；
- 执行器（runner）只负责按顺序调用，不再自己拼下单参数。

为什么必须 post-only
- 全系统唯一允许吃单的路径是黑天鹅 / 灾难线的紧急全平（exits._market_reduce_and_confirm）。
- 止盈单全部带 GTX（Binance 的 post-only）：只要会立即成交，交易所直接拒单，
  我们下一轮再用最新盘口重挂。宁可这一轮没挂上，也不会以 taker 身份成交。
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Tuple

from loguru import logger

from .config import _f
from .state import _raw_position_side, _rest

CLIENT_TP_PREFIX = "PM_WS_TP_"

# Binance 对「post-only 会立即成交」的拒单：-5022 / 文本里带 maker 相关提示。
# 这是正常路径（价格刚穿过 TP 时盘口已经跑到挂价里面），不是故障。
_POST_ONLY_REJECT_MARKERS = (
    '-5022',
    'post only',
    'could not be executed as maker',
    'immediately trigger',
    'immediately match',
)


def _tp_client_id(symbol: str, side: str, level: int) -> str:
    compact = symbol.replace('/', '').replace(':', '')
    suffix = 'L' if side == 'long' else 'S'
    return f'{CLIENT_TP_PREFIX}{compact}_{suffix}{level}_{uuid.uuid4().hex[:6]}'[:36]


def is_post_only_reject(exc: Exception) -> bool:
    """判断异常是不是「post-only 会立即成交」被交易所拒单（可安全重试）。"""
    text = str(exc).lower()
    return any(marker in text for marker in _POST_ONLY_REJECT_MARKERS)


async def place_tp_order(exchange, symbol: str, side: str, position: Dict[str, Any],
                         qty: float, price: float, level: int,
                         conf: Dict[str, Any]) -> Dict[str, Any]:
    """挂一张 post-only 止盈限价单。失败抛异常（拒单由调用方识别后重试）。"""
    params: Dict[str, Any] = {
        'reduceOnly': True,
        'timeInForce': 'GTX',
        'newClientOrderId': _tp_client_id(symbol, side, level),
    }
    raw_ps = _raw_position_side(position)
    if raw_ps != 'BOTH':
        params['positionSide'] = raw_ps

    order_side = 'sell' if side == 'long' else 'buy'
    qty_str = exchange.amount_to_precision(symbol, qty)
    price_str = exchange.price_to_precision(symbol, price)
    return await _rest(exchange, 'create_limit_order', symbol, order_side,
                       qty_str, price_str, priority='HIGH', conf=conf, params=params)


async def fetch_tp_order(exchange, symbol: str, order_id: str,
                         conf: Dict[str, Any]) -> Dict[str, Any]:
    return await _rest(exchange, 'fetch_order', order_id, symbol,
                       priority='HIGH', conf=conf)


def tp_fill_state(order: Dict[str, Any]) -> Tuple[bool, float, bool]:
    """解析一张止盈单的成交情况：(完全成交, 已成交数量, 已终结)。

    「已终结」= 撤单/过期/拒单：单子还在但没有成交，需要重新挂。
    """
    if not isinstance(order, dict):
        return False, 0.0, False
    status = str(order.get('status') or '').lower()
    filled = _f(order.get('filled'))
    amount = _f(order.get('amount'))
    full = status in ('closed', 'filled') or (amount > 0 and filled >= amount * 0.999)
    dead = status in ('canceled', 'cancelled', 'expired', 'rejected')
    return full, filled, dead


async def cancel_tp_order(exchange, symbol: str, order_id: str,
                          conf: Dict[str, Any]) -> None:
    await _rest(exchange, 'cancel_order', order_id, symbol, priority='HIGH', conf=conf)


def _is_tp_order(order: Dict[str, Any], side: str) -> bool:
    info = order.get('info') if isinstance(order.get('info'), dict) else {}
    client_id = str(
        order.get('clientOrderId') or info.get('clientOrderId')
        or info.get('origClientOrderId') or '')
    if not client_id.startswith(CLIENT_TP_PREFIX):
        return False
    expected = 'sell' if side == 'long' else 'buy'
    order_side = str(order.get('side') or '').lower()
    return not order_side or order_side == expected


async def cancel_all_tp_orders(exchange, symbol: str, side: str,
                              conf: Dict[str, Any], reason: str = '清理止盈挂单') -> int:
    """清掉本机器人遗留的止盈挂单（仓位已平 / 换档 / 重启收尾）。

    只按 clientOrderId 前缀识别，绝不动用户在交易所手动挂的单。
    """
    try:
        orders = await _rest(exchange, 'fetch_open_orders', symbol,
                             priority='HIGH', conf=conf)
    except Exception as exc:  # noqa: BLE001 - 清理失败不影响守护
        logger.warning(f'[{symbol}] 查询止盈挂单失败: {exc}')
        return 0
    if not isinstance(orders, list):
        return 0

    canceled = 0
    for order in orders:
        if not _is_tp_order(order, side):
            continue
        order_id = str(order.get('id') or '')
        if not order_id:
            continue
        try:
            await cancel_tp_order(exchange, symbol, order_id, conf)
            canceled += 1
        except Exception as exc:  # noqa: BLE001 - 单张失败继续清其它
            logger.warning(f'[{symbol}] 撤销止盈挂单失败: {exc}')
    if canceled:
        logger.info(f'[{symbol}/{side}] 🧹 {reason}：撤销 {canceled} 张')
    return canceled


def tp_order_of(state: Dict[str, Any]) -> Dict[str, Any]:
    """账本里的止盈挂单记录（没有则空字典）。"""
    order = state.get('tp_order')
    return order if isinstance(order, dict) else {}
