# backend/app/logic/plan_calculator.py
"""自动开仓计划计算（纯函数，无 IO / 无打印）。

分配口径（只有一套，不存在隐藏默认值）：
- 币种列表去空白、统一大写、去重、过滤非法值；
- 权重与币种清单**一同保存**（POST /api/settings 一次请求内对齐），默认均分；
- 权重只对「当前清单里的币」生效：清单外的键直接丢弃，清单内的新币按剩余比例均分；
- 权重总和不等于 100 时按比例归一，并归整到两位小数、尾差并入最后一项；
- 因此「没设过权重」和「权重全部失效」都等于均分。

历史教训（2026-11-15）：旧实现没设权重时按 BTC 40% / ETH 30% 分配，权重又按币名
单独存、换清单不同步，于是「我设的是均分，BTC 却拿了 40%」。默认值必须只有一个：均分。
"""
from typing import Any, Dict, List, Tuple

TOTAL_WEIGHT_BASE = 100.0


def _normalize_coin_list(coins: Any) -> List[str]:
    if not isinstance(coins, (list, tuple, set)):
        return []
    normalized: List[str] = []
    seen = set()
    for coin in coins:
        if not isinstance(coin, str):
            continue
        symbol = coin.strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        normalized.append(symbol)
    return normalized


def _positive_float(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    if result != result or result in (float('inf'), float('-inf')):
        return 0.0
    return result if result > 0 else 0.0


def _normalize_custom_weights(weights: Any, coin_set: set) -> Dict[str, float]:
    """过滤非法币种/非法权重，合并重复并统一大写。"""
    result: Dict[str, float] = {}
    if not isinstance(weights, dict):
        return result
    for coin, weight in weights.items():
        if not isinstance(coin, str):
            continue
        symbol = coin.strip().upper()
        if symbol not in coin_set:
            continue
        value = _positive_float(weight)
        if value <= 0:
            continue
        result[symbol] = result.get(symbol, 0.0) + value
    return result


def _spread_evenly(coins: List[str]) -> Dict[str, float]:
    """把 100% 均分到各币，两位小数，尾差并入最后一项（合计正好 100）。"""
    if not coins:
        return {}
    per_coin = round(TOTAL_WEIGHT_BASE / len(coins), 2)
    result: Dict[str, float] = {}
    accumulated = 0.0
    for index, coin in enumerate(coins):
        value = round(TOTAL_WEIGHT_BASE - accumulated, 2) if index == len(coins) - 1 else per_coin
        result[coin] = value
        accumulated = round(accumulated + value, 2)
    return result


def reconcile_weights(coins: Any, weights: Any) -> Dict[str, float]:
    """把权重对齐到币种清单：键集合 = 清单，合计 = 100。

    保存设置与计算计划共用这一个函数，保证「界面看到的」=「存进去的」=「下单用的」。
    - 没有可用权重（没设过 / 全部对不上清单）→ 均分；
    - 只覆盖部分币种 → 剩余比例由未覆盖的币均分（已分配已达 100 时按均值参与）；
    - 清单外的键一律丢弃，不会留给下一套清单造成串味。
    """
    ordered = _normalize_coin_list(coins)
    if not ordered:
        return {}

    saved = _normalize_custom_weights(weights, set(ordered))
    if not saved:
        return _spread_evenly(ordered)

    missing = [coin for coin in ordered if coin not in saved]
    if missing:
        assigned = sum(saved.values())
        if assigned < TOTAL_WEIGHT_BASE:
            share = (TOTAL_WEIGHT_BASE - assigned) / len(missing)
        else:
            # 只给 BTC/ETH 设了 50/50、之后又把 BNB 加进清单：按已分配权重的均值
            # 参与分配，否则新币权重为 0 会直接从计划里消失。
            share = assigned / len(saved)
        for coin in missing:
            saved[coin] = share

    total = sum(saved.values())
    if total <= 0:
        return _spread_evenly(ordered)

    result: Dict[str, float] = {}
    accumulated = 0.0
    last_index = len(ordered) - 1
    for index, coin in enumerate(ordered):
        if index == last_index:
            value = round(TOTAL_WEIGHT_BASE - accumulated, 2)
        else:
            value = round(saved[coin] * TOTAL_WEIGHT_BASE / total, 2)
        if value <= 0:
            # 币种极多时两位小数的累计误差可能吃光最后一项，整体退回均分
            return _spread_evenly(ordered)
        result[coin] = value
        accumulated = round(accumulated + value, 2)
    return result


def calculate_trade_plan(config: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, float]]:
    """根据配置计算 (long_plan, short_plan)，值为目标 USD 名义价值。"""
    if not isinstance(config, dict):
        return {}, {}

    long_plan: Dict[str, float] = {}
    short_plan: Dict[str, float] = {}

    long_coins = _normalize_coin_list(config.get('long_coin_list'))
    total_long_value = _positive_float(config.get('total_long_position_value'))
    if config.get('enable_long_trades', True) and long_coins and total_long_value > 0:
        weights = reconcile_weights(long_coins, config.get('long_custom_weights'))
        total_weight = sum(weights.values())
        if total_weight > 0:
            # 按权重拆分，并把两位小数带来的尾差并入最后一个币：
            # 合计始终等于用户填的总价值（否则日志里会出现「合计 2999.9」这种数）。
            items = [(coin, weight) for coin, weight in weights.items() if weight > 0]
            accumulated = 0.0
            for index, (coin, weight) in enumerate(items):
                if index == len(items) - 1:
                    value = max(total_long_value - accumulated, 0.0)
                else:
                    value = total_long_value * weight / total_weight
                    accumulated += value
                long_plan[coin] = value

    short_coins = _normalize_coin_list(config.get('short_coin_list'))
    total_short_value = _positive_float(config.get('total_short_position_value'))
    if config.get('enable_short_trades', True) and short_coins and total_short_value > 0:
        value_per_short = total_short_value / len(short_coins)
        short_plan = {coin: value_per_short for coin in short_coins}

    return long_plan, short_plan
