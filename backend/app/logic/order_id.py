# backend/app/logic/order_id.py
"""clientOrderId 生成与超时反查（R-P0-1 下单幂等）。

设计契约（ARCH_REFACTOR_PHASE3 §1.3）：
- ``make_client_order_id``：prefix ∈ {O=开仓, C=平仓, SL, TP, TS=移动止盈} +
  base36 毫秒时间戳 + 币种 + 单调 seq；字符集全部落在 Binance
  ``^[\\.A-Za-z0-9_-]{1,36}$`` 合规集内，长度 ≤36，单进程内绝对唯一
  （毫秒时间戳 + 模块级 ``itertools.count`` 单调 seq）。
- ``recover_order_by_client_id_async``：网络类异常后按 clientOrderId 反查：
  1) 先扫 ``fetch_open_orders(symbol)`` 按 ccxt 统一 ``clientOrderId`` 字段匹配；
  2) 未命中再 ``fetch_order(coid, symbol, params={'origClientOrderId': coid})``，
     ``OrderNotFound`` / 未命中 → 返回 None（调用方才允许重下）。
  每次反查最多 2 个请求，仅在异常路径触发（D6）。
"""
import itertools
import time
from typing import Any, Optional

import ccxt.async_support as ccxt

# 与交易语义一一对应的单号前缀：开仓/平仓/固定止损/固定止盈/移动止盈
VALID_PREFIXES = ('O', 'C', 'SL', 'TP', 'TS')

# 模块级单调序列：单进程内保证毫秒级同刻生成的 coid 也不重复
_seq = itertools.count(1)


def _base36(value: int) -> str:
    """非负整数转 base36（小写字母 + 数字，均属 Binance coid 合规字符集）。"""
    digits = '0123456789abcdefghijklmnopqrstuvwxyz'
    if value <= 0:
        return '0'
    chars: list[str] = []
    while value:
        value, remainder = divmod(value, 36)
        chars.append(digits[remainder])
    return ''.join(reversed(chars))


def make_client_order_id(prefix: str, symbol: str, seq: Optional[int] = None) -> str:
    """生成确定性 clientOrderId：``{prefix}{base36(ms)}{coin}{seq}``，≤36 字符。

    :param prefix: 单号用途前缀，必须是 ``VALID_PREFIXES`` 之一；
    :param symbol: ccxt 统一交易对（如 ``BTC/USDC:USDC``），取 base 币作可读后缀；
    :param seq: 显式序号（缺省用模块级单调计数器）。
    :raises ValueError: prefix 非法（防止把不可追溯的单号写进交易所）。
    """
    if prefix not in VALID_PREFIXES:
        raise ValueError(f"非法 clientOrderId prefix: {prefix}（允许 {VALID_PREFIXES}）")
    coin = str(symbol or '').split('/')[0].split(':')[0].upper()
    ts_part = _base36(int(time.time() * 1000))
    seq_part = str(next(_seq)) if seq is None else str(int(seq))
    return f"{prefix}{ts_part}{coin}{seq_part}"[:36]


def order_client_id(order: dict) -> str:
    """读取订单的 clientOrderId：兼容 ccxt 统一字段与交易所原始 ``info``。"""
    info = (order or {}).get('info') or {}
    for key in ('clientOrderId', 'origClientOrderId'):
        value = (order or {}).get(key) or info.get(key)
        if value:
            return str(value)
    return ''


async def recover_order_by_client_id_async(exchange: Any, symbol: str,
                                           client_order_id: str) -> Optional[dict]:
    """按 clientOrderId 反查订单；查不到返回 None。

    先扫挂单簿（最常见：请求已入簿但响应超时），未命中再用交易所原生
    ``origClientOrderId`` 查询兜底（订单可能已经成交/撤销但仍在订单簿历史里）。
    """
    if not client_order_id:
        return None
    try:
        open_orders = await exchange.fetch_open_orders(symbol)
    except Exception:  # noqa: BLE001 - 挂单扫描失败不阻断反查，还有 fetch_order 兜底
        open_orders = []
    for order in open_orders or []:
        if not isinstance(order, dict):
            continue
        if str((order or {}).get('symbol') or '') not in ('', symbol):
            continue
        if order_client_id(order) == client_order_id:
            return order
    try:
        return await exchange.fetch_order(
            client_order_id, symbol, params={'origClientOrderId': client_order_id})
    except ccxt.OrderNotFound:
        return None
    except TypeError:
        # 部分 fake / 旧实现不支持 params 关键字：退化为按 id 直接查一次
        try:
            return await exchange.fetch_order(client_order_id, symbol)
        except Exception:  # noqa: BLE001 - 反查失败一律按"查不到"处理
            return None
    except Exception:  # noqa: BLE001 - 反查失败返回 None，由调用方决定是否重下
        return None
