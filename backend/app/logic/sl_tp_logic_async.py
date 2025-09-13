import asyncio
import math
import ccxt.async_support as ccxt
from ..config import i18n
from ..models.schemas import Position
from .exchange_logic_async import resolve_full_symbol


async def _cancel_sl_tp_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """异步清理指定交易对的所有止盈止损挂单"""
    await async_logger(f"正在为 {symbol} 清理旧的SL/TP订单...")
    try:
        open_orders = await exchange.fetch_open_orders(symbol)
        canceled_count = 0
        tasks = []

        # 收集所有需要取消的订单ID
        orders_to_cancel = [
            order for order in open_orders
            if order.get('reduceOnly') and order['type'] in ['stop_market', 'stop', 'take_profit_market', 'take_profit']
        ]

        if not orders_to_cancel:
            await async_logger("  > 未发现需要取消的旧订单。")
            return True

        # 并发取消订单
        for order in orders_to_cancel:
            tasks.append(exchange.cancel_order(order['id'], symbol))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, res in enumerate(results):
            order_id_to_cancel = orders_to_cancel[i]['id']
            if isinstance(res, dict):
                canceled_count += 1
                await async_logger(f"  > ✅ 已取消订单: {order_id_to_cancel}")
            else:
                await async_logger(f"  > ⚠️ 取消订单 {order_id_to_cancel} 失败: {res}", "warning")

        return True
    except Exception as e:
        await async_logger(f"  > ❌ 清理SL/TP订单时出错: {e}", "error")
        return False


async def set_tp_sl_for_position_async(exchange: ccxt.binanceusdm, position: Position, config: dict, async_logger):
    """
    严格按照原始逻辑，为单个仓位异步设置止盈止损。
    """
    full_symbol = resolve_full_symbol(exchange, position.symbol)
    if not full_symbol:
        await async_logger(f"无法为 {position.symbol} 找到交易对，跳过SL/TP设置。", "warning")
        return False

    is_long = position.side == i18n.SIDE_LONG
    side_text = "多头" if is_long else "空头"

    # 检查是否为该方向启用了SL/TP
    if (is_long and not config.get('enable_long_sl_tp', False)) or \
            (not is_long and not config.get('enable_short_sl_tp', False)):
        await async_logger(f"{side_text}仓位 {position.symbol} 的SL/TP已禁用，将清理现有挂单。")
        return await _cancel_sl_tp_orders_async(exchange, full_symbol, async_logger)

    # 获取SL/TP百分比
    sl_perc = config.get('long_stop_loss_percentage' if is_long else 'short_stop_loss_percentage', 0)
    tp_perc = config.get('long_take_profit_percentage' if is_long else 'short_take_profit_percentage', 0)

    if sl_perc <= 0 or tp_perc <= 0:
        await async_logger(f"{position.symbol} 的SL/TP参数无效(<=0)，将清理挂单并跳过。", "warning")
        return await _cancel_sl_tp_orders_async(exchange, full_symbol, async_logger)

    # 精确计算目标价格
    leverage = config.get('leverage', 1)
    sl_ratio = float(sl_perc) / 100 / leverage
    tp_ratio = float(tp_perc) / 100 / leverage

    entry_price = position.entry_price
    if is_long:
        target_sl_price = float(exchange.price_to_precision(full_symbol, entry_price * (1 - sl_ratio)))
        target_tp_price = float(exchange.price_to_precision(full_symbol, entry_price * (1 + tp_ratio)))
    else:  # is_short
        target_sl_price = float(exchange.price_to_precision(full_symbol, entry_price * (1 + sl_ratio)))
        target_tp_price = float(exchange.price_to_precision(full_symbol, entry_price * (1 - tp_ratio)))

    await async_logger(f"目标价格 -> 止损: {target_sl_price}, 止盈: {target_tp_price}")

    try:
        # 获取现有订单
        open_orders = await exchange.fetch_open_orders(full_symbol)
        existing_sl_order, existing_tp_order = None, None
        other_reduce_only_orders_to_cancel = []

        for order in open_orders:
            if order.get('reduceOnly'):
                if order['type'] in ['stop_market', 'stop']:
                    if not existing_sl_order:
                        existing_sl_order = order
                    else:
                        other_reduce_only_orders_to_cancel.append(order['id'])
                elif order['type'] in ['take_profit_market', 'take_profit']:
                    if not existing_tp_order:
                        existing_tp_order = order
                    else:
                        other_reduce_only_orders_to_cancel.append(order['id'])
                else:
                    other_reduce_only_orders_to_cancel.append(order['id'])

        # 清理多余的只减仓订单
        if other_reduce_only_orders_to_cancel:
            cancel_tasks = [exchange.cancel_order(order_id, full_symbol) for order_id in
                            other_reduce_only_orders_to_cancel]
            await asyncio.gather(*cancel_tasks, return_exceptions=True)
            await async_logger(f"  > 清理了 {len(other_reduce_only_orders_to_cancel)} 个多余的只减仓订单。", "info")

        sl_ok, tp_ok = False, False
        sl_side = i18n.ORDER_SIDE_SELL if is_long else i18n.ORDER_SIDE_BUY

        # --- 处理止损单 ---
        if existing_sl_order and math.isclose(existing_sl_order.get('stopPrice'), target_sl_price):
            await async_logger(f"  > ✅ 现有止损单 (ID: {existing_sl_order['id']}) 价格正确。")
            sl_ok = True
        else:
            if existing_sl_order:
                await async_logger(f"  > 止损单价格不匹配，正在取消旧单 (ID: {existing_sl_order['id']})...")
                await exchange.cancel_order(existing_sl_order['id'], full_symbol)
            await async_logger("  > 正在提交新的止损单...")
            sl_params = {'stopPrice': target_sl_price, 'reduceOnly': True}
            sl_order = await exchange.create_order(full_symbol, 'STOP_MARKET', sl_side, position.contracts, None,
                                                   sl_params)
            await async_logger(f"  > ✅ 新止损单已提交！ID: {sl_order['id']}")
            sl_ok = True

        # --- 处理止盈单 ---
        if existing_tp_order and math.isclose(existing_tp_order.get('stopPrice'), target_tp_price):
            await async_logger(f"  > ✅ 现有止盈单 (ID: {existing_tp_order['id']}) 价格正确。")
            tp_ok = True
        else:
            if existing_tp_order:
                await async_logger(f"  > 止盈单价格不匹配，正在取消旧单 (ID: {existing_tp_order['id']})...")
                await exchange.cancel_order(existing_tp_order['id'], full_symbol)
            await async_logger("  > 正在提交新的止盈单...")
            tp_params = {'stopPrice': target_tp_price, 'reduceOnly': True}
            tp_order = await exchange.create_order(full_symbol, 'TAKE_PROFIT_MARKET', sl_side, position.contracts, None,
                                                   tp_params)
            await async_logger(f"  > ✅ 新止盈单已提交！ID: {tp_order['id']}")
            tp_ok = True

        if sl_ok and tp_ok:
            await async_logger(f"✅ {position.symbol} 止盈和止损均已校准！", "success")
            return True
        else:
            # 这种情况理论上不应该发生，因为我们总是尝试创建
            await async_logger(f"⚠️ {position.symbol} SL/TP未能完全设置，请检查！", "warning")
            return False

    except Exception as e:
        await async_logger(f"❌ 设置 {position.symbol} SL/TP时发生严重错误: {e}", "error")
        return False