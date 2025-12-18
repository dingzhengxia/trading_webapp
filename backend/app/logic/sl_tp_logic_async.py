# backend/app/logic/sl_tp_logic_async.py (标准CCXT接口 + 参数严格互斥版)
import asyncio
from typing import Set, List, Any

import ccxt.async_support as ccxt

from .exceptions import InterruptedError
from ..config import i18n
from ..models.schemas import Position


async def _cancel_sl_tp_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """清理旧订单"""
    try:
        open_orders = await exchange.fetch_open_orders(symbol)
        orders_to_cancel = [
            order for order in open_orders
            if (order.get('reduceOnly') or order.get('info', {}).get('closePosition'))
               and order['type'] in ['STOP', 'TAKE_PROFIT', 'STOP_MARKET', 'TAKE_PROFIT_MARKET']
        ]
        if not orders_to_cancel: return True

        tasks = [exchange.cancel_order(order['id'], symbol) for order in orders_to_cancel]
        await asyncio.gather(*tasks, return_exceptions=True)
        return True
    except Exception as e:
        await async_logger(f"  > ❌ 清理旧订单失败: {e}", "error")
        return False


async def _place_stop_order_ccxt(
        exchange: ccxt.binanceusdm,
        symbol: str,
        side: str,
        amount: float,
        trigger_price: float,
        is_stop_loss: bool,
        async_logger
):
    """
    使用 standard create_order 方法。
    严格区分 STOP_MARKET (无价格) 和 STOP (有价格) 的参数要求。
    """

    # 1. 精度处理
    str_trigger_price = float(exchange.price_to_precision(symbol, trigger_price))
    str_amount = float(exchange.amount_to_precision(symbol, amount))

    # ======================================================
    # 策略 A: 优先尝试 STOP_MARKET + closePosition (最稳)
    # 这种方式不需要 quantity，不需要 price，符合 Algo 定义
    # ======================================================
    type_market = 'STOP_MARKET' if is_stop_loss else 'TAKE_PROFIT_MARKET'

    # 关键：当使用 closePosition=True 时，create_order 的 amount 应该传 0 或 None (取决于具体驱动实现)
    # 但为了兼容性，params 里带上 closePosition: True 才是核心
    params_market = {
        'stopPrice': str_trigger_price,
        'closePosition': True,  # 这里的 True 是布尔值，ccxt 会处理
        'workingType': 'MARK_PRICE'
    }
    # 绝对不传 'reduceOnly', 'timeInForce'

    try:
        # print(f"--- [DEBUG] 尝试策略A (市价全平) {symbol} ---")
        # 注意：这里 amount 传 0，因为 closePosition=True 会忽略数量
        return await exchange.create_order(symbol, type_market, side, 0, None, params_market)

    except ccxt.ExchangeError as e:
        err_msg = str(e)
        # 如果报错 -4120 (Type not supported) 或 -2021 (Immediate trigger)
        # print(f"--- [DEBUG] 策略A失败: {err_msg} -> 切换策略B ---")

        # ======================================================
        # 策略 B: 降级为 STOP (限价单) + reduceOnly
        # 必须传 price, quantity, timeInForce
        # ======================================================
        type_limit = 'STOP' if is_stop_loss else 'TAKE_PROFIT'

        # 计算激进限价 (5% 滑点)
        if side.upper() == 'BUY':
            limit_price = trigger_price * 1.05
        else:
            limit_price = trigger_price * 0.95
        str_limit_price = float(exchange.price_to_precision(symbol, limit_price))

        params_limit = {
            'stopPrice': str_trigger_price,
            'reduceOnly': True,
            'timeInForce': 'GTC',  # 限价单必须有
            'workingType': 'MARK_PRICE'
        }
        # 绝对不传 'closePosition'

        # 再次尝试
        return await exchange.create_order(symbol, type_limit, side, str_amount, str_limit_price, params_limit)


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
            await async_logger(f"⚠️ {position.symbol} 仓位不存在。", "warning")
            await _cancel_sl_tp_orders_async(exchange, full_symbol, async_logger)
            return True

        # 2. 清理旧订单
        await _cancel_sl_tp_orders_async(exchange, full_symbol, async_logger)

        is_long = position.side == i18n.SIDE_LONG
        side_key = "long" if is_long else "short"

        # 3. 检查开关
        if not config.get(f'enable_{side_key}_sl_tp', False):
            return True

        sl_perc = config.get(f'{side_key}_stop_loss_percentage', 0)
        tp_perc = config.get(f'{side_key}_take_profit_percentage', 0)

        tasks: List[Any] = []

        # 止损
        if sl_perc > 0:
            leverage = config.get('leverage', 1)
            sl_ratio = float(sl_perc) / 100 / leverage
            entry_price = position.entry_price

            if is_long:
                target_sl = entry_price * (1 - sl_ratio)
                sl_side = 'sell'
            else:
                target_sl = entry_price * (1 + sl_ratio)
                sl_side = 'buy'

            await async_logger(f"  > 提交 {position.symbol} SL (触发: {target_sl:.4f})...")
            tasks.append(_place_stop_order_ccxt(
                exchange, full_symbol, sl_side, position.contracts,
                target_sl, True, async_logger
            ))

        # 止盈
        if tp_perc > 0:
            leverage = config.get('leverage', 1)
            tp_ratio = float(tp_perc) / 100 / leverage
            entry_price = position.entry_price

            if is_long:
                target_tp = entry_price * (1 + tp_ratio)
                tp_side = 'sell'
            else:
                target_tp = entry_price * (1 - tp_ratio)
                tp_side = 'buy'

            await async_logger(f"  > 提交 {position.symbol} TP (触发: {target_tp:.4f})...")
            tasks.append(_place_stop_order_ccxt(
                exchange, full_symbol, tp_side, position.contracts,
                target_tp, False, async_logger
            ))

        if not tasks: return True

        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = 0
        for res in results:
            if isinstance(res, dict) and res.get('id'):
                success_count += 1
            elif isinstance(res, Exception):
                await async_logger(f"  > ❌ {position.symbol} 失败: {res}", "error")

        if success_count < len(tasks):
            await async_logger(f"⚠️ {position.symbol} SL/TP 不完整", "warning")
        else:
            await async_logger(f"✅ {position.symbol} 完成", "success")

        return success_count == len(tasks)

    except Exception as e:
        await async_logger(f"❌ {position.symbol} 异常: {e}", "error")
        return False


async def cleanup_orphan_sltp_orders_async(exchange: ccxt.binanceusdm, active_symbols: Set[str], async_logger):
    try:
        all_open_orders = await exchange.fetch_open_orders()
        orphan_orders = [
            o for o in all_open_orders
            if (o.get('reduceOnly') or o.get('info', {}).get('closePosition')) and o['symbol'] not in active_symbols
        ]
        if not orphan_orders: return
        await async_logger(f"清理 {len(orphan_orders)} 个无主订单", "warning")
        await asyncio.gather(*[exchange.cancel_order(o['id'], o['symbol']) for o in orphan_orders],
                             return_exceptions=True)
    except:
        pass