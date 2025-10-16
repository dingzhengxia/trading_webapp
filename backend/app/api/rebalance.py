# backend/app/api/rebalance.py (最终完整正确版)
import asyncio
from typing import List, Dict, Any

import ccxt.async_support as ccxt
from fastapi import APIRouter, Depends, BackgroundTasks

from ..config.config import AVAILABLE_LONG_COINS, STABLECOIN_PREFERENCE, AVAILABLE_SHORT_COINS
from ..core.dependencies import get_settings_dependency
from ..core.exchange_manager import get_exchange_dependency
from ..core.security import verify_api_key
from ..core.trading_service import trading_service
from ..core.websocket_manager import log_message
from ..logic import exchange_logic_async as ex_async
from ..logic import rebalance_logic
from ..models.schemas import RebalanceCriteria, RebalancePlanResponse, ExecutionPlanRequest

router = APIRouter(prefix="/api/rebalance", tags=["Rebalance"], dependencies=[Depends(verify_api_key)])


async def screen_coins_task(exchange: ccxt.binanceusdm, criteria: RebalanceCriteria, settings: Dict[str, Any]) -> List[
    str]:
    await log_message(f"开始筛选，策略: {criteria.method}, 目标数量: {criteria.top_n}", "info")

    short_pool = set(AVAILABLE_SHORT_COINS)
    if not short_pool:
        raise ValueError("做空币种备选池为空，无法进行智能再平衡筛选。请先在'币种列表管理'中配置。")
    await log_message(f"将使用您配置的 {len(short_pool)} 个币种的做空备选池进行筛选。", "info")

    await log_message("正在获取全市场行情以进行流动性筛选...", "info")
    all_tickers = await exchange.fetch_tickers()

    stablecoins = set(STABLECOIN_PREFERENCE)
    liquid_coins_symbols = []
    processed_bases = set()

    for symbol, ticker in all_tickers.items():
        if '/' not in symbol: continue
        base, quote = symbol.split('/')[:2]
        quote = quote.split(':')[0]
        if base in processed_bases: continue

        if (quote in stablecoins and
                base in short_pool and
                ticker.get('quoteVolume', 0) is not None and
                ticker['quoteVolume'] > criteria.min_volume_usd):
            liquid_coins_symbols.append(base)
            processed_bases.add(base)

    if not liquid_coins_symbols:
        raise ValueError("您选择的做空币种中，没有币种通过流动性筛选。请检查或降低交易额门槛。")
    await log_message(f"通过流动性筛选的币种数量: {len(liquid_coins_symbols)}", "info")

    # --- 核心逻辑修改：统一获取所有需要的K线 ---
    days_to_fetch = max(
        criteria.abs_momentum_days,
        criteria.rel_strength_days,
        criteria.rebalance_volume_ma_days,
        criteria.rebalance_rsi_period,
        criteria.rebalance_bollinger_period,
        criteria.rebalance_short_term_momentum_days,
        2
    )
    fetch_limit = days_to_fetch + 30

    benchmark_coins = set(criteria.rebalance_benchmark_coin)
    if not benchmark_coins:
        raise ValueError("多因子策略需要至少指定一个基准币种 (如 BTC)。")

    symbols_to_fetch = list(set(liquid_coins_symbols) | benchmark_coins)
    await log_message(f"准备并发获取 {len(symbols_to_fetch)} 个币种过去 {fetch_limit} 天的K线...", "info")

    CONCURRENT_REQUESTS = 20
    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)

    async def fetch_kline_with_semaphore(symbol):
        async with semaphore:
            full_symbol = ex_async.resolve_full_symbol(exchange, symbol)
            if full_symbol:
                return symbol, await ex_async.fetch_klines_async(exchange, full_symbol, '1d', fetch_limit)
            return symbol, None

    fetch_tasks = [fetch_kline_with_semaphore(s) for s in symbols_to_fetch]
    results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    all_klines_map = {}
    for res in results:
        if isinstance(res, tuple) and res[1] is not None and len(res[1]) >= days_to_fetch:
            symbol, klines = res
            all_klines_map[symbol] = klines

    if not all_klines_map:
        raise ValueError("未能成功获取任何币种的K线数据。")

    benchmark_klines = {s: all_klines_map[s] for s in benchmark_coins if s in all_klines_map}
    if len(benchmark_klines) != len(benchmark_coins):
        missing = benchmark_coins - set(benchmark_klines.keys())
        raise ValueError(f"获取部分基准币种K线失败: {', '.join(missing)}")

    candidate_klines = {s: all_klines_map[s] for s in liquid_coins_symbols if s in all_klines_map}

    if not candidate_klines:
        raise ValueError("成功获取K线数据的候选币种为0，无法进行下一步计算。")
    await log_message(
        f"成功获取并处理了 {len(candidate_klines)} 个候选币种和 {len(benchmark_klines)} 个基准币种的K线数据。", "info")

    loop = asyncio.get_running_loop()
    target_coin_list = await loop.run_in_executor(
        None,
        rebalance_logic.screen_coins_based_on_relative_weakness,
        candidate_klines,
        benchmark_klines,
        criteria.model_dump(),
        AVAILABLE_LONG_COINS
    )

    return target_coin_list


