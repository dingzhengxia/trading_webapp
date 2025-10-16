# backend/app/logic/rebalance_logic.py (最终整合版)
from typing import List, Dict, Any, Tuple
import numpy as np
import pandas as pd

from ..models.schemas import Position


def create_synthetic_benchmark(benchmark_klines: Dict[str, List], benchmark_weights: Dict[str, float]) -> pd.DataFrame:
    """
    根据多个基准币种及其权重，创建一个合成基准指数的DataFrame。
    """
    benchmark_dfs = {}
    common_timestamps = None
    for symbol, klines in benchmark_klines.items():
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.set_index('timestamp')
        benchmark_dfs[symbol] = df['close']
        if common_timestamps is None:
            common_timestamps = set(df.index)
        else:
            common_timestamps &= set(df.index)

    if not common_timestamps:
        return pd.DataFrame()

    common_timestamps = sorted(list(common_timestamps))

    total_weight = sum(benchmark_weights.values())
    if total_weight == 0:
        num_benchmarks = len(benchmark_dfs)
        weights = {s: 1.0 / num_benchmarks for s in benchmark_dfs.keys()} if num_benchmarks > 0 else {}
    else:
        weights = {s: w / total_weight for s, w in benchmark_weights.items()}

    synthetic_index = pd.Series(0.0, index=common_timestamps)
    for symbol, close_prices in benchmark_dfs.items():
        synthetic_index += close_prices.reindex(common_timestamps, method='ffill') * weights.get(symbol, 0)

    return synthetic_index.to_frame(name='close')


def calculate_relative_performance(coin_close: pd.Series, benchmark_close: pd.Series, days: int) -> float | None:
    """
    计算一个币种相对于基准的超额/亏损回报率 (Alpha Spread)。
    """
    if len(coin_close) < days + 1 or len(benchmark_close) < days + 1:
        return None

    df = pd.concat([coin_close, benchmark_close], axis=1, join='inner').tail(days + 1)
    if len(df) < days + 1:
        return None

    coin_return = (df.iloc[-1, 0] / df.iloc[0, 0]) - 1 if df.iloc[0, 0] > 0 else 0
    benchmark_return = (df.iloc[-1, 1] / df.iloc[0, 1]) - 1 if df.iloc[0, 1] > 0 else 0

    return (coin_return - benchmark_return) * 100


def calculate_indicators_for_filtering(klines_df: pd.DataFrame, criteria: Dict[str, Any]) -> Dict[str, Any]:
    """计算用于防反弹过滤的技术指标"""
    indicators = {}
    close_prices = klines_df['close']

    rsi_period = criteria.get('rebalance_rsi_period', 14)
    if len(close_prices) > rsi_period:
        delta = close_prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
        rs = gain.iloc[-1] / loss.iloc[-1] if loss.iloc[-1] > 1e-9 else float('inf')
        indicators['rsi'] = 100 - (100 / (1 + rs))

    short_term_days = criteria.get('rebalance_short_term_momentum_days', 3)
    if len(klines_df) > short_term_days:
        start_price = klines_df['open'].iloc[-short_term_days]
        end_price = klines_df['close'].iloc[-1]
        if start_price > 0:
            indicators['short_term_momentum'] = ((end_price - start_price) / start_price) * 100

    return indicators


def screen_coins_based_on_relative_weakness(
        candidate_klines: Dict[str, List],
        benchmark_klines: Dict[str, List],
        criteria: Dict[str, Any],
        blacklist: List[str]
) -> List[str]:
    """
    整合了防反弹过滤和相对弱势评分的最终筛选函数。
    """
    top_n = criteria.get('top_n')
    blacklist_upper = set(b.upper() for b in blacklist)

    # --- 阶段1: 防反弹过滤 ---
    filtered_klines = {}
    enable_filters = criteria.get('enable_rebalance_filters', False)

    for symbol, klines in candidate_klines.items():
        if symbol.upper() in blacklist_upper or symbol in benchmark_klines:
            continue

        klines_df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        if enable_filters:
            indicators = calculate_indicators_for_filtering(
                klines_df.set_index(pd.to_datetime(klines_df['timestamp'], unit='ms')), criteria)

            rsi_threshold = criteria.get('rebalance_rsi_threshold', 0)
            if 'rsi' in indicators and indicators['rsi'] < rsi_threshold:
                print(f"--- [REBALANCE_FILTER] 剔除 {symbol}: RSI({indicators['rsi']:.2f}) < {rsi_threshold} ---")
                continue

            short_mom_threshold = criteria.get('rebalance_short_term_momentum_threshold', 100)
            if 'short_term_momentum' in indicators and indicators['short_term_momentum'] > short_mom_threshold:
                print(
                    f"--- [REBALANCE_FILTER] 剔除 {symbol}: 短期动量({indicators['short_term_momentum']:.2f}%) > {short_mom_threshold}% ---")
                continue

        filtered_klines[symbol] = klines

    print(f"--- [REBALANCE_INFO] 经过防反弹过滤后，剩余 {len(filtered_klines)} 个候选币种。")
    if not filtered_klines:
        return []

    # --- 阶段2: 相对弱势评分 ---
    benchmark_weights = {s: 1.0 for s in benchmark_klines.keys()}
    synthetic_benchmark_df = create_synthetic_benchmark(benchmark_klines, benchmark_weights)

    if synthetic_benchmark_df.empty:
        print("--- [REBALANCE_ERROR] 无法创建合成基准指数，筛选中止。")
        return []

    qualified_coins = []
    abs_days = criteria.get('abs_momentum_days', 21)
    rel_days = criteria.get('rel_strength_days', 21)

    for symbol, klines in filtered_klines.items():
        coin_df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        coin_df['timestamp'] = pd.to_datetime(coin_df['timestamp'], unit='ms')
        coin_df = coin_df.set_index('timestamp')

        abs_momentum = calculate_relative_performance(coin_df['close'], pd.Series(1.0, index=coin_df.index), abs_days)
        relative_performance = calculate_relative_performance(coin_df['close'], synthetic_benchmark_df['close'],
                                                              rel_days)

        if relative_performance is None or abs_momentum is None:
            continue

        score = (relative_performance * 0.7) + (abs_momentum * 0.3)
        qualified_coins.append({'symbol': symbol, 'score': score})

    if not qualified_coins:
        return []

    qualified_coins.sort(key=lambda x: x['score'])

    print("--- [REBALANCE] Top 10 Weakest Coins (Score): ---")
    for coin in qualified_coins[:10]:
        print(f"  - {coin['symbol']}: {coin['score']:.2f}")
    print("-------------------------------------------------")

    return [coin['symbol'] for coin in qualified_coins[:top_n]]


# --- 辅助函数 ---
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
            close_plan.append({"symbol": position.symbol, "notional": position.notional, "close_ratio": 1.0})
        return close_plan, {}
    value_per_coin_ideal = target_short_value / len(target_symbols)
    for symbol, position in current_positions_map.items():
        if symbol not in target_symbols:
            close_plan.append({"symbol": position.symbol, "notional": position.notional, "close_ratio": 1.0})
        else:
            delta = value_per_coin_ideal - position.notional
            if delta < -10:
                close_ratio = min(abs(delta) / position.notional, 1.0)
                close_plan.append(
                    {"symbol": position.symbol, "notional": position.notional, "close_ratio": close_ratio})
            elif delta > 10:
                open_plan[symbol] = delta
    symbols_to_open_new = target_symbols - current_symbols
    for symbol in symbols_to_open_new:
        open_plan[symbol] = value_per_coin_ideal
    return close_plan, open_plan