# backend/app/api/rebalance.py (完整代码)
import asyncio
from fastapi import APIRouter, HTTPException, Depends
import ccxt.async_support as ccxt
from typing import Dict, Any, List

from ..models.schemas import RebalanceCriteria, RebalancePlanResponse, Position
from ..core.exchange_manager import get_exchange_dependency
from ..logic import rebalance_logic
from ..logic import exchange_logic_async as ex_async
from ..config.config import AVAILABLE_SHORT_COINS, AVAILABLE_LONG_COINS, load_settings, STABLECOIN_PREFERENCE
from ..core.websocket_manager import log_message

router = APIRouter(prefix="/api/rebalance", tags=["Rebalance"])


async def screen_coins_task(exchange: ccxt.binanceusdm, criteria: RebalanceCriteria) -> List[str]:
    await log_message(f"开始筛选，策略: {criteria.method}, 目标数量: {criteria.top_n}", "info")

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
                base in AVAILABLE_SHORT_COINS and
                ticker.get('quoteVolume', 0) is not None and
                ticker['quoteVolume'] > criteria.min_volume_usd):
            liquid_coins_symbols.append(base)
            processed_bases.add(base)

    if not liquid_coins_symbols:
        raise ValueError("没有币种通过流动性筛选。请检查备选池或降低交易额门槛。")

    await log_message(f"通过流动性筛选的币种数量: {len(liquid_coins_symbols)}", "info")

    days_to_fetch = max(criteria.abs_momentum_days, criteria.rel_strength_days, criteria.foam_days, 2)
    await log_message(f"准备并发获取 {len(liquid_coins_symbols)} 个币种过去 {days_to_fetch} 天的K线...", "info")

    tasks = []
    for symbol in liquid_coins_symbols:
        tasks.append(ex_async.fetch_klines_async(exchange, f"{symbol}/USDT", '1d', days_to_fetch))
        # 为“多因子弱势”策略准备BTC交易对数据
        if criteria.method == 'multi_factor_weakest':
            tasks.append(ex_async.fetch_klines_async(exchange, f"{symbol}/BTC", '1d', criteria.rel_strength_days + 2))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    coin_data = []
    if criteria.method == 'multi_factor_weakest':
        for i in range(0, len(results), 2):
            symbol_index = i // 2
            usdt_klines = results[i]
            btc_klines = results[i + 1]
            if isinstance(usdt_klines, list) and len(usdt_klines) >= days_to_fetch:
                data = {'symbol': liquid_coins_symbols[symbol_index], 'usdt_klines': usdt_klines}
                if isinstance(btc_klines, list):
                    data['btc_klines'] = btc_klines
                coin_data.append(data)
    else:  # foam
        for i, klines in enumerate(results):
            if isinstance(klines, list) and len(klines) >= days_to_fetch:
                coin_data.append({'symbol': liquid_coins_symbols[i], 'usdt_klines': klines})

    if not coin_data:
        raise ValueError("成功获取K线数据的币种为0，无法进行下一步计算。")

    await log_message(f"成功获取 {len(coin_data)} 个币种的K线数据，开始计算排名...", "info")

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
        exchange: ccxt.binanceusdm = Depends(get_exchange_dependency)
):
    try:
        config = load_settings()

        positions_task = ex_async.fetch_positions_with_pnl_async(exchange)
        screening_task = screen_coins_task(exchange, criteria)

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

        # --- 核心修复：适配新的返回值 ---
        close_plan_data, open_plan_data = rebalance_logic.generate_rebalance_plan(
            current_short_positions, target_coin_list, target_short_value
        )

        close_plan_formatted = []
        for p_info in close_plan_data:
            close_plan_formatted.append({
                "symbol": p_info["symbol"],
                "close_value": p_info["notional"] * p_info["close_ratio"],
                "close_ratio_perc": p_info["close_ratio"] * 100
            })

        open_plan_formatted = []
        value_per_coin_ideal = target_short_value / len(target_coin_list) if target_coin_list else 0
        for symbol, value in open_plan_data.items():
            percentage = (value / value_per_coin_ideal) * 100 if value_per_coin_ideal > 0.01 else 100
            open_plan_formatted.append({
                "symbol": symbol,
                "open_value": value,
                "percentage": percentage
            })
        # --- 修复结束 ---

        return RebalancePlanResponse(
            target_ratio_perc=target_ratio * 100,
            positions_to_close=close_plan_formatted,
            positions_to_open=open_plan_formatted
        )
    except Exception as e:
        error_message = str(e)
        await log_message(f"生成再平衡计划失败: {error_message}", "error")
        return RebalancePlanResponse(
            target_ratio_perc=0,
            positions_to_close=[],
            positions_to_open=[],
            error=error_message
        )