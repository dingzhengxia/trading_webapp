# backend/app/logic/rebalance_logic.py (最终完整版)
from typing import List, Dict, Optional, Any, Tuple
import numpy as np
import pandas as pd

from ..models.schemas import Position


def calculate_change_percent(klines: Optional[List], days: int) -> Optional[float]:
    """计算指定天数的价格变化百分比"""
    if days <= 0: return None
    if not klines or len(klines) < days + 1:
        return None

    end_price = klines[-1][4]  # 最新收盘价
    start_price = klines[-1 - days][1]  # N天前的开盘价

    if start_price > 0:
        return ((end_price - start_price) / start_price) * 100
    return 0.0


def calculate_indicators(klines_df: pd.DataFrame, criteria: Dict[str, Any]) -> Dict[str, Any]:
    """为一个币种的K线数据计算所有需要的技术指标"""
    indicators = {}
    close_prices = klines_df['close']

    # 1. RSI
    rsi_period = criteria.get('rebalance_rsi_period', 14)
    if len(close_prices) > rsi_period:
        delta = close_prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
        # 检查 loss.iloc[-1] 是否为 NaN 或 0
        last_loss = loss.iloc[-1]
        if pd.notna(last_loss) and last_loss > 1e-9:
            rs = gain.iloc[-1] / last_loss
            indicators['rsi'] = 100 - (100 / (1 + rs))
        else:
            indicators['rsi'] = 100  # 如果没有下跌，RSI为100

    # 2. Bollinger Bands Width
    bb_period = criteria.get('rebalance_bollinger_period', 20)
    bb_std = criteria.get('rebalance_bollinger_std_dev', 2)
    if len(close_prices) > bb_period:
        sma = close_prices.rolling(window=bb_period).mean()
        std = close_prices.rolling(window=bb_period).std()
        upper_band = sma + (std * bb_std)
        lower_band = sma - (std * bb_std)

        bb_width = ((upper_band - lower_band) / sma) * 100
        if not bb_width.empty and pd.notna(bb_width.iloc[-1]):
            indicators['bb_width'] = bb_width.iloc[-1]
            if len(bb_width.dropna()) >= 5:
                indicators['bb_width_sma'] = bb_width.rolling(window=5).mean().iloc[-1]

    # 3. 短期动量
    short_term_days = criteria.get('rebalance_short_term_momentum_days', 3)
    if len(klines_df) > short_term_days:
        short_term_start_price = klines_df['open'].iloc[-short_term_days]
        short_term_end_price = klines_df['close'].iloc[-1]
        if short_term_start_price > 0:
            indicators['short_term_momentum'] = ((
                                                             short_term_end_price - short_term_start_price) / short_term_start_price) * 100

    return indicators


def screen_coins_advanced(
        coin_data: List[Dict[str, Any]],
        criteria: Dict[str, Any],
        blacklist: List[str]
) -> List[str]:
    method = criteria.get('method')
    top_n = criteria.get('top_n')
    blacklist_upper = [b.upper() for b in blacklist]

    # 步骤1: 应用成交量激增过滤器和黑名单
    volume_spike_ratio = criteria.get('rebalance_volume_spike_ratio', 3.0)
    volume_ma_days = criteria.get('rebalance_volume_ma_days', 20)

    initial_filtered_data = []
    for data in coin_data:
        symbol = data['symbol']
        if symbol.upper() in blacklist_upper:
            continue

        if 'usdt_klines' not in data or len(data['usdt_klines']) < volume_ma_days + 1:
            continue

        df = pd.DataFrame(data['usdt_klines'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        avg_volume = df['volume'].iloc[-(volume_ma_days + 1):-1].mean()
        latest_volume = df['volume'].iloc[-1]

        if avg_volume > 1e-9 and (latest_volume / avg_volume) > volume_spike_ratio:
            print(
                f"--- [REBALANCE_FILTER] 剔除币种 {symbol}: 成交量异常放大 ({latest_volume:,.0f} vs 均量 {avg_volume:,.0f}, 超过 {volume_spike_ratio}x) ---")
            continue

        initial_filtered_data.append(data)

    if not initial_filtered_data:
        return []

    # 步骤2: 计算技术指标并应用防反弹过滤器
    final_filtered_data = []
    enable_filters = criteria.get('enable_rebalance_filters', False)

    for data in initial_filtered_data:
        symbol = data['symbol']

        if 'usdt_klines' not in data or not data['usdt_klines']: continue

        klines_df = pd.DataFrame(data['usdt_klines'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        if klines_df.empty: continue

        indicators = calculate_indicators(klines_df, criteria)
        data.update(indicators)

        if enable_filters:
            rsi_threshold = criteria.get('rebalance_rsi_threshold', 0)
            if 'rsi' in data and pd.notna(data['rsi']) and data['rsi'] < rsi_threshold:
                print(
                    f"--- [REBALANCE_FILTER] 剔除币种 {symbol}: RSI({data['rsi']:.2f}) 过低，低于门槛 {rsi_threshold} ---")
                continue

            short_mom_threshold = criteria.get('rebalance_short_term_momentum_threshold', 100)
            if 'short_term_momentum' in data and pd.notna(data['short_term_momentum']) and data[
                'short_term_momentum'] > short_mom_threshold:
                print(
                    f"--- [REBALANCE_FILTER] 剔除币种 {symbol}: 短期动量({data['short_term_momentum']:.2f}%) 过高，高于门槛 {short_mom_threshold}% ---")
                continue

            bb_spike_ratio = criteria.get('rebalance_bollinger_width_spike_ratio', 100)
            if 'bb_width' in data and 'bb_width_sma' in data and pd.notna(data['bb_width']) and pd.notna(
                    data['bb_width_sma']) and data['bb_width_sma'] > 1e-9:
                current_ratio = data['bb_width'] / data['bb_width_sma']
                if current_ratio > bb_spike_ratio:
                    print(
                        f"--- [REBALANCE_FILTER] 剔除币种 {symbol}: 波动率异常放大({current_ratio:.2f}x)，高于门槛 {bb_spike_ratio}x ---")
                    continue

        final_filtered_data.append(data)

    if not final_filtered_data:
        print("--- [REBALANCE_INFO] 所有通过流动性筛选的币种均被防反弹过滤器剔除。---")
        return []

    # 步骤3: 对通过所有过滤的币种进行评分和排名
    qualified_coins = []
    abs_days = criteria.get('abs_momentum_days', 30)
    rel_days = criteria.get('rel_strength_days', 60)
    foam_days = criteria.get('foam_days', 1)

    for data in final_filtered_data:
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

    # 步骤4: 最终排序
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

    value_per_coin_ideal = target_short_value / len(target_symbols) if target_symbols else 0

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