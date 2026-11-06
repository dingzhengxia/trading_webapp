# backend/app/logic/rebalance_logic.py
import logging
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from ..models.schemas import Position

logger = logging.getLogger(__name__)

SUPPORTED_REBALANCE_METHODS = ('multi_factor_weakest',)


def validate_rebalance_method(method: Any) -> str:
    """校验再平衡策略：当前只实现了 multi_factor_weakest。"""
    normalized = str(method or '').strip().lower()
    if normalized not in SUPPORTED_REBALANCE_METHODS:
        raise ValueError(f"不支持的再平衡策略: {method}，当前仅支持 multi_factor_weakest。")
    return normalized


def create_synthetic_benchmark(benchmark_klines: Dict[str, List], benchmark_weights: Dict[str, float]) -> pd.DataFrame:
    """根据多个基准币种及其权重，创建一个合成基准指数的 DataFrame。"""
    benchmark_dfs = {}
    common_timestamps = None
    for symbol, klines in benchmark_klines.items():
        if not klines:
            continue
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.set_index('timestamp')
        benchmark_dfs[symbol] = df['close']
        if common_timestamps is None:
            common_timestamps = set(df.index)
        else:
            common_timestamps &= set(df.index)

    if not common_timestamps or not benchmark_dfs:
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
    """计算一个币种相对于基准的超额/亏损回报率 (Alpha Spread)。"""
    if len(coin_close) < days + 1 or len(benchmark_close) < days + 1:
        return None

    df = pd.concat([coin_close, benchmark_close], axis=1, join='inner').tail(days + 1)
    if len(df) < days + 1:
        return None

    coin_return = (df.iloc[-1, 0] / df.iloc[0, 0]) - 1 if df.iloc[0, 0] > 0 else 0
    benchmark_return = (df.iloc[-1, 1] / df.iloc[0, 1]) - 1 if df.iloc[0, 1] > 0 else 0

    return float((coin_return - benchmark_return) * 100)


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(result):
        return default
    return result


def calculate_indicators_for_filtering(klines_df: pd.DataFrame, criteria: Dict[str, Any]) -> Dict[str, float]:
    """计算用于防反弹过滤的技术指标，空数据/数据不足时安全返回。"""
    indicators: Dict[str, float] = {}
    if klines_df is None or len(klines_df) == 0 or 'close' not in klines_df:
        return indicators

    close_prices = klines_df['close'].astype(float)

    # --- RSI ---
    rsi_period = int(_safe_float(criteria.get('rebalance_rsi_period'), 14) or 14)
    if rsi_period > 0 and len(close_prices) > rsi_period:
        delta = close_prices.diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=rsi_period).mean()
        avg_gain = gain.iloc[-1]
        avg_loss = loss.iloc[-1]
        if pd.notna(avg_gain) and pd.notna(avg_loss):
            if avg_loss > 1e-9:
                rs = avg_gain / avg_loss
                indicators['rsi'] = float(100 - (100 / (1 + rs)))
            elif avg_gain > 0:
                indicators['rsi'] = 100.0
            else:
                indicators['rsi'] = 50.0

    # --- 短期动量 ---
    short_term_days = int(_safe_float(criteria.get('rebalance_short_term_momentum_days'), 3) or 3)
    if short_term_days > 0 and len(klines_df) > short_term_days and 'open' in klines_df:
        start_price = float(klines_df['open'].astype(float).iloc[-short_term_days])
        end_price = float(close_prices.iloc[-1])
        if start_price > 0:
            indicators['short_term_momentum'] = (end_price - start_price) / start_price * 100

    # --- 布林带宽度放大过滤 ---
    bollinger_period = int(_safe_float(criteria.get('rebalance_bollinger_period'), 20) or 20)
    bollinger_std = _safe_float(criteria.get('rebalance_bollinger_std_dev'), 2.0) or 2.0
    if bollinger_period > 1 and len(close_prices) >= bollinger_period:
        middle = close_prices.rolling(window=bollinger_period).mean()
        std = close_prices.rolling(window=bollinger_period).std()
        bandwidth = (2 * bollinger_std * std) / middle.replace(0, np.nan)
        valid_bandwidth = bandwidth.dropna()
        if len(valid_bandwidth) >= 2:
            current_width = float(valid_bandwidth.iloc[-1])
            average_width = float(valid_bandwidth.iloc[:-1].mean())
            if average_width > 1e-12 and np.isfinite(current_width):
                indicators['bollinger_width_ratio'] = current_width / average_width

    # --- 成交量放大过滤 ---
    volume_ma_days = int(_safe_float(criteria.get('rebalance_volume_ma_days'), 20) or 20)
    if volume_ma_days > 1 and 'volume' in klines_df and len(klines_df) > volume_ma_days:
        volumes = klines_df['volume'].astype(float)
        volume_ma = volumes.rolling(window=volume_ma_days).mean()
        current_volume = float(volumes.iloc[-1])
        average_volume = volume_ma.iloc[-1]
        if pd.notna(average_volume) and average_volume > 0 and np.isfinite(current_volume):
            indicators['volume_spike_ratio'] = current_volume / float(average_volume)

    return indicators


