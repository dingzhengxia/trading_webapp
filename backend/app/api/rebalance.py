# backend/app/api/rebalance.py (最终正确版)
import asyncio
from typing import List, Dict, Any

import ccxt.async_support as ccxt
from fastapi import APIRouter, Depends, BackgroundTasks

from ..config.config import AVAILABLE_LONG_COINS, STABLECOIN_PREFERENCE
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

    short_pool = set(settings.get('short_coin_list', []))
    if not short_pool:
        raise ValueError("做空交易列表为空，无法进行智能再平衡筛选。请先在'通用开仓设置'中配置。")
    await log_message(f"将使用您配置的 {len(short_pool)} 个币种的做空列表进行筛选。", "info")

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

    volume_ma_days = criteria.rebalance_volume_ma_days
    days_to_fetch = max(
        criteria.abs_momentum_days,
        criteria.rel_strength_days,
        criteria.foam_days,
        volume_ma_days,
        2
    )
    fetch_limit = days_to_fetch + 2
    await log_message(f"准备并发获取 {len(liquid_coins_symbols)} 个币种过去 {fetch_limit} 天的K线...", "info")

    kline_tasks = []
    valid_symbols_for_kline = []
    for symbol in liquid_coins_symbols:
        full_usdt_symbol = ex_async.resolve_full_symbol(exchange, symbol)
        if full_usdt_symbol:
            kline_tasks.append(ex_async.fetch_klines_async(exchange, full_usdt_symbol, '1d', fetch_limit))
            valid_symbols_for_kline.append(symbol)

    usdt_results = await asyncio.gather(*kline_tasks, return_exceptions=True)
    coin_data = []

    if criteria.method == 'multi_factor_weakest':
        benchmark_coins = criteria.rebalance_benchmark_coin
        if not benchmark_coins:
            raise ValueError("多因子策略需要至少指定一个基准币种 (如 BTC)。")

        await log_message(f"正在获取 {', '.join(benchmark_coins)} 作为相对强度基准K线...", "info")

        benchmark_kline_tasks = [
            ex_async.fetch_klines_async(exchange, ex_async.resolve_full_symbol(exchange, coin), '1d', fetch_limit)
            for coin in benchmark_coins
        ]
        benchmark_results = await asyncio.gather(*benchmark_kline_tasks, return_exceptions=True)

        benchmark_klines_maps = {}
        for i, klines in enumerate(benchmark_results):
            coin = benchmark_coins[i]
            if isinstance(klines, list) and len(klines) >= days_to_fetch:
                benchmark_klines_maps[coin] = {kline[0]: kline for kline in klines}
            else:
                raise ValueError(f"获取基准币种 {coin} 的K线数据失败，无法计算相对强度。")

        await log_message("基准数据准备完毕，开始合成各币种的相对强度K线...", "info")

        for i, coin_usdt_klines in enumerate(usdt_results):
            if isinstance(coin_usdt_klines, list) and len(coin_usdt_klines) >= days_to_fetch:
                symbol = valid_symbols_for_kline[i]

                synthetic_klines_dict = {}

                for bench_coin, bench_klines_map in benchmark_klines_maps.items():
                    synthetic_bench_klines = []
                    for coin_kline in coin_usdt_klines:
                        timestamp = coin_kline[0]
                        base_kline = bench_klines_map.get(timestamp)

                        if base_kline and all(p > 1e-8 for p in base_kline[1:5]):
                            synthetic_kline = [
                                timestamp,
                                coin_kline[1] / base_kline[1],
                                coin_kline[2] / base_kline[2],
                                coin_kline[3] / base_kline[3],
                                coin_kline[4] / base_kline[4],
                                coin_kline[5]
                            ]
                            synthetic_bench_klines.append(synthetic_kline)

                    synthetic_klines_dict[bench_coin] = synthetic_bench_klines

                coin_data.append({
                    'symbol': symbol,
                    'usdt_klines': coin_usdt_klines,
                    'synthetic_klines': synthetic_klines_dict
                })
    else:  # foam
        for i, klines in enumerate(usdt_results):
            if isinstance(klines, list) and len(klines) >= days_to_fetch:
                coin_data.append({'symbol': valid_symbols_for_kline[i], 'usdt_klines': klines})

    if not coin_data:
        raise ValueError("成功获取K线数据的币种为0，无法进行下一步计算。")

    await log_message(f"成功获取并处理了 {len(coin_data)} 个币种的K线数据，开始计算最终排名...", "info")

    loop = asyncio.get_running_loop()
    target_coin_list = await loop.run_in_executor(
        None,
        rebalance_logic.screen_coins_advanced,
        coin_data,
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
    # 核心修正：将 config (即 settings) 传递下去
    screening_task = screen_coins_task(exchange, criteria, config)

    all_positions, target_coin_list = await asyncio.gather(positions_task, screening_task)

    await log_message(f"筛选完成，最终选出 {len(target_coin_list)} 个目标币种。", "success")

    long_positions = [p for p in all_positions if p.side == 'long']
    current_short_positions = [p for p in all_positions if p.side == 'short']
    current_long_value = sum(p.notional for p in long_positions)

    if current_long_value <= 0:
        raise ValueError("多头仓位价值为零，无法再平衡。")

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
        positions_to_open=open_plan_formatted
    )


@router.post("/execute")
def execute_rebalance_plan(plan: ExecutionPlanRequest, background_tasks: BackgroundTasks):
    print("--- 📢 API HIT: /api/rebalance/execute ---")
    return trading_service.execute_rebalance_plan(plan, background_tasks)