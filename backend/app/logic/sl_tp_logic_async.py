# backend/app/logic/sl_tp_logic_async.py (底层直连版 - 绕过 CCXT 封装)
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


async def _send_raw_order(
        exchange: ccxt.binanceusdm,
        market_id: str,  # 例如 "BTCUSDT"
        side: str,  # "BUY" or "SELL"
        order_type: str,  # "STOP_MARKET", "STOP", "TAKE_PROFIT_MARKET", "TAKE_PROFIT"
        qty: float,
        stop_price: float,
        price: float = None,  # 仅限价单需要
        async_logger=None
):
    """
    直接调用 private_post_order，完全绕过 ccxt 的 create_order 封装。
    """

    # 1. 构建最原始的参数字典
    params = {
        'symbol': market_id,
        'side': side.upper(),
        'type': order_type,
        'quantity': exchange.amount_to_precision(market_id, qty),
        'stopPrice': exchange.price_to_precision(market_id, stop_price),
        'reduceOnly': 'true',  # 必须是字符串 'true'
        'workingType': 'MARK_PRICE'
    }

    # 2. 如果是限价单 (STOP / TAKE_PROFIT)，必须加 price 和 timeInForce
    if order_type in ['STOP', 'TAKE_PROFIT']:
        if price is None:
            raise ValueError("Limit orders require a price")
        params['price'] = exchange.price_to_precision(market_id, price)
        params['timeInForce'] = 'GTC'

    # 3. 打印核弹级日志
    if async_logger:
        log_str = json.dumps(params, indent=2)
        print(f"--- [RAW REQUEST] Sending to Binance ---\n{log_str}\n------------------------------------")

    # 4. 发送请求
    try:
        return await exchange.private_post_order(params)
    except Exception as e:
        # 把原始错误抛出去，并在外部捕获
        raise e


async def _place_stop_order_robust(
        exchange: ccxt.binanceusdm,
        full_symbol: str,
        side: str,
        amount: float,
        trigger_price: float,
        is_stop_loss: bool,
        async_logger
):
    """
    健壮的下单流程：
    1. 获取 market_id (去除 / )
    2. 尝试 STOP_MARKET (市价止损)
    3. 失败则尝试 STOP (限价止损)
    """

    # 获取原始 symbol id (例如 ETH/USDT:USDT -> ETHUSDT)
    market = exchange.market(full_symbol)
    market_id = market['id']

    # 确定类型字符串
    if is_stop_loss:
        market_type = 'STOP_MARKET'
        limit_type = 'STOP'
    else:
        market_type = 'TAKE_PROFIT_MARKET'
        limit_type = 'TAKE_PROFIT'

    # --- 尝试 1: 市价止损 (最优先) ---
    try:
        # await async_logger(f"  > 尝试市价止损 {full_symbol} (Type={market_type})...")
        return await _send_raw_order(exchange, market_id, side, market_type, amount, trigger_price,
                                     async_logger=async_logger)

    except Exception as e:
        err_str = str(e)
        # 如果是 -4120 (Order type not supported) 或其他特定错误，降级
        if '-4120' in err_str or 'Order type' in err_str:
            print(f"--- [DEBUG] {full_symbol} 市价止损不支持，降级为限价止损 ---")

            # 计算限价单价格 (确保成交的激进价格)
            # 买入: 触发价 * 1.05
            # 卖出: 触发价 * 0.95
            if side.upper() == 'BUY':
                limit_price = trigger_price * 1.05
            else:
                limit_price = trigger_price * 0.95

            # --- 尝试 2: 限价止损 (降级方案) ---
            try:
                return await _send_raw_order(exchange, market_id, side, limit_type, amount, trigger_price,
                                             price=limit_price, async_logger=async_logger)
            except Exception as e2:
                # 如果还失败，记录详细日志
                await async_logger(f"  > ❌ {full_symbol} 最终失败: {e2}", "error")
                return None
        else:
            # 其他错误 (如余额不足，最小交易额不足) 直接报错
            await async_logger(f"  > ❌ {full_symbol} 下单异常: {e}", "error")
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

            await async_logger(f"  > 准备提交 {position.symbol} SL (Price: {target_sl_price:.4f})...")

            # 这里的 asyncio.create_task 是为了并行，但为了调试清晰，这里直接调
            tasks.append(_place_stop_order_robust(
                exchange, full_symbol, sl_side, position.contracts,
                target_sl_price, True, async_logger
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

            await async_logger(f"  > 准备提交 {position.symbol} TP (Price: {target_tp_price:.4f})...")

            tasks.append(_place_stop_order_robust(
                exchange, full_symbol, tp_side, position.contracts,
                target_tp_price, False, async_logger
            ))

        if not tasks:
            return True

        # 4. 执行
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for res in results if res is not None)
        total_tasks = len(tasks)

        if success_count < total_tasks:
            await async_logger(f"⚠️ {position.symbol} SL/TP 设置不完整 ({success_count}/{total_tasks})", "warning")
        else:
            await async_logger(f"✅ {position.symbol} 止盈/止损校准成功！", "success")

        return success_count == total_tasks

    except InterruptedError:
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