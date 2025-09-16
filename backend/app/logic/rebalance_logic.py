# backend/app/logic/rebalance_logic.py (完整修复版)
from typing import List, Dict, Optional, Any, Tuple

from ..models.schemas import Position  # 导入 Pydantic 模型


def calculate_change_percent(klines: Optional[List], days: int) -> Optional[float]:
    if days <= 0: return None
    if not klines or len(klines) < days + 1:
        return None

    end_price = klines[-1][4]
    start_price = klines[-1 - days][1]

    if start_price > 0:
        return ((end_price - start_price) / start_price) * 100
    return 0.0


def screen_coins_advanced(
        coin_data: List[Dict[str, Any]],
        criteria: Dict[str, Any],
        blacklist: List[str]
) -> List[str]:
    method = criteria.get('method')
    top_n = criteria.get('top_n')
    blacklist_upper = [b.upper() for b in blacklist]

    filtered_coin_data = [d for d in coin_data if d['symbol'].upper() not in blacklist_upper]

    qualified_coins = []
    abs_days = criteria.get('abs_momentum_days', 30)
    rel_days = criteria.get('rel_strength_days', 60)
    foam_days = criteria.get('foam_days', 1)

    for data in filtered_coin_data:
        coin_info = {'symbol': data['symbol']}
        foam_momentum = calculate_change_percent(data.get('usdt_klines'), foam_days)
        abs_momentum = calculate_change_percent(data.get('usdt_klines'), abs_days)
        rel_strength = calculate_change_percent(data.get('btc_klines'), rel_days)

        if method == 'foam' and foam_momentum is not None:
            coin_info['foam_momentum'] = foam_momentum
            qualified_coins.append(coin_info)
        elif method == 'multi_factor_weakest' and abs_momentum is not None:
            coin_info['abs_momentum'] = abs_momentum
            coin_info['rel_strength'] = rel_strength if rel_strength is not None else abs_momentum
            qualified_coins.append(coin_info)

    if not qualified_coins: return []

    if method == 'foam':
        qualified_coins.sort(key=lambda x: x['foam_momentum'], reverse=True)
    elif method == 'multi_factor_weakest':
        qualified_coins.sort(key=lambda x: x['abs_momentum'])
        for i, coin in enumerate(qualified_coins): coin['rank_abs'] = i

        qualified_coins.sort(key=lambda x: x['rel_strength'])
        for i, coin in enumerate(qualified_coins): coin['rank_rel'] = i

        for coin in qualified_coins: coin['score'] = coin['rank_abs'] * 0.6 + coin['rank_rel'] * 0.4
        qualified_coins.sort(key=lambda x: x['score'])
    else:
        return []

    return [coin['symbol'] for coin in qualified_coins[:top_n]]


def calculate_target_ratio_by_alt_index(alt_index: float, config: dict) -> float:
    max_ratio = config.get('rebalance_short_ratio_max', 0.70)
    min_ratio = config.get('rebalance_short_ratio_min', 0.35)
    index_normalized = alt_index / 100.0
    target_ratio = max_ratio - (index_normalized * (max_ratio - min_ratio))
    return max(min_ratio, min(max_ratio, target_ratio))


# --- 核心修复 ---
def generate_rebalance_plan(
        current_short_positions: List[Position],
        target_coin_list: List[str],
        target_short_value: float
) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    """
    不再修改 Position 对象，而是返回一个包含平仓信息的字典列表。
    """
    current_positions_map = {p.symbol: p for p in current_short_positions}
    current_symbols = set(current_positions_map.keys())
    target_symbols = set(target_coin_list)

    close_plan = []  # 返回一个字典列表
    open_plan = {}

    if not target_symbols:
        # 如果目标列表为空，则计划平掉所有现有空头仓位
        for position in current_short_positions:
            close_plan.append({
                "symbol": position.symbol,
                "notional": position.notional,
                "close_ratio": 1.0
            })
        return close_plan, {}

    value_per_coin_ideal = target_short_value / len(target_symbols)

    for symbol, position in current_positions_map.items():
        if symbol not in target_symbols:
            # 计划完全平仓
            close_plan.append({
                "symbol": position.symbol,
                "notional": position.notional,
                "close_ratio": 1.0
            })
        else:
            delta = value_per_coin_ideal - position.notional
            if delta < -10:  # 需要减仓
                close_ratio = min(abs(delta) / position.notional, 1.0)
                close_plan.append({
                    "symbol": position.symbol,
                    "notional": position.notional,
                    "close_ratio": close_ratio
                })
            elif delta > 10:  # 需要加仓
                open_plan[symbol] = delta

    symbols_to_open_new = target_symbols - current_symbols
    for symbol in symbols_to_open_new:
        open_plan[symbol] = value_per_coin_ideal

    return close_plan, open_plan
# --- 修复结束 ---