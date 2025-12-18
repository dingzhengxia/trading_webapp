# backend/app/logic/sl_tp_logic_async.py (回归 CCXT 最标准接口 - 终极规范版)
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
        # 只要是 STOP 或 TAKE_PROFIT 相关的都清理
        orders_to_cancel = [
            order for order in open_orders
            if order['type'] in ['STOP', 'TAKE_PROFIT', 'STOP_MARKET', 'TAKE_PROFIT_MARKET', 'STOP_LOSS',
                                 'STOP_LOSS_LIMIT', 'TAKE_PROFIT_LIMIT']
        ]

        if not orders_to_cancel:
            return True

        # 批量取消
        tasks = [exchange.cancel_order(order['id'], symbol) for order in orders_to_cancel]
        await asyncio.gather(*tasks, return_exceptions=True)
        return True
    except Exception as e:
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
    这是最符合用户直觉和文档规范的下单方式。
    """

    # 1. 确定标准的订单类型 (Standard Enum)
    # 币安合约推荐使用 STOP_MARKET 和 TAKE_PROFIT_MARKET 来做单纯的止损止盈
    order_type = 'STOP_MARKET' if is_stop_loss else 'TAKE_PROFIT_MARKET'

    # 2. 精度处理
    price_str = exchange.price_to_precision(symbol, trigger_price)
    # 注意：使用 closePosition=True 时，币安其实忽略数量，但 ccxt 的 create_order 签名需要传一个值
    amount_str = exchange.amount_to_precision(symbol, amount)

    # 3. 构造 params (这是 CCXT 传递额外参数的标准方式)
    params = {
        'stopPrice': price_str,  # 触发价格
        'closePosition': True,  # 【关键】开启“只平仓”，自动平掉所有仓位
        'workingType': 'MARK_PRICE',  # 推荐使用标记价格
    }

    # 【重要】为了避免 -1106 或 -4120 错误，必须显式清理掉冲突参数
    # 如果使用了 closePosition，就绝对不能有 reduceOnly
    if 'reduceOnly' in params:
        del params['reduceOnly']

    # 调试日志
    # print(f"--- [STANDARD] {symbol} {side} {order_type} @ {price_str} ---")

    try:
        # 调用标准接口
        # create_order(symbol, type, side, amount, price, params)
        # 市价单 price 传 None
        return await exchange.create_order(symbol, order_type, side, amount_str, None, params)

    except ccxt.ExchangeError as e:
        err_msg = str(e)

        # 如果还是报 -4120，说明该交易对暂不支持 STOP_MARKET，降级为 STOP (限价)
        if '-4120' in err_msg:
            print(f"--- [INFO] {symbol} 不支持市价止损，切换为标准限价止损 ---")

            # 切换为限价类型
            limit_type = 'STOP' if is_stop_loss else 'TAKE_PROFIT'

            # 计算一个必定成交的限价 (5% 滑点)
            if side.upper() == 'BUY':
                limit_price = trigger_price * 1.05
            else:
                limit_price = trigger_price * 0.95
            limit_price_str = exchange.price_to_precision(symbol, limit_price)

            # 限价单参数调整
            params_limit = {
                'stopPrice': price_str,
                'reduceOnly': True,  # 限价单不支持 closePosition，必须用 reduceOnly
                'timeInForce': 'GTC',  # 限价单必须有 GTC
                'workingType': 'MARK_PRICE'
            }

            return await exchange.create_order(symbol, limit_type, side, amount_str, limit_price_str, params_limit)

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
            await async_logger(f"⚠️ {position.symbol} 仓位已平，跳过。", "warning")
            await _cancel_sl_tp_orders_async(exchange, full_symbol, async_logger)
            return True

        # 2. 清理旧订单
        await _cancel_sl_tp_orders_async(exchange, full_symbol, async_logger)
        if stop_event.is_set(): raise InterruptedError()

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

        if not tasks: return True

        # 4. 执行
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
            await async_logger(f"✅ {position.symbol} 设置成功", "success")

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