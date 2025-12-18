# backend/app/logic/sl_tp_logic_async.py (回归 CCXT 标准接口 - 智能降级版)
import asyncio
from typing import Set, List, Dict, Any

import ccxt.async_support as ccxt

from .exceptions import InterruptedError
from ..config import i18n
from ..models.schemas import Position


async def _cancel_sl_tp_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    清理旧订单
    """
    try:
        open_orders = await exchange.fetch_open_orders(symbol)
        orders_to_cancel = [
            order for order in open_orders
            if (order.get('reduceOnly') or order.get('info', {}).get('reduceOnly'))
               and order['type'] in ['STOP', 'TAKE_PROFIT', 'STOP_MARKET', 'TAKE_PROFIT_MARKET']
        ]
        if not orders_to_cancel:
            return True

        tasks = [exchange.cancel_order(order['id'], symbol) for order in orders_to_cancel]
        await asyncio.gather(*tasks, return_exceptions=True)
        return True
    except Exception as e:
        await async_logger(f"  > ❌ 为 {symbol} 清理SL/TP订单时出错: {e}", "error")
        return False


async def _place_order_standard_ccxt(
        exchange: ccxt.binanceusdm,
        symbol: str,
        side: str,
        amount: float,
        trigger_price: float,
        is_stop_loss: bool,
        async_logger
):
    """
    使用 CCXT 标准 create_order 方法。
    策略：
    1. 先试 STOP_MARKET (参数极简)。
    2. 报错则试 STOP (限价单，参数完整)。
    """

    # 1. 准备数据
    # 精度处理：价格和数量
    str_trigger_price = float(exchange.price_to_precision(symbol, trigger_price))
    str_amount = float(exchange.amount_to_precision(symbol, amount))

    # ==========================================
    # 尝试 A: 标准市价止损 (STOP_MARKET)
    # 规则：params 中只能有 stopPrice 和 reduceOnly。严禁 price 和 timeInForce。
    # ==========================================
    market_type = 'STOP_MARKET' if is_stop_loss else 'TAKE_PROFIT_MARKET'

    params_market = {
        'stopPrice': str_trigger_price,
        'reduceOnly': True,
        'workingType': 'MARK_PRICE'
    }

    try:
        # print(f"--- [DEBUG] 尝试市价 {symbol}: {market_type}, {params_market}")
        return await exchange.create_order(symbol, market_type, side, str_amount, None, params_market)

    except ccxt.ExchangeError as e:
        error_msg = str(e)

        # 如果报错 -4120 (Order type not supported) 或其他不支持的错误
        if '-4120' in error_msg or 'Order type' in error_msg:
            # print(f"--- [DEBUG] 市价不支持，降级为限价 {symbol} ---")

            # ==========================================
            # 尝试 B: 限价止损 (STOP / TAKE_PROFIT)
            # 规则：必须有 price (第5个参数) 和 timeInForce。
            # ==========================================
            limit_type = 'STOP' if is_stop_loss else 'TAKE_PROFIT'

            # 计算激进限价 (5% 滑点)
            if side.upper() == 'BUY':
                raw_limit = trigger_price * 1.05
            else:
                raw_limit = trigger_price * 0.95

            str_limit_price = float(exchange.price_to_precision(symbol, raw_limit))

            params_limit = {
                'stopPrice': str_trigger_price,
                'reduceOnly': True,
                'timeInForce': 'GTC',  # 限价单必须
                'workingType': 'MARK_PRICE'
            }

            # 再次尝试，这次带上 price
            return await exchange.create_order(symbol, limit_type, side, str_amount, str_limit_price, params_limit)

        else:
            # 其他错误 (如 -2021 立即触发, -4061 模式不对) 直接抛出
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
            await async_logger(f"⚠️ {position.symbol} 仓位不存在。", "warning")
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
                target_sl_price = entry_price * (1 - sl_ratio)
                sl_side = 'sell'
            else:
                target_sl_price = entry_price * (1 + sl_ratio)
                sl_side = 'buy'

            await async_logger(f"  > 提交 {position.symbol} SL (触发: {target_sl_price:.4f})...")
            tasks.append(_place_order_standard_ccxt(
                exchange, full_symbol, sl_side, position.contracts,
                target_sl_price, is_stop_loss=True, async_logger=async_logger
            ))

        # 止盈
        if tp_perc > 0:
            leverage = config.get('leverage', 1)
            tp_ratio = float(tp_perc) / 100 / leverage
            entry_price = position.entry_price

            if is_long:
                target_tp_price = entry_price * (1 + tp_ratio)
                tp_side = 'sell'
            else:
                target_tp_price = entry_price * (1 - tp_ratio)
                tp_side = 'buy'

            await async_logger(f"  > 提交 {position.symbol} TP (触发: {target_tp_price:.4f})...")
            tasks.append(_place_order_standard_ccxt(
                exchange, full_symbol, tp_side, position.contracts,
                target_tp_price, is_stop_loss=False, async_logger=async_logger
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
                await async_logger(f"  > ❌ {position.symbol} 失败: {res}", "error")

        if success_count < total_tasks:
            await async_logger(f"⚠️ {position.symbol} SL/TP 不完整 ({success_count}/{total_tasks})", "warning")
        else:
            await async_logger(f"✅ {position.symbol} 校准成功！", "success")

        return success_count == total_tasks

    except InterruptedError:
        return False
    except Exception as e:
        await async_logger(f"❌ {position.symbol} 异常: {e}", "error")
        return False


async def cleanup_orphan_sltp_orders_async(exchange: ccxt.binanceusdm, active_symbols: Set[str], async_logger):
    try:
        all_open_orders = await exchange.fetch_open_orders()
        orphan_orders = [
            order for order in all_open_orders
            if order.get('reduceOnly') and order['symbol'] not in active_symbols
        ]
        if not orphan_orders:
            return
        await async_logger(f"清理 {len(orphan_orders)} 个无主订单...", "warning")
        tasks = [exchange.cancel_order(order['id'], order['symbol']) for order in orphan_orders]
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception:
        pass