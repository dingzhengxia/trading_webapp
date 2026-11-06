# backend/app/logic/plan_calculator.py
"""自动开仓计划计算（纯函数，无 IO / 无打印）。

规则：
- 币种列表去空白、统一大写、去重、过滤非法值；
- 自定义权重只保留合法币种 + 正权重；权重总和不等于 100 时按比例归一；
- 自定义权重全部非法/为 0 时回退默认分配；
- 默认分配保留 BTC 40% / ETH 30%（同时存在卫星币时）语义，其余均分。
"""
from typing import Any, Dict, List, Tuple

TOTAL_WEIGHT_BASE = 100.0
BTC_DEFAULT_WEIGHT = 0.40
ETH_DEFAULT_WEIGHT = 0.30
BTC_ETH_ONLY_WEIGHT = {'BTC': 0.60, 'ETH': 0.40}


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


def _allocate_by_weights(total_value: float, coins: List[str], weights: Dict[str, float]) -> Dict[str, float]:
    """按权重分配总价值；未分配币种在剩余权重中均分。"""
    if not weights or total_value <= 0:
        return {}

    final_weights: Dict[str, float] = dict(weights)
    assigned_total = sum(weights.values())
    unassigned = [coin for coin in coins if coin not in weights]
    if unassigned and assigned_total < TOTAL_WEIGHT_BASE:
        per_coin = (TOTAL_WEIGHT_BASE - assigned_total) / len(unassigned)
        for coin in unassigned:
            final_weights[coin] = per_coin

    total_weight = sum(final_weights.values())
    if total_weight <= 0:
        return {}
    return {coin: total_value * weight / total_weight for coin, weight in final_weights.items()}


def _default_allocation(total_value: float, coins: List[str]) -> Dict[str, float]:
    """默认分配：BTC 40% + ETH 30%（有卫星币时），仅 BTC+ETH 时 60/40，其余均分。"""
    if total_value <= 0 or not coins:
        return {}

    has_btc = 'BTC' in coins
    has_eth = 'ETH' in coins
    satellite_coins = [coin for coin in coins if coin not in ('BTC', 'ETH')]

    if (has_btc or has_eth) and satellite_coins:
        plan: Dict[str, float] = {}
        remaining_value = total_value
        if has_btc:
            plan['BTC'] = total_value * BTC_DEFAULT_WEIGHT
            remaining_value -= plan['BTC']
        if has_eth:
            plan['ETH'] = total_value * ETH_DEFAULT_WEIGHT
            remaining_value -= plan['ETH']
        value_per_satellite = max(remaining_value, 0.0) / len(satellite_coins)
        for coin in satellite_coins:
            plan[coin] = value_per_satellite
        return plan

    if has_btc and has_eth and not satellite_coins:
        return {
            'BTC': total_value * BTC_ETH_ONLY_WEIGHT['BTC'],
            'ETH': total_value * BTC_ETH_ONLY_WEIGHT['ETH'],
        }

    value_per_coin = total_value / len(coins)
    return {coin: value_per_coin for coin in coins}


def calculate_trade_plan(config: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, float]]:
    """根据配置计算 (long_plan, short_plan)，值为目标 USD 名义价值。"""
    if not isinstance(config, dict):
        return {}, {}

    long_plan: Dict[str, float] = {}
    short_plan: Dict[str, float] = {}

    long_coins = _normalize_coin_list(config.get('long_coin_list'))
    total_long_value = _positive_float(config.get('total_long_position_value'))
    if config.get('enable_long_trades', True) and long_coins and total_long_value > 0:
        custom_weights = _normalize_custom_weights(config.get('long_custom_weights'), set(long_coins))
        long_plan = _allocate_by_weights(total_long_value, long_coins, custom_weights)
        if not long_plan:
            # 自定义权重非法/总为 0：回退默认分配，不再静默返回空计划
            long_plan = _default_allocation(total_long_value, long_coins)

    short_coins = _normalize_coin_list(config.get('short_coin_list'))
    total_short_value = _positive_float(config.get('total_short_position_value'))
    if config.get('enable_short_trades', True) and short_coins and total_short_value > 0:
        value_per_short = total_short_value / len(short_coins)
        short_plan = {coin: value_per_short for coin in short_coins}

    return long_plan, short_plan
