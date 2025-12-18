# backend/app/logic/sl_tp_logic_async.py (严格限价止损止盈版 - 符合文档规范)
import asyncio
from typing import Set, List, Dict, Any

import ccxt.async_support as ccxt

from .exceptions import InterruptedError
from ..config import i18n
from ..models.schemas import Position


async def _cancel_sl_tp_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    清理该交易对下所有只减仓的条件单
    """
    try:
        open_orders = await exchange.fetch_open_orders(symbol)
        # 清理所有 Stop/TakeProfit 类型的订单
        orders_to_cancel = [
            order for order in open_orders
            if order.get('reduceOnly')
               and order['type'] in ['stop', 'take_profit', 'stop_market', 'take_profit_market']
        ]
        if not orders_to_cancel:
            return True

        tasks = [exchange.cancel_order(order['id'], symbol) for order in orders_to_cancel]
        await asyncio.gather(*tasks, return_exceptions=True)
        return True
    except Exception as e:
        await async_logger(f"  > ❌ 为 {symbol} 清理SL/TP订单时出错: {e}", "error")
        return False


async def _place_limit_conditional_order(
        exchange: ccxt.binanceusdm,
        symbol: str,
        side: str,
        amount: float,
        trigger_price: float,
        limit_price: float,
        is_stop_loss: bool,
        async_logger
):
    """
    下单核心函数：发送符合文档要求的限价条件单 (STOP_LOSS_LIMIT / TAKE_PROFIT_LIMIT)

    对应币安合约 API 参数:
    - type: STOP (限价止损) 或 TAKE_PROFIT (限价止盈)
    - price: 触发后的挂单价格
    - stopPrice: 触发价格
    - quantity: 数量
    - timeInForce: GTC
    - reduceOnly: True
    """

    # 1. 确定 API 订单类型
    # 在 CCXT Binance Futures 中:
    # 'STOP' 对应 STOP_LOSS_LIMIT
    # 'TAKE_PROFIT' 对应 TAKE_PROFIT_LIMIT
    order_type = 'STOP' if is_stop_loss else 'TAKE_PROFIT'

    # 2. 准备参数
    params = {
        'stopPrice': trigger_price,  # 触发价格
        'timeInForce': 'GTC',  # 必须参数
        'reduceOnly': True,  # 单向持仓必须参数
        'workingType': 'MARK_PRICE'  # 推荐使用标记价格触发，防止插针
    }

    # 3. 调试日志
    # print(f"--- [DEBUG] 下单: {symbol} {side} {order_type} | 触发: {trigger_price} | 限价: {limit_price} ---")

    try:
        # ccxt.create_order(symbol, type, side, amount, price, params)
        # 注意：这里必须传入第5个参数 price
        return await exchange.create_order(symbol, order_type, side, amount, limit_price, params)
    except ccxt.ExchangeError as e:
        error_msg = str(e)
        if '-4061' in error_msg:
            # 如果遇到双向持仓错误，尝试切换参数（虽然用户说是单向，但为了健壮性）
            params_hedge = params.copy()
            del params_hedge['reduceOnly']
            params_hedge['positionSide'] = 'LONG' if side == 'sell' else 'SHORT'
            return await exchange.create_order(symbol, order_type, side, amount, limit_price, params_hedge)
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
            await async_logger(f"⚠️ {position.symbol} 仓位不存在，跳过。", "warning")
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
            await async_logger(f"{position.symbol} SL/TP 已禁用。", "info")
            return True

        sl_perc = config.get(f'{side_key}_stop_loss_percentage', 0)
        tp_perc = config.get(f'{side_key}_take_profit_percentage', 0)

        tasks: List[Any] = []

        # ==================== 计算逻辑 ====================
        # 为了保证限价单能像止损一样成交，我们需要设置一个“滑点缓冲”。
        # 如果多单止损：触发价 100，限价设为 95。这样触发时会以“不低于95”的价格卖出，
        # 由于当时市价是100，系统会立即以最优价（约100）成交。
        # 如果您希望完全不滑点（严格限价），可以将下面的 buffer 系数改为 1.0，但那样可能无法完全成交。
        SLIPPAGE_BUFFER = 0.05  # 5% 的价格缓冲，确保止损能成交

        # --- 止损订单 (STOP LOSS LIMIT) ---
        if sl_perc > 0:
            leverage = config.get('leverage', 1)
            sl_ratio = float(sl_perc) / 100 / leverage
            entry_price = position.entry_price

            # 1. 计算触发价格 (Stop Price)
            if is_long:
                raw_trigger = entry_price * (1 - sl_ratio)
                sl_side = 'sell'
                # 多单止损卖出：限价 = 触发价 * (1 - 缓冲)
                raw_limit = raw_trigger * (1 - SLIPPAGE_BUFFER)
            else:
                raw_trigger = entry_price * (1 + sl_ratio)
                sl_side = 'buy'
                # 空单止损买入：限价 = 触发价 * (1 + 缓冲)
                raw_limit = raw_trigger * (1 + SLIPPAGE_BUFFER)

            # 2. 精度修正
            trigger_price = float(exchange.price_to_precision(full_symbol, raw_trigger))
            limit_price = float(exchange.price_to_precision(full_symbol, raw_limit))

            await async_logger(f"  > 准备提交 {position.symbol} 限价止损 (触发: {trigger_price}, 限价: {limit_price})")

            tasks.append(_place_limit_conditional_order(
                exchange, full_symbol, sl_side, position.contracts,
                trigger_price, limit_price, is_stop_loss=True, async_logger=async_logger
            ))

        # --- 止盈订单 (TAKE PROFIT LIMIT) ---
        if tp_perc > 0:
            leverage = config.get('leverage', 1)
            tp_ratio = float(tp_perc) / 100 / leverage
            entry_price = position.entry_price

            # 1. 计算触发价格
            if is_long:
                raw_trigger = entry_price * (1 + tp_ratio)
                tp_side = 'sell'
                # 多单止盈卖出：限价 = 触发价 (止盈通常希望卖得更高，或者设为与触发价相同)
                # 为了保证触发即成交，也可以略微让利，或者设为相同。这里设为相同。
                raw_limit = raw_trigger
            else:
                raw_trigger = entry_price * (1 - tp_ratio)
                tp_side = 'buy'
                # 空单止盈买入
                raw_limit = raw_trigger

            # 2. 精度修正
            trigger_price = float(exchange.price_to_precision(full_symbol, raw_trigger))
            limit_price = float(exchange.price_to_precision(full_symbol, raw_limit))

            await async_logger(f"  > 准备提交 {position.symbol} 限价止盈 (触发: {trigger_price}, 限价: {limit_price})")

            tasks.append(_place_limit_conditional_order(
                exchange, full_symbol, tp_side, position.contracts,
                trigger_price, limit_price, is_stop_loss=False, async_logger=async_logger
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