# backend/app/logic/sl_tp_logic_async.py (完整代码)
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
        # 获取未完成的订单
        open_orders = await exchange.fetch_open_orders(symbol)

        # 筛选条件单
        # 只要是 STOP, TAKE_PROFIT, TRAILING_STOP 相关的都清理
        orders_to_cancel = [
            order for order in open_orders
            if order['type'] in [
                'STOP', 'TAKE_PROFIT', 'STOP_MARKET', 'TAKE_PROFIT_MARKET',
                'STOP_LOSS', 'STOP_LOSS_LIMIT', 'TAKE_PROFIT_LIMIT',
                'TRAILING_STOP_MARKET'  # --- 新增: 清理移动止盈单 ---
            ]
        ]

        if not orders_to_cancel:
            return True

        # 批量取消
        tasks = [exchange.cancel_order(order['id'], symbol) for order in orders_to_cancel]
        await asyncio.gather(*tasks, return_exceptions=True)
        return True
    except Exception as e:
        # 即使清理失败通常也不影响主流程
        return True


async def _place_standard_stop_order(
        exchange: ccxt.binanceusdm,
        symbol: str,
        side: str,
        amount: float,
        trigger_price: float,
        is_stop_loss: bool,
        async_logger
):
    """
    使用 CCXT 最标准的 create_order 接口。
    对应币安功能：【市价止损/止盈】+【只平仓(Close Position)】
    增加了自动错误重试机制 (-4130 冲突清理 和 -4120 降级)。
    """

    # 1. 确定标准的订单类型
    order_type = 'STOP_MARKET' if is_stop_loss else 'TAKE_PROFIT_MARKET'

    # 2. 精度处理
    price_str = exchange.price_to_precision(symbol, trigger_price)
    amount_str = exchange.amount_to_precision(symbol, amount)

    # 3. 构造 params
    params = {
        'stopPrice': price_str,  # 触发价格
        'closePosition': True,  # 【关键】开启“只平仓”，自动平掉所有仓位
        'workingType': 'MARK_PRICE',  # 推荐使用标记价格
    }

    if 'reduceOnly' in params:
        del params['reduceOnly']

    # --- 内部执行函数，用于支持重试逻辑 ---
    async def _execute_create():
        try:
            return await exchange.create_order(symbol, order_type, side, amount_str, None, params)
        except ccxt.ExchangeError as e:
            err_msg = str(e)

            # 处理 -4130 冲突错误
            if '-4130' in err_msg:
                print(f"--- [RETRY] {symbol} 遇到订单冲突 (-4130)，正在清理并重试... ---")
                await _cancel_sl_tp_orders_async(exchange, symbol, async_logger)
                await asyncio.sleep(0.5)
                return await exchange.create_order(symbol, order_type, side, amount_str, None, params)

            # 处理 -4120 不支持市价单错误 (降级为限价)
            elif '-4120' in err_msg:
                print(f"--- [INFO] {symbol} 不支持市价止损，切换为标准限价止损 ---")

                # 切换为限价类型
                limit_type = 'STOP' if is_stop_loss else 'TAKE_PROFIT'

                # 计算一个必定成交的限价 (5% 滑点)
                if side.upper() == 'BUY':
                    limit_price = trigger_price * 1.05
                else:
                    limit_price = trigger_price * 0.95
                limit_price_str = exchange.price_to_precision(symbol, limit_price)

                params_limit = {
                    'stopPrice': price_str,
                    'reduceOnly': True,
                    'timeInForce': 'GTC',
                    'workingType': 'MARK_PRICE'
                }

                return await exchange.create_order(symbol, limit_type, side, amount_str, limit_price_str, params_limit)

            else:
                raise e

    return await _execute_create()


async def _place_trailing_stop_order(
        exchange: ccxt.binanceusdm,
        symbol: str,
        side: str,
        amount: float,
        callback_rate: float,
        async_logger
):
    """
    提交移动止盈止损订单 (Trailing Stop)
    注意：Binance 要求 callbackRate 范围通常是 0.1% 到 5%
    """
    # 确保回调率在有效范围内 (0.1 - 5.0)
    rate = max(0.1, min(5.0, float(callback_rate)))

    amount_str = exchange.amount_to_precision(symbol, amount)

    params = {
        'callbackRate': rate,
        'reduceOnly': True,  # 移动止盈必须是只减仓
        # 'workingType': 'MARK_PRICE' # 默认就是MARK_PRICE
    }

    try:
        # type='TRAILING_STOP_MARKET'
        return await exchange.create_order(symbol, 'TRAILING_STOP_MARKET', side, amount_str, None, params)
    except Exception as e:
        await async_logger(f"⚠️ {symbol} 移动止盈下单失败 (Rate:{rate}%): {e}", "error")
        return e


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
            await async_logger(f"⚠️ {position.symbol} 仓位已平，跳过。", "warning")
            await _cancel_sl_tp_orders_async(exchange, full_symbol, async_logger)
            return True

        # 2. 清理旧订单
        await _cancel_sl_tp_orders_async(exchange, full_symbol, async_logger)
        if stop_event.is_set(): raise InterruptedError()

        is_long = position.side == i18n.SIDE_LONG
        side_key = "long" if is_long else "short"

        tasks: List[Any] = []

        # --- 3. 固定止盈止损 (Stop Loss / Take Profit) ---
        if config.get(f'enable_{side_key}_sl_tp', False):

            sl_perc = config.get(f'{side_key}_stop_loss_percentage', 0)
            tp_perc = config.get(f'{side_key}_take_profit_percentage', 0)

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

                await async_logger(f"  > 提交 {position.symbol} SL ({target_sl:.4f})...")
                tasks.append(_place_standard_stop_order(
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

                await async_logger(f"  > 提交 {position.symbol} TP ({target_tp:.4f})...")
                tasks.append(_place_standard_stop_order(
                    exchange, full_symbol, tp_side, position.contracts,
                    target_tp, False, async_logger
                ))

        # --- 4. 移动止盈 (Trailing Stop) ---
        enable_trailing = config.get(f'enable_{side_key}_trailing_stop', False)
        callback_rate = config.get(f'{side_key}_trailing_stop_callback_rate', 1.0)

        if enable_trailing:
            # 做多仓位，平仓方向是 sell；做空仓位，平仓方向是 buy
            ts_side = 'sell' if is_long else 'buy'

            await async_logger(f"  > 提交 {position.symbol} 移动止盈 (回调率: {callback_rate}%)...")
            tasks.append(_place_trailing_stop_order(
                exchange, full_symbol, ts_side, position.contracts, callback_rate, async_logger
            ))

        if not tasks: return True

        # 5. 执行
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = 0
        for res in results:
            if isinstance(res, dict) and res.get('id'):
                success_count += 1
            elif isinstance(res, Exception):
                await async_logger(f"  > ❌ {position.symbol} 失败: {res}", "error")

        if success_count < len(tasks):
            await async_logger(f"⚠️ {position.symbol} SL/TP/TS 不完整", "warning")
        else:
            await async_logger(f"✅ {position.symbol} 订单设置成功", "success")

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