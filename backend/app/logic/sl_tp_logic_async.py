# backend/app/logic/sl_tp_logic_async.py (单向持仓优先版)
import asyncio
from typing import Set, List, Dict, Any

import ccxt.async_support as ccxt

from .exceptions import InterruptedError
from ..config import i18n
from ..models.schemas import Position


async def _cancel_sl_tp_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    try:
        open_orders = await exchange.fetch_open_orders(symbol)
        orders_to_cancel = [
            order for order in open_orders
            # 单向模式下，订单通常只有 reduceOnly 标记，没有 positionSide
            if order.get('reduceOnly')
               and order['type'] in ['stop_market', 'stop', 'take_profit_market', 'take_profit']
        ]
        if not orders_to_cancel:
            return True

        tasks = [exchange.cancel_order(order['id'], symbol) for order in orders_to_cancel]
        await asyncio.gather(*tasks, return_exceptions=True)

        if len(orders_to_cancel) > 0:
            await async_logger(f"  > 为 {symbol} 清理了 {len(orders_to_cancel)} 个旧的SL/TP订单。", "info")
        return True
    except Exception as e:
        await async_logger(f"  > ❌ 为 {symbol} 清理SL/TP订单时出错: {e}", "error")
        return False


async def _place_stop_order_with_retry(
        exchange: ccxt.binanceusdm,
        symbol: str,
        type_: str,
        side: str,
        amount: float,
        params: Dict[str, Any],
        pos_side_arg: str,  # 备用的 positionSide 参数，仅在重试时使用
        async_logger
):
    """
    智能下单函数：
    优先策略: One-Way Mode (单向持仓)
    参数特征: reduceOnly=True, 且不包含 positionSide
    """

    # --- 尝试 1: One-Way Mode (默认优先) ---
    params_oneway = params.copy()

    # 确保移除 positionSide (单向持仓不能有这个)
    if 'positionSide' in params_oneway:
        del params_oneway['positionSide']

    # 确保开启 reduceOnly (单向持仓止损必须是只减仓)
    params_oneway['reduceOnly'] = True

    try:
        return await exchange.create_order(symbol, type_, side, amount, None, params_oneway)
    except ccxt.ExchangeError as e:
        error_msg = str(e)

        # 如果报错提示由 positionSide 引起 (例如 -4061)，则尝试切换到双向持仓模式
        # 虽然用户说是单向，但为了代码健壮性，保留这个 fallback
        if '-4061' in error_msg:
            # await async_logger(f"  > 模式自适应：检测到双向持仓(Hedge)模式，重试 {symbol}...", "info")

            params_hedge = params.copy()
            # Hedge 模式: 必须有 positionSide，必须移除 reduceOnly
            params_hedge['positionSide'] = pos_side_arg
            if 'reduceOnly' in params_hedge:
                del params_hedge['reduceOnly']

            return await exchange.create_order(symbol, type_, side, amount, None, params_hedge)
        else:
            raise e