def screen_coins_based_on_relative_weakness(
        candidate_klines: Dict[str, List],
        benchmark_klines: Dict[str, List],
        criteria: Dict[str, Any],
        blacklist: List[str]
) -> List[str]:
    """整合防反弹过滤和相对弱势评分的最终筛选函数。"""
    top_n = int(_safe_float(criteria.get('top_n'), 10) or 10)
    blacklist_upper = {str(b).upper() for b in (blacklist or [])}

    # --- 阶段1: 防反弹过滤 ---
    filtered_klines: Dict[str, List] = {}
    enable_filters = bool(criteria.get('enable_rebalance_filters', False))

    rsi_threshold = _safe_float(criteria.get('rebalance_rsi_threshold'), 0.0) or 0.0
    short_mom_threshold = _safe_float(criteria.get('rebalance_short_term_momentum_threshold'), 100.0) or 0.0
    width_spike_ratio = _safe_float(criteria.get('rebalance_bollinger_width_spike_ratio'), 2.0) or 2.0
    volume_spike_ratio = _safe_float(criteria.get('rebalance_volume_spike_ratio'), 3.0) or 3.0

    for symbol, klines in candidate_klines.items():
        if str(symbol).upper() in blacklist_upper or symbol in benchmark_klines or not klines:
            continue

        klines_df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        if enable_filters:
            indexed_df = klines_df.set_index(pd.to_datetime(klines_df['timestamp'], unit='ms'))
            indicators = calculate_indicators_for_filtering(indexed_df, criteria)

            if 'rsi' in indicators and indicators['rsi'] < rsi_threshold:
                logger.info("剔除 %s: RSI(%.2f) < %.2f", symbol, indicators['rsi'], rsi_threshold)
                continue

            if 'short_term_momentum' in indicators and indicators['short_term_momentum'] > short_mom_threshold:
                logger.info("剔除 %s: 短期动量(%.2f%%) > %.2f%%",
                            symbol, indicators['short_term_momentum'], short_mom_threshold)
                continue

            if 'bollinger_width_ratio' in indicators and indicators['bollinger_width_ratio'] > width_spike_ratio:
                logger.info("剔除 %s: 布林带宽度放大(%.2f) > %.2f",
                            symbol, indicators['bollinger_width_ratio'], width_spike_ratio)
                continue

            if 'volume_spike_ratio' in indicators and indicators['volume_spike_ratio'] > volume_spike_ratio:
                logger.info("剔除 %s: 成交量放大(%.2f) > %.2f",
                            symbol, indicators['volume_spike_ratio'], volume_spike_ratio)
                continue

        filtered_klines[symbol] = klines

    logger.info("经过防反弹过滤后，剩余 %d 个候选币种。", len(filtered_klines))
    if not filtered_klines:
        return []

    # --- 阶段2: 相对弱势评分 ---
    benchmark_weights = {s: 1.0 for s in benchmark_klines.keys()}
    synthetic_benchmark_df = create_synthetic_benchmark(benchmark_klines, benchmark_weights)

    if synthetic_benchmark_df.empty:
        logger.warning("无法创建合成基准指数，筛选中止。")
        return []

    qualified_coins = []
    abs_days = int(_safe_float(criteria.get('abs_momentum_days'), 21) or 21)
    rel_days = int(_safe_float(criteria.get('rel_strength_days'), 21) or 21)

    for symbol, klines in filtered_klines.items():
        coin_df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        coin_df['timestamp'] = pd.to_datetime(coin_df['timestamp'], unit='ms')
        coin_df = coin_df.set_index('timestamp')

        abs_momentum = calculate_relative_performance(coin_df['close'], pd.Series(1.0, index=coin_df.index), abs_days)
        relative_performance = calculate_relative_performance(
            coin_df['close'], synthetic_benchmark_df['close'], rel_days)

        if relative_performance is None or abs_momentum is None:
            continue

        score = (relative_performance * 0.7) + (abs_momentum * 0.3)
        qualified_coins.append({'symbol': symbol, 'score': score})

    if not qualified_coins:
        return []

    qualified_coins.sort(key=lambda x: x['score'])
    return [coin['symbol'] for coin in qualified_coins[:top_n]]


# --- 辅助函数 ---
def calculate_target_ratio_by_alt_index(alt_index: float, config: dict) -> float:
    max_ratio = _safe_float(config.get('rebalance_short_ratio_max'), 0.70) or 0.70
    min_ratio = _safe_float(config.get('rebalance_short_ratio_min'), 0.35) or 0.35
    index_normalized = float(alt_index) / 100.0
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
            if position.notional <= 0:
                continue
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
