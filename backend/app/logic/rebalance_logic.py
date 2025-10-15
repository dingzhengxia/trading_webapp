# backend/app/logic/rebalance_logic.py (最终版)
from typing import List, Dict, Optional, Any, Tuple
import numpy as np

from ..models.schemas import Position


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

    volume_ma_days = criteria.get('rebalance_volume_ma_days', 20)
    volume_spike_ratio = criteria.get('rebalance_volume_spike_ratio', 3.0)

    pre_filtered_coin_data = []
    for data in coin_data:
        if 'usdt_klines' not in data or len(data['usdt_klines']) < volume_ma_days + 1:
            continue
        volumes = [kline[5] for kline in data['usdt_klines'][-(volume_ma_days + 1):-1]]
        if not volumes:
            continue
        avg_volume = np.mean(volumes)
        latest_volume = data['usdt_klines'][-1][5]
        if avg_volume < 1e-6:
            continue
        if (latest_volume / avg_volume) <= volume_spike_ratio:
            pre_filtered_coin_data.append(data)
        else:
            print(
                f"--- [REBALANCE_FILTER] 剔除币种 {data['symbol']}: 成交量异常放大 ({latest_volume:,.0f} vs 均量 {avg_volume:,.0f}, 超过 {volume_spike_ratio}x) ---")

    filtered_coin_data = [d for d in pre_filtered_coin_data if d['symbol'].upper() not in blacklist_upper]
    if not filtered_coin_data:
        return []

    qualified_coins = []
    abs_days = criteria.get('abs_momentum_days', 30)
    rel_days = criteria.get('rel_strength_days', 60)
    foam_days = criteria.get('foam_days', 1)

    for data in filtered_coin_data:
        coin_info = {'symbol': data['symbol']}
        foam_momentum = calculate_change_percent(data.get('usdt_klines'), foam_days)
        abs_momentum = calculate_change_percent(data.get('usdt_klines'), abs_days)

        if method == 'foam' and foam_momentum is not None:
            coin_info['foam_momentum'] = foam_momentum
            qualified_coins.append(coin_info)
        elif method == 'multi_factor_weakest' and abs_momentum is not None:
            coin_info['abs_momentum'] = abs_momentum

            rel_strengths = {}
            if 'synthetic_klines' in data:
                for bench_coin, klines in data['synthetic_klines'].items():
                    strength = calculate_change_percent(klines, rel_days)
                    if strength is not None:
                        rel_strengths[bench_coin] = strength
            coin_info['rel_strengths'] = rel_strengths

            qualified_coins.append(coin_info)

    if not qualified_coins: return []

    if method == 'foam':
        qualified_coins.sort(key=lambda x: x['foam_momentum'], reverse=True)
    elif method == 'multi_factor_weakest':
        benchmark_coins = criteria.get('rebalance_benchmark_coin', ['BTC'])

        abs_sorted = sorted(qualified_coins, key=lambda x: x['abs_momentum'])
        abs_rank_map = {coin['symbol']: i for i, coin in enumerate(abs_sorted)}

        rel_rank_maps = {}
        for bench_coin in benchmark_coins:
            rel_sorted = sorted(
                [c for c in qualified_coins if bench_coin in c['rel_strengths']],
                key=lambda x: x['rel_strengths'][bench_coin]
            )
            rel_rank_maps[bench_coin] = {coin['symbol']: i for i, coin in enumerate(rel_sorted)}

        for coin in qualified_coins:
            rank_abs = abs_rank_map.get(coin['symbol'], len(qualified_coins))

            rel_ranks = []
            for bench_coin, rank_map in rel_rank_maps.items():
                rank = rank_map.get(coin['symbol'], len(rank_map))
                rel_ranks.append(rank)

            avg_rel_rank = np.mean(rel_ranks) if rel_ranks else len(qualified_coins)

            coin['score'] = rank_abs * 0.6 + avg_rel_rank * 0.4

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


def generate_rebalance_plan(
        current_short_positions: List[Position],
        target_coin_list: List[str],
        target_short_value: float
) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    current_positions_map = {p.symbol: p for p in current_short_positions}
    current_symbols = set(current_positions_map.keys())
    target_symbols = set(target_coin_list)

    close_plan = []
    open_plan = {}

    if not target_symbols:
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
            close_plan.append({
                "symbol": position.symbol,
                "notional": position.notional,
                "close_ratio": 1.0
            })
        else:
            delta = value_per_coin_ideal - position.notional
            if delta < -10:
                close_ratio = min(abs(delta) / position.notional, 1.0)
                close_plan.append({
                    "symbol": position.symbol,
                    "notional": position.notional,
                    "close_ratio": close_ratio
                })
            elif delta > 10:
                open_plan[symbol] = delta

    symbols_to_open_new = target_symbols - current_symbols
    for symbol in symbols_to_open_new:
        open_plan[symbol] = value_per_coin_ideal

    return close_plan, open_plan