async def set_tp_sl_for_position_async(exchange: ccxt.binanceusdm, position: Position, config: dict, async_logger,
                                       stop_event: asyncio.Event) -> bool:
    full_symbol = position.full_symbol
    if stop_event.is_set(): raise InterruptedError()

    try:
        # 1. 检查仓位
        live_positions_raw = await exchange.fetch_positions([full_symbol])
        live_pos = next(
            (p for p in live_positions_raw if p['symbol'] == full_symbol and float(p.get('contracts', 0)) != 0), None)

        if not live_pos:
            await async_logger(f"⚠️ 为 {position.symbol} 校准前检查发现仓位已不存在，将仅执行清理操作。", "warning")
            await _cancel_sl_tp_orders_async(exchange, full_symbol, async_logger)
            return True

        # 2. 清理旧订单
        await _cancel_sl_tp_orders_async(exchange, full_symbol, async_logger)
        if stop_event.is_set(): raise InterruptedError()

        is_long = position.side == i18n.SIDE_LONG
        side_key = "long" if is_long else "short"

        # 3. 检查开关
        sl_tp_enabled = config.get(f'enable_{side_key}_sl_tp', False)
        if not sl_tp_enabled:
            await async_logger(f"{position.symbol} 的SL/TP功能已禁用，仅执行清理。", "info")
            return True

        sl_perc = config.get(f'{side_key}_stop_loss_percentage', 0)
        tp_perc = config.get(f'{side_key}_take_profit_percentage', 0)

        tasks: List[Any] = []

        # 准备备用的 positionSide 参数 (仅用于 fallback，默认不会发送)
        pos_side_fallback = 'LONG' if is_long else 'SHORT'

        # 止损订单
        if sl_perc > 0:
            leverage = config.get('leverage', 1)
            sl_ratio = float(sl_perc) / 100 / leverage
            entry_price = position.entry_price

            if is_long:
                price_raw = entry_price * (1 - sl_ratio)
            else:
                price_raw = entry_price * (1 + sl_ratio)

            target_sl_price = float(exchange.price_to_precision(full_symbol, price_raw))
            sl_side = i18n.ORDER_SIDE_SELL if is_long else i18n.ORDER_SIDE_BUY

            # 基础参数 (不含 reduceOnly/positionSide，由 _place_stop_order_with_retry 组装)
            sl_params = {
                'stopPrice': target_sl_price,
                'workingType': 'MARK_PRICE'
            }

            await async_logger(f"  > 准备为 {position.symbol} 提交 SL (标记价: {target_sl_price}) ...")

            tasks.append(_place_stop_order_with_retry(
                exchange, full_symbol, 'STOP_MARKET', sl_side, position.contracts,
                sl_params, pos_side_fallback, async_logger
            ))

        # 止盈订单
        if tp_perc > 0:
            leverage = config.get('leverage', 1)
            tp_ratio = float(tp_perc) / 100 / leverage
            entry_price = position.entry_price

            if is_long:
                price_raw = entry_price * (1 + tp_ratio)
            else:
                price_raw = entry_price * (1 - tp_ratio)

            target_tp_price = float(exchange.price_to_precision(full_symbol, price_raw))
            tp_side = i18n.ORDER_SIDE_SELL if is_long else i18n.ORDER_SIDE_BUY

            tp_params = {
                'stopPrice': target_tp_price,
                'workingType': 'MARK_PRICE'
            }

            await async_logger(f"  > 准备为 {position.symbol} 提交 TP (标记价: {target_tp_price}) ...")

            tasks.append(_place_stop_order_with_retry(
                exchange, full_symbol, 'TAKE_PROFIT_MARKET', tp_side, position.contracts,
                tp_params, pos_side_fallback, async_logger
            ))

        if not tasks:
            await async_logger(f"  > {position.symbol} 的SL和TP百分比均未设置(>0)，不创建新订单。", "info")
            return True

        # 4. 执行
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = 0
        total_tasks = len(tasks)

        for res in results:
            if isinstance(res, dict) and res.get('id'):
                success_count += 1
            elif isinstance(res, Exception):
                await async_logger(f"  > ❌ {position.symbol} 订单提交失败: {res}", "error")

        if success_count < total_tasks:
            await async_logger(f"⚠️ {position.symbol} SL/TP未能完全设置 ({success_count}/{total_tasks} 成功)",
                               "warning")
        else:
            await async_logger(f"✅ {position.symbol} 止盈/止损校准成功！", "success")

        return success_count == total_tasks

    except InterruptedError:
        await async_logger(f"为 {position.symbol} 设置SL/TP的操作被中断。", "warning")
        return False
    except ccxt.ExchangeError as e:
        if '-1106' in str(e):
            await async_logger(f"⚠️ 为 {position.symbol} 设置SL/TP失败 (参数冲突): {e}", "warning")
            return True
        await async_logger(f"❌ 设置 {position.symbol} SL/TP时发生未处理的交易所错误: {e}", "error")
        return False
    except Exception as e:
        await async_logger(f"❌ 设置 {position.symbol} SL/TP时发生严重错误: {e}", "error")
        return False


async def cleanup_orphan_sltp_orders_async(exchange: ccxt.binanceusdm, active_symbols: Set[str], async_logger):
    await async_logger("开始全局清理无主(孤儿)SL/TP订单...", "info")
    try:
        all_open_orders = await exchange.fetch_open_orders()
        orphan_orders = [
            order for order in all_open_orders
            if order.get('reduceOnly') and order['symbol'] not in active_symbols
        ]
        if not orphan_orders:
            await async_logger("未发现任何无主订单。", "success")
            return
        await async_logger(f"发现 {len(orphan_orders)} 个无主订单，正在取消...", "warning")
        tasks = [exchange.cancel_order(order['id'], order['symbol']) for order in orphan_orders]
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        await async_logger(f"!!! 清理无主订单时发生错误: {e}", "error")