@router.post("/plan", response_model=RebalancePlanResponse)
async def generate_rebalance_plan(
        criteria: RebalanceCriteria,
        exchange: ccxt.binanceusdm = Depends(get_exchange_dependency),
        config: Dict[str, Any] = Depends(get_settings_dependency)
):
    print("--- 📢 API HIT: /api/rebalance/plan ---")

    positions_task = ex_async.fetch_positions_with_pnl_async(exchange, config.get('leverage', 1))
    screening_task = screen_coins_task(exchange, criteria, config)

    all_positions, target_coin_list = await asyncio.gather(positions_task, screening_task)

    await log_message(f"筛选完成，最终选出 {len(target_coin_list)} 个目标币种。", "success")

    long_positions = [p for p in all_positions if p.side == 'long']
    current_short_positions = [p for p in all_positions if p.side == 'short']
    current_long_value = sum(p.notional for p in long_positions)

    if current_long_value <= 0:
        raise ValueError("多头仓位价值为零，无法再平衡。")

    if criteria.manual_target_ratio_perc is not None:
        await log_message(f"使用手动设置的目标比例: {criteria.manual_target_ratio_perc:.1f}%", "info")
        target_ratio = criteria.manual_target_ratio_perc / 100.0
    else:
        alt_season_index = 50
        target_ratio = rebalance_logic.calculate_target_ratio_by_alt_index(alt_season_index, config)

    target_short_value = current_long_value * target_ratio

    await log_message(
        f"当前多头价值: ${current_long_value:,.2f}, 目标空头比例: {target_ratio:.1%}, 目标空头总价值: ${target_short_value:,.2f}",
        "info")

    close_plan_data, open_plan_data = rebalance_logic.generate_rebalance_plan(
        current_short_positions, target_coin_list, target_short_value
    )

    close_plan_formatted = [
        {
            "symbol": p_info["symbol"],
            "notional": p_info["notional"],
            "close_value": p_info["notional"] * p_info["close_ratio"],
            "close_ratio_perc": p_info["close_ratio"] * 100
        } for p_info in close_plan_data
    ]

    open_plan_formatted = []
    if target_coin_list:
        value_per_coin_ideal = target_short_value / len(target_coin_list)
        for symbol, value in open_plan_data.items():
            percentage = (value / value_per_coin_ideal) * 100 if value_per_coin_ideal > 0.01 else 100
            open_plan_formatted.append({
                "symbol": symbol,
                "open_value": value,
                "percentage": percentage
            })

    return RebalancePlanResponse(
        target_ratio_perc=target_ratio * 100,
        positions_to_close=close_plan_formatted,
        positions_to_open=open_plan_formatted,
        target_coin_list=target_coin_list
    )


@router.post("/execute")
def execute_rebalance_plan(plan: ExecutionPlanRequest, background_tasks: BackgroundTasks):
    print("--- 📢 API HIT: /api/rebalance/execute ---")
    return trading_service.execute_rebalance_plan(plan, background_tasks)