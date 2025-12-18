# backend/app/logic/sl_tp_logic_async.py (严格对照文档-分层重试版)
import asyncio
import json
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
            if (order.get('reduceOnly') or order.get('info', {}).get('closePosition') == 'true')
               and order['type'] in ['STOP', 'TAKE_PROFIT', 'STOP_MARKET', 'TAKE_PROFIT_MARKET']
        ]
        if not orders_to_cancel:
            return True

        tasks = [exchange.cancel_order(order['id'], symbol) for order in orders_to_cancel]
        await asyncio.gather(*tasks, return_exceptions=True)
        return True
    except Exception as e:
        await async_logger(f"  > ❌ 清理旧订单失败: {e}", "error")
        return False


async def _submit_stop_order(
        exchange: ccxt.binanceusdm,
        full_symbol: str,
        side: str,
        amount: float,
        trigger_price: float,
        is_stop_loss: bool,
        async_logger
):
    """
    核心下单函数：
    1. 优先尝试 STOP_MARKET + closePosition=true (最简参数，不传 quantity/price/timeInForce)
    2. 失败则降级为 STOP + reduceOnly=true (全参数，模拟市价)
    """

    # 获取原生 Symbol (如 "BTCUSDT")
    market = exchange.market(full_symbol)
    raw_symbol = market['id']

    # 格式化价格和数量
    str_stop_price = exchange.price_to_precision(full_symbol, trigger_price)
    str_qty = exchange.amount_to_precision(full_symbol, amount)

    # ==========================================
    # 方案 A: 市价止损/止盈 (文档对应的 STOP_MARKET)
    # 关键：使用 closePosition=true，不传数量和 TIF
    # ==========================================
    type_market = 'STOP_MARKET' if is_stop_loss else 'TAKE_PROFIT_MARKET'

    params_market = {
        'symbol': raw_symbol,
        'side': side.upper(),
        'type': type_market,
        'stopPrice': str_stop_price,
        'closePosition': 'true',  # 触发后平掉所有仓位
        'workingType': 'MARK_PRICE'
    }
    # 注意：这里绝对没有 timeInForce, price, quantity, reduceOnly

    try:
        # print(f"--- [DEBUG A] {raw_symbol} 尝试市价全平: {params_market}")
        return await exchange.private_post_order(params_market)

    except Exception as e:
        err_str = str(e)
        # 如果报错 -4120 (不支持) 或 -2021 (立刻触发) 以外的错误，尝试方案B
        # print(f"--- [DEBUG A 失败] {raw_symbol}: {err_str} -> 尝试方案B")

        # ==========================================
        # 方案 B: 限价止损/止盈 (文档对应的 STOP)
        # 关键：使用 reduceOnly=true，必须传数量、价格、TIF
        # ==========================================
        type_limit = 'STOP' if is_stop_loss else 'TAKE_PROFIT'

        # 计算激进限价 (5% 滑点)
        if side.upper() == 'BUY':
            limit_price = trigger_price * 1.05
        else:
            limit_price = trigger_price * 0.95
        str_limit_price = exchange.price_to_precision(full_symbol, limit_price)

        params_limit = {
            'symbol': raw_symbol,
            'side': side.upper(),
            'type': type_limit,
            'quantity': str_qty,  # 限价单必须有数量
            'price': str_limit_price,  # 限价单必须有价格
            'stopPrice': str_stop_price,
            'reduceOnly': 'true',  # 必须是字符串
            'timeInForce': 'GTC',  # 限价单必须有 TIF
            'workingType': 'MARK_PRICE'
        }

        # print(f"--- [DEBUG B] {raw_symbol} 尝试限价模拟: {params_limit}")

        try:
            return await exchange.private_post_order(params_limit)
        except Exception as e2:
            await async_logger(f"  > ❌ {full_symbol} 最终下单失败: {e2}", "error")
            return None


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
                sl_side = 'SELL'
            else:
                target_sl_price = entry_price * (1 + sl_ratio)
                sl_side = 'BUY'

            await async_logger(f"  > 准备提交 {position.symbol} SL (触发: {target_sl_price:.4f})")
            tasks.append(_submit_stop_order(
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
                tp_side = 'SELL'
            else:
                target_tp_price = entry_price * (1 - tp_ratio)
                tp_side = 'BUY'

            await async_logger(f"  > 准备提交 {position.symbol} TP (触发: {target_tp_price:.4f})")
            tasks.append(_submit_stop_order(
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
            if isinstance(res, dict) and res.get('orderId'):
                success_count += 1
            elif isinstance(res, Exception):
                pass  # 错误已在内部打印

        if success_count < total_tasks:
            await async_logger(f"⚠️ {position.symbol} SL/TP 不完整 ({success_count}/{total_tasks})", "warning")
        else:
            await async_logger(f"✅ {position.symbol} 校准成功！", "success")

        return success_count == total_tasks

    except InterruptedError:
        return False
    except Exception as e:
        await async_logger(f"❌ 设置 {position.symbol} SL/TP 严重错误: {e}", "error")
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