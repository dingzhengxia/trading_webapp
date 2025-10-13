# backend/app/logic/sl_tp_logic_async.py (精细化SL/TP控制)
import asyncio
from typing import Set, List

import ccxt.async_support as ccxt

from .exceptions import InterruptedError
from ..config import i18n
from ..models.schemas import Position


async def _cancel_sl_tp_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    try:
        open_orders = await exchange.fetch_open_orders(symbol)
        orders_to_cancel = [
            order for order in open_orders
            if order.get('reduceOnly') and order['type'] in ['stop_market', 'stop', 'take_profit_market', 'take_profit']
        ]
        if not orders_to_cancel:
            return True
        tasks = [exchange.cancel_order(order['id'], symbol) for order in orders_to_cancel]
        await asyncio.gather(*tasks, return_exceptions=True)
        await async_logger(f"  > 为 {symbol} 清理了 {len(orders_to_cancel)} 个旧的SL/TP订单。", "info")
        return True
    except Exception as e:
        await async_logger(f"  > ❌ 为 {symbol} 清理SL/TP订单时出错: {e}", "error")
        return False


async def set_tp_sl_for_position_async(exchange: ccxt.binanceusdm, position: Position, config: dict, async_logger,
                                       stop_event: asyncio.Event) -> bool:
    full_symbol = position.full_symbol
    if stop_event.is_set(): raise InterruptedError()

    try:
        live_positions_raw = await exchange.fetch_positions([full_symbol])
        live_pos = next(
            (p for p in live_positions_raw if p['symbol'] == full_symbol and float(p.get('contracts', 0)) != 0), None)

        if not live_pos:
            await async_logger(f"⚠️ 为 {position.symbol} 校准前检查发现仓位已不存在，将仅执行清理操作。", "warning")
            await _cancel_sl_tp_orders_async(exchange, full_symbol, async_logger)
            return True

        # --- 核心逻辑修改：精细化控制 SL 和 TP ---

        # 1. 总是先清理旧订单，确保状态干净
        await _cancel_sl_tp_orders_async(exchange, full_symbol, async_logger)
        if stop_event.is_set(): raise InterruptedError()

        is_long = position.side == i18n.SIDE_LONG
        side_key = "long" if is_long else "short"

        # 2. 检查总开关是否开启
        sl_tp_enabled = config.get(f'enable_{side_key}_sl_tp', False)
        if not sl_tp_enabled:
            await async_logger(f"{position.symbol} 的SL/TP功能已禁用，仅执行清理。", "info")
            return True

        sl_perc = config.get(f'{side_key}_stop_loss_percentage', 0)
        tp_perc = config.get(f'{side_key}_take_profit_percentage', 0)

        tasks: List[asyncio.Task] = []

        # 3. 如果止损百分比 > 0，则创建止损任务
        if sl_perc > 0:
            leverage = config.get('leverage', 1)
            sl_ratio = float(sl_perc) / 100 / leverage
            entry_price = position.entry_price
            target_sl_price = float(
                exchange.price_to_precision(full_symbol, entry_price * (1 - (sl_ratio if is_long else -sl_ratio))))

            sl_side = i18n.ORDER_SIDE_SELL if is_long else i18n.ORDER_SIDE_BUY
            sl_params = {'stopPrice': target_sl_price, 'reduceOnly': True}

            await async_logger(f"  > 准备为 {position.symbol} 提交 SL ({target_sl_price}) 订单...")
            sl_task = exchange.create_order(full_symbol, 'STOP_MARKET', sl_side, position.contracts, None, sl_params)
            tasks.append(sl_task)

        # 4. 如果止盈百分比 > 0，则创建止盈任务
        if tp_perc > 0:
            leverage = config.get('leverage', 1)
            tp_ratio = float(tp_perc) / 100 / leverage
            entry_price = position.entry_price
            target_tp_price = float(
                exchange.price_to_precision(full_symbol, entry_price * (1 + (tp_ratio if is_long else -tp_ratio))))

            tp_side = i18n.ORDER_SIDE_SELL if is_long else i18n.ORDER_SIDE_BUY
            tp_params = {'stopPrice': target_tp_price, 'reduceOnly': True}

            await async_logger(f"  > 准备为 {position.symbol} 提交 TP ({target_tp_price}) 订单...")
            tp_task = exchange.create_order(full_symbol, 'TAKE_PROFIT_MARKET', tp_side, position.contracts, None,
                                            tp_params)
            tasks.append(tp_task)

        # 5. 如果没有任何任务，记录并返回成功
        if not tasks:
            await async_logger(f"  > {position.symbol} 的SL和TP百分比均未设置(>0)，不创建新订单。", "info")
            return True

        # 6. 执行创建的任务
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for res in results if isinstance(res, dict) and res.get('id'))
        total_tasks = len(tasks)

        if success_count < total_tasks:
            for res in results:
                if isinstance(res, Exception):
                    await async_logger(f"  > ❌ {position.symbol} 订单提交失败: {res}", "error")
            await async_logger(f"⚠️ {position.symbol} SL/TP未能完全设置，请检查！", "warning")
        else:
            await async_logger(f"✅ {position.symbol} 止盈和/或止损均已校准！", "success")

        return success_count == total_tasks
        # --- 修改结束 ---

    except InterruptedError:
        await async_logger(f"为 {position.symbol} 设置SL/TP的操作被中断。", "warning")
        return False
    except ccxt.ExchangeError as e:
        if '-1106' in str(e):  # 'Parameter "XXX" is not valid.' Usually means position closed.
            await async_logger(f"⚠️ 为 {position.symbol} 设置SL/TP失败 (仓位可能已关闭): {e.args[0]}", "warning")
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