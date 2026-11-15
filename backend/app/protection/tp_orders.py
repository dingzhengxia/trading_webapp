"""止盈单清理：本机器人不再往交易所预挂止盈单，这里只负责收尾。

为什么删掉「预挂 post-only 卖单」
- 挂限价卖单在 TP 上 = 把判断权交给撮合：价格第一根插针碰到 TP 就成交，
  之后真正走出的大行情一点吃不到（用户口径：超过 TP 之后，跌回 TP 才止盈）。
- 3 秒轮询本来就是干这件事的：引擎自己盯「有没有真的越过 TP」，再等它回到 TP 才减仓，
  决策在 risk_model.decide（tp_armed + 回落触发），执行在 runner._apply_reduce。
- 所以现在交易所上不应该有任何止盈单；旧版本留下的（PM_WS_TP_ 前缀的 reduceOnly 限价单）
  会抢在引擎前面成交，必须在启动/换周期时清掉。
"""
from __future__ import annotations

from typing import Any, Dict

from loguru import logger

from .state import _rest

CLIENT_TP_PREFIX = "PM_WS_TP_"


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
    """清掉本机器人遗留的止盈挂单（仓位已平 / 换口径 / 重启收尾）。

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
            await _rest(exchange, 'cancel_order', order_id, symbol,
                        priority='HIGH', conf=conf)
            canceled += 1
        except Exception as exc:  # noqa: BLE001 - 单张失败继续清其它
            logger.warning(f'[{symbol}] 撤销止盈挂单失败: {exc}')
    if canceled:
        logger.info(f'[{symbol}/{side}] 🧹 {reason}：撤销 {canceled} 张')
    return canceled
