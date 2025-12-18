# backend/app/logic/sl_tp_logic_async.py (最终方案：自动降级为模拟市价的限价止损)
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
            if (order.get('reduceOnly') or order.get('info', {}).get('reduceOnly'))
               and order['type'] in ['stop_market', 'stop', 'take_profit_market', 'take_profit']
        ]
        if not orders_to_cancel:
            return True

        tasks = [exchange.cancel_order(order['id'], symbol) for order in orders_to_cancel]
        await asyncio.gather(*tasks, return_exceptions=True)
        return True
    except Exception as e:
        await async_logger(f"  > ❌ 为 {symbol} 清理SL/TP订单时出错: {e}", "error")
        return False


async def _place_stop_order_final(
        exchange: ccxt.binanceusdm,
        symbol: str,
        side: str,
        amount: float,
        trigger_price: float,
        is_stop_loss: bool,  # True=SL, False=TP
        pos_side_fallback: str,
        async_logger
):
    """
    终极下单函数：
    1. 优先尝试标准的 STOP_MARKET / TAKE_PROFIT_MARKET
    2. 如果报错 -4120 (类型不支持)，自动降级为 STOP / TAKE_PROFIT (限价单)，并设置大滑点模拟市价。
    """

    # 确定首选类型
    if is_stop_loss:
        primary_type = 'STOP_MARKET'
        secondary_type = 'STOP'
    else:
        primary_type = 'TAKE_PROFIT_MARKET'
        secondary_type = 'TAKE_PROFIT'

    # 基础参数 (One-Way Mode)
    params = {
        'stopPrice': trigger_price,
        'workingType': 'MARK_PRICE',
        'reduceOnly': True
    }

    try:
        # --- 尝试 1: 标准市价止损/止盈 ---
        # print(f"--- [DEBUG] 尝试标准市价止损 {symbol} Type={primary_type} ---")
        return await exchange.create_order(symbol, primary_type, side, amount, None, params)

    except ccxt.ExchangeError as e:
        error_msg = str(e)

        # 处理 -4061 (Hedge Mode 冲突)
        if '-4061' in error_msg:
            # print(f"--- [DEBUG] 切换到 Hedge Mode 重试 {symbol} ---")
            params_hedge = params.copy()
            params_hedge['positionSide'] = pos_side_fallback
            if 'reduceOnly' in params_hedge: del params_hedge['reduceOnly']
            return await exchange.create_order(symbol, primary_type, side, amount, None, params_hedge)

        # 处理 -4120 (市价止损不支持) -> 降级为限价止损
        elif '-4120' in error_msg:
            print(f"--- [DEBUG] {symbol} 不支持市价止损，降级为模拟市价的限价止损 (Type={secondary_type}) ---")

            # 计算激进的限价价格以确保立即成交
            # 买入平空: 限价 = 触发价 * 1.1 (允许10%滑点)
            # 卖出平多: 限价 = 触发价 * 0.9 (允许10%滑点)
            if side.lower() == 'buy':
                limit_price = trigger_price * 1.1
            else:
                limit_price = trigger_price * 0.9

            # 修正价格精度
            limit_price = float(exchange.price_to_precision(symbol, limit_price))

            # 构建限价单参数
            params_limit = params.copy()
            # 限价单不需要 type 字段在 params 里，create_order 第2个参数决定

            return await exchange.create_order(symbol, secondary_type, side, amount, limit_price, params_limit)

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
            await async_logger(f"⚠️ 为 {position.symbol} 校准前检查发现仓位已不存在。", "warning")
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
            await async_logger(f"{position.symbol} 的SL/TP功能已禁用。", "info")
            return True

        sl_perc = config.get(f'{side_key}_stop_loss_percentage', 0)
        tp_perc = config.get(f'{side_key}_take_profit_percentage', 0)

        tasks: List[Any] = []
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

            await async_logger(f"  > 准备为 {position.symbol} 提交 SL (触发价: {target_sl_price}) ...")

            tasks.append(_place_stop_order_final(
                exchange, full_symbol, sl_side, position.contracts,
                target_sl_price, True, pos_side_fallback, async_logger
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

            await async_logger(f"  > 准备为 {position.symbol} 提交 TP (触发价: {target_tp_price}) ...")

            tasks.append(_place_stop_order_final(
                exchange, full_symbol, tp_side, position.contracts,
                target_tp_price, False, pos_side_fallback, async_logger
            ))

        if not tasks:
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
        await async_logger(f"❌ 设置 {position.symbol} SL/TP时发生交易所错误: {e}", "error")
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