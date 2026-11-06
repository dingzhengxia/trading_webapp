# backend/app/protection/algo_compat.py
"""币安条件单（STOP_MARKET）接口兼容层。

背景：monitor 依赖币安新版 Algo Order 接口（fapiPrivateGetOpenAlgoOrders /
fapiPrivatePostAlgoOrder / fapiPrivateDeleteAlgoOrder）。部分 ccxt 版本（如 4.3.x）
尚未包含这些方法，直接调用会抛 RuntimeError，导致整个仓位保护无法启动。

本模块统一封装三件事，让引擎逻辑保持零改动：
1. 查询该交易对上的条件单 → 统一成 Algo 风格的字段（algoId/clientAlgoId/orderType/...）；
2. 下达「全平型」STOP_MARKET（closePosition=True，随仓位自动调整数量）；
3. 撤销条件单。

有 Algo 接口走 Algo，没有则退回 ccxt 标准条件单（create_order/fetch_open_orders/
cancel_order），两者对引擎完全等价。
"""
from typing import Any, Dict, List

from loguru import logger

_ALGO_METHODS = (
    "fapiPrivateGetOpenAlgoOrders",
    "fapiPrivatePostAlgoOrder",
    "fapiPrivateDeleteAlgoOrder",
)

_warned = False


def supports_algo(exchange: Any) -> bool:
    """当前 ccxt 版本是否支持币安 Algo Order 接口。"""
    return all(hasattr(exchange, name) for name in _ALGO_METHODS)


def _warn_once() -> None:
    global _warned
    if _warned:
        return
    _warned = True
    logger.warning(
        "⚠️ 当前 CCXT 版本不支持币安 Algo Order 接口，仓位保护将使用旧版条件单接口"
        "（STOP_MARKET + closePosition），功能等价但建议升级 ccxt。")


def _normalize_legacy_order(order: Dict[str, Any]) -> Dict[str, Any]:
    """把 ccxt 标准条件单转成引擎识别的 Algo 字段结构。"""
    return {
        "algoId": order.get("id"),
        "clientAlgoId": order.get("clientOrderId") or order.get("info", {}).get("clientOrderId"),
        "symbol": order.get("symbol"),
        "side": str(order.get("side") or "").upper(),
        "orderType": str(order.get("type") or "").upper(),
        "algoStatus": str(order.get("status") or "").upper(),
        "triggerPrice": order.get("stopPrice") or order.get("triggerPrice"),
        "positionSide": order.get("info", {}).get("positionSide"),
        "raw": order,
    }


async def fetch_open_algo_orders(exchange: Any, symbol: str, conf: Dict[str, Any],
                                 rest: Any) -> List[Dict[str, Any]]:
    """查询指定交易对的全部未触发条件单（已归一化）。"""
    if supports_algo(exchange):
        market_id = exchange.market(symbol)["id"]
        response = await rest.call(
            exchange.fapiPrivateGetOpenAlgoOrders, {"symbol": market_id},
            priority="NORMAL", conf=conf)
        if isinstance(response, dict):
            return response.get("orders") or response.get("data") or []
        return response or []

    _warn_once()
    orders = await rest.call(
        exchange.fetch_open_orders, symbol, None, None, {"stop": True},
        priority="NORMAL", conf=conf)
    return [_normalize_legacy_order(o) for o in (orders or [])]


async def create_close_position_stop(exchange: Any, symbol: str, side: str,
                                     position_side: str, stop_price: float,
                                     client_id: str, conf: Dict[str, Any],
                                     rest: Any) -> Dict[str, Any]:
    """下达「全平型」STOP_MARKET 灾难止损单（closePosition=True）。"""
    trigger_str = exchange.price_to_precision(symbol, stop_price)
    order_side = "SELL" if side == "long" else "BUY"

    if supports_algo(exchange):
        params = {
            "algoType": "CONDITIONAL", "symbol": exchange.market(symbol)["id"],
            "side": order_side,
            "type": "STOP_MARKET", "positionSide": position_side,
            "triggerPrice": trigger_str,
            "workingType": "MARK_PRICE", "closePosition": "true",
            "clientAlgoId": client_id,
        }
        return await rest.call(exchange.fapiPrivatePostAlgoOrder, params,
                               priority="HIGH", conf=conf)

    _warn_once()
    params = {
        "stopPrice": trigger_str,
        "closePosition": True,
        "workingType": "MARK_PRICE",
        "newClientOrderId": client_id,
    }
    if position_side and position_side != "BOTH":
        params["positionSide"] = position_side
    return await rest.call(
        exchange.create_order, symbol, "STOP_MARKET",
        "sell" if side == "long" else "buy", None, None, params,
        priority="HIGH", conf=conf)


async def cancel_algo_order(exchange: Any, symbol: str, algo_id: Any,
                            conf: Dict[str, Any], rest: Any) -> Any:
    """撤销条件单（Algo 或旧版标准条件单均可）。"""
    if supports_algo(exchange):
        market_id = exchange.market(symbol)["id"]
        return await rest.call(
            exchange.fapiPrivateDeleteAlgoOrder,
            {"symbol": market_id, "algoId": str(algo_id)},
            priority="HIGH", conf=conf)

    _warn_once()
    return await rest.call(exchange.cancel_order, str(algo_id), symbol,
                           priority="HIGH", conf=conf)
