# backend/app/logic/sl_tp_logic_async.py (最终修复版)
import asyncio
import math
import ccxt.async_support as ccxt
from typing import List

from .exceptions import InterruptedError
from ..config import i18n
from ..models.schemas import Position
from .utils import resolve_full_symbol


async def _cancel_sl_tp_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """异步清理指定交易对的所有止盈止损挂单"""
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


# --- 核心修改在这里 ---
# 1. 在函数签名中添加 stop_event 参数
async def set_tp_sl_for_position_async(exchange: ccxt.binanceusdm, position: Position, config: dict, async_logger,
                                       stop_event: asyncio.Event):
    # --- 修改结束 ---
    """
    为单个仓位异步设置止盈止损，并响应停止信号。
    """
    full_symbol = position.full_symbol
    if not full_symbol:
        await async_logger(f"无法为 {position.symbol} 找到交易对，跳过SL/TP设置。", "warning")
        return False

    # 2. 在函数开始时就检查停止信号
    if stop_event.is_set(): raise InterruptedError()

    is_long = position.side == i18n.SIDE_LONG
    side_text = "多头" if is_long else "空头"

    if (is_long and not config.get('enable_long_sl_tp', False)) or \
            (not is_long and not config.get('enable_short_sl_tp', False)):
        await async_logger(f"{side_text}仓位 {position.symbol} 的SL/TP已禁用，将清理现有挂单。")
        return await _cancel_sl_tp_orders_async(exchange, full_symbol, async_logger)

    sl_perc = config.get('long_stop_loss_percentage' if is_long else 'short_stop_loss_percentage', 0)
    tp_perc = config.get('long_take_profit_percentage' if is_long else 'short_take_profit_percentage', 0)

    if sl_perc <= 0 or tp_perc <= 0:
        await async_logger(f"{position.symbol} 的SL/TP参数无效(<=0)，将清理挂单并跳过。", "warning")
        return await _cancel_sl_tp_orders_async(exchange, full_symbol, async_logger)

    leverage = config.get('leverage', 1)
    sl_ratio, tp_ratio = float(sl_perc) / 100 / leverage, float(tp_perc) / 100 / leverage
    entry_price = position.entry_price

    if is_long:
        target_sl_price = float(exchange.price_to_precision(full_symbol, entry_price * (1 - sl_ratio)))
        target_tp_price = float(exchange.price_to_precision(full_symbol, entry_price * (1 + tp_ratio)))
    else:
        target_sl_price = float(exchange.price_to_precision(full_symbol, entry_price * (1 + sl_ratio)))
        target_tp_price = float(exchange.price_to_precision(full_symbol, entry_price * (1 - tp_ratio)))

    try:
        # 3. 在进行网络请求前，再次检查停止信号
        if stop_event.is_set(): raise InterruptedError()
        await _cancel_sl_tp_orders_async(exchange, full_symbol, async_logger)  # 先清理所有旧订单

        # 4. 在提交新订单前，再次检查
        if stop_event.is_set(): raise InterruptedError()
        sl_side = i18n.ORDER_SIDE_SELL if is_long else i18n.ORDER_SIDE_BUY
        sl_params = {'stopPrice': target_sl_price, 'reduceOnly': True, 'closePosition': True}
        tp_params = {'stopPrice': target_tp_price, 'reduceOnly': True, 'closePosition': True}

        await async_logger(
            f"  > 正在为 {position.symbol} 提交新的 SL ({target_sl_price}) / TP ({target_tp_price}) 订单...")

        # 将两个订单并发提交
        sl_task = exchange.create_order(full_symbol, 'STOP_MARKET', sl_side, position.contracts, None, sl_params)
        tp_task = exchange.create_order(full_symbol, 'TAKE_PROFIT_MARKET', sl_side, position.contracts, None, tp_params)

        results = await asyncio.gather(sl_task, tp_task, return_exceptions=True)

        success_count = 0
        for res in results:
            if isinstance(res, dict) and res.get('id'):
                success_count += 1
                await async_logger(f"  > ✅ 订单 (ID: {res['id']}) 提交成功。", "success")
            else:
                await async_logger(f"  > ❌ 订单提交失败: {res}", "error")

        if success_count == 2:
            await async_logger(f"✅ {position.symbol} 止盈和止损均已校准！", "success")
            return True
        else:
            await async_logger(f"⚠️ {position.symbol} SL/TP未能完全设置，请检查！", "warning")
            return False

    except InterruptedError:
        await async_logger(f"为 {position.symbol} 设置SL/TP的操作被中断。", "warning")
        return False  # 中断不算成功
    except Exception as e:
        await async_logger(f"❌ 设置 {position.symbol} SL/TP时发生严重错误: {e}", "error")
        return False


async def cleanup_orphan_sltp_orders_async(exchange: ccxt.binanceusdm, active_symbols: List[str], async_logger):
    await async_logger("开始全局清理无主(孤儿)SL/TP订单...", "info")
    try:
        all_open_orders = await exchange.fetch_open_orders()
        orphan_orders = [
            order for order in all_open_orders
            if order.get('reduceOnly') and
               order['type'] in ['stop_market', 'stop', 'take_profit_market', 'take_profit'] and
               order['symbol'] not in active_symbols
        ]
        if not orphan_orders:
            await async_logger("未发现任何无主订单。", "success")
            return
        await async_logger(f"发现 {len(orphan_orders)} 个无主订单，正在取消...", "warning")
        tasks = [exchange.cancel_order(order['id'], order['symbol']) for order in orphan_orders]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        await async_logger(f"无主订单清理完成，成功取消 {success_count} 个。", "success")
    except Exception as e:
        await async_logger(f"!!! 清理无主订单时发生错误: {e}", "error")