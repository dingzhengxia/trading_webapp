# backend/app/logic/sl_tp_logic_async.py (最终暴力修复版)
import asyncio
from typing import Set, List, Dict, Any

import ccxt.async_support as ccxt

from .exceptions import InterruptedError
from ..config import i18n
from ..models.schemas import Position


async def _force_cancel_all_orders(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    【核弹级清理】直接调用撤销所有订单接口。
    用于解决 -4045 (Reach max stop order limit) 问题。
    """
    try:
        # 尝试调用 cancel_all_orders
        await exchange.cancel_all_orders(symbol)
        # await async_logger(f"⚠️ 已强制撤销 {symbol} 所有挂单以腾出空间。", "warning")
        return True
    except Exception as e:
        # 如果没有订单可撤，可能会报错，忽略即可
        return True


async def _cancel_sl_tp_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    普通清理：只清理止盈止损类订单
    """
    try:
        open_orders = await exchange.fetch_open_orders(symbol)
        orders_to_cancel = [
            order for order in open_orders
            if order['type'] in [
                'STOP', 'TAKE_PROFIT', 'STOP_MARKET', 'TAKE_PROFIT_MARKET',
                'STOP_LOSS', 'STOP_LOSS_LIMIT', 'TAKE_PROFIT_LIMIT',
                'TRAILING_STOP_MARKET'
            ]
        ]
        if not orders_to_cancel: return True

        # 并发取消
        await asyncio.gather(*[exchange.cancel_order(o['id'], symbol) for o in orders_to_cancel],
                             return_exceptions=True)
        return True
    except Exception:
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
    标准止损/止盈下单 (带强力重试)
    """
    order_type = 'STOP_MARKET' if is_stop_loss else 'TAKE_PROFIT_MARKET'
    price_str = exchange.price_to_precision(symbol, trigger_price)
    amount_str = exchange.amount_to_precision(symbol, amount)

    params = {
        'stopPrice': price_str,
        'closePosition': True,
        'workingType': 'MARK_PRICE',
    }
    if 'reduceOnly' in params: del params['reduceOnly']

    # --- 循环重试机制 ---
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return await exchange.create_order(symbol, order_type, side, amount_str, None, params)
        except ccxt.ExchangeError as e:
            err_msg = str(e)

            # 遇到 冲突(-4130) 或 超限(-4045)
            if '-4130' in err_msg or '-4045' in err_msg or 'limit' in err_msg.lower():
                # print(f"--- [RETRY {attempt+1}] {symbol} 固定止损冲突/超限，强制清理... ---")
                # 强制清理所有订单
                await _force_cancel_all_orders(exchange, symbol, async_logger)
                # 等待时间随重试次数递增 (1.5s, 3.0s, 4.5s)
                await asyncio.sleep(1.5 * (attempt + 1))
                continue  # 进行下一次尝试

            # 遇到不支持市价单 (-4120) -> 降级为限价
            elif '-4120' in err_msg:
                # print(f"--- [INFO] {symbol} 降级为限价止损 ---")
                limit_type = 'STOP' if is_stop_loss else 'TAKE_PROFIT'
                limit_price = trigger_price * (1.05 if side.upper() == 'BUY' else 0.95)
                limit_price_str = exchange.price_to_precision(symbol, limit_price)
                params_limit = {
                    'stopPrice': price_str, 'reduceOnly': True,
                    'timeInForce': 'GTC', 'workingType': 'MARK_PRICE'
                }
                return await exchange.create_order(symbol, limit_type, side, amount_str, limit_price_str, params_limit)

            # 其他错误直接抛出
            else:
                raise e
        except Exception as e:
            if attempt == max_retries - 1: raise e
            await asyncio.sleep(1)

    return False


async def _place_trailing_stop_order(
        exchange: ccxt.binanceusdm,
        symbol: str,
        side: str,
        amount: float,
        callback_rate: float,
        async_logger
):
    """
    移动止盈下单 (带强力重试)
    """
    # 这里的上限已经放宽到 20.0，以满足你的 10% 需求
    rate = max(0.1, min(20.0, float(callback_rate)))
    amount_str = exchange.amount_to_precision(symbol, amount)

    params = {
        'callbackRate': rate,
        'reduceOnly': True,
    }

    # --- 循环重试机制 ---
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return await exchange.create_order(symbol, 'TRAILING_STOP_MARKET', side, amount_str, None, params)
        except ccxt.ExchangeError as e:
            err_msg = str(e)

            # 遇到 冲突(-4130) 或 超限(-4045)
            if '-4130' in err_msg or '-4045' in err_msg or 'limit' in err_msg.lower():
                msg = f"--- [RETRY {attempt + 1}] {symbol} 移动止盈冲突/超限，正在强力清理... ---"
                print(msg)
                if attempt == 0: await async_logger(msg, "warning")

                # 强制清理该币种所有订单！
                await _force_cancel_all_orders(exchange, symbol, async_logger)

                # 等待时间递增，给币安撮合引擎一点时间
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            else:
                raise e
        except Exception as e:
            # 未知错误
            await async_logger(f"⚠️ {symbol} 移动止盈未知错误: {e}", "error")
            if attempt == max_retries - 1: return e
            await asyncio.sleep(1)

    return False


async def set_tp_sl_for_position_async(exchange: ccxt.binanceusdm, position: Position, config: dict, async_logger,
                                       stop_event: asyncio.Event) -> bool:
    full_symbol = position.full_symbol
    if stop_event.is_set(): raise InterruptedError()

    try:
        # 1. 检查仓位是否存在
        live_positions_raw = await exchange.fetch_positions([full_symbol])
        live_pos = next(
            (p for p in live_positions_raw if p['symbol'] == full_symbol and float(p.get('contracts', 0)) != 0), None)

        if not live_pos:
            await async_logger(f"⚠️ {position.symbol} 仓位已平，跳过。", "warning")
            # 顺手清理一下挂单
            await _force_cancel_all_orders(exchange, full_symbol, async_logger)
            return True

        # 2. 初始清理：直接强制撤单，保证环境干净
        await _force_cancel_all_orders(exchange, full_symbol, async_logger)
        await asyncio.sleep(0.5)  # 稍微等待

        if stop_event.is_set(): raise InterruptedError()

        is_long = position.side == i18n.SIDE_LONG
        side_key = "long" if is_long else "short"

        tasks_to_run = []

        # --- 3. 准备固定 SL/TP ---
        if config.get(f'enable_{side_key}_sl_tp', False):
            sl_perc = config.get(f'{side_key}_stop_loss_percentage', 0)
            tp_perc = config.get(f'{side_key}_take_profit_percentage', 0)
            entry_price = position.entry_price
            leverage = config.get('leverage', 1)

            if sl_perc > 0:
                sl_ratio = float(sl_perc) / 100 / leverage
                target_sl = entry_price * (1 - sl_ratio) if is_long else entry_price * (1 + sl_ratio)
                sl_side = 'sell' if is_long else 'buy'

                tasks_to_run.append({
                    "name": "SL",
                    "coro": _place_standard_stop_order(exchange, full_symbol, sl_side, position.contracts, target_sl,
                                                       True, async_logger)
                })

            if tp_perc > 0:
                tp_ratio = float(tp_perc) / 100 / leverage
                target_tp = entry_price * (1 + tp_ratio) if is_long else entry_price * (1 - tp_ratio)
                tp_side = 'sell' if is_long else 'buy'

                tasks_to_run.append({
                    "name": "TP",
                    "coro": _place_standard_stop_order(exchange, full_symbol, tp_side, position.contracts, target_tp,
                                                       False, async_logger)
                })

        # --- 4. 准备移动止盈 (Trailing) ---
        if config.get(f'enable_{side_key}_trailing_stop', False):
            callback_rate = config.get(f'{side_key}_trailing_stop_callback_rate', 1.0)
            ts_side = 'sell' if is_long else 'buy'
            tasks_to_run.append({
                "name": "Trailing",
                "coro": _place_trailing_stop_order(exchange, full_symbol, ts_side, position.contracts, callback_rate,
                                                   async_logger)
            })

        if not tasks_to_run: return True

        # 5. 顺序执行，间隔稍微拉大
        success_count = 0
        for task_info in tasks_to_run:
            if stop_event.is_set(): break

            task_name = task_info["name"]

            # 为了减少日志刷屏，仅在出错时详细打印，或者汇总打印
            # await async_logger(f"  > 提交 {position.symbol} {task_name}...", "info")

            try:
                res = await task_info["coro"]

                if isinstance(res, dict) and res.get('id'):
                    success_count += 1
                elif isinstance(res, Exception):
                    # 如果经过多次重试依然失败
                    await async_logger(f"  > ❌ {position.symbol} {task_name} 最终失败: {res}", "error")
            except Exception as e:
                await async_logger(f"  > ❌ {position.symbol} {task_name} 异常: {e}", "error")

            # 这里的延时很重要，给撤单逻辑一点时间，也防止触发频率限制
            await asyncio.sleep(0.3)

        if success_count < len(tasks_to_run):
            await async_logger(f"⚠️ {position.symbol} 策略部分生效 ({success_count}/{len(tasks_to_run)})", "warning")
        else:
            await async_logger(f"✅ {position.symbol} 策略全部设置成功", "success")

        return success_count == len(tasks_to_run)

    except Exception as e:
        await async_logger(f"❌ {position.symbol} 流程异常: {e}", "error")
        return False


async def cleanup_orphan_sltp_orders_async(exchange: ccxt.binanceusdm, active_symbols: Set[str], async_logger):
    try:
        # 使用 fetch_open_orders 不带参数可能比较慢，但为了清理无主订单是必须的
        all_open_orders = await exchange.fetch_open_orders()
        orphan_orders = [
            o for o in all_open_orders
            if (o.get('reduceOnly') or o.get('info', {}).get('closePosition')) and o['symbol'] not in active_symbols
        ]
        if not orphan_orders: return
        await async_logger(f"清理 {len(orphan_orders)} 个无主订单", "warning")

        # 针对无主订单，也使用 cancel_order 逐个清理
        await asyncio.gather(*[exchange.cancel_order(o['id'], o['symbol']) for o in orphan_orders],
                             return_exceptions=True)
    except:
        pass