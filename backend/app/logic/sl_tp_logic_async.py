# backend/app/logic/sl_tp_logic_async.py (互斥优先版)
import asyncio
from typing import Set, List, Dict, Any

import ccxt.async_support as ccxt

from .exceptions import InterruptedError
from ..config import i18n
from ..models.schemas import Position


async def _force_cancel_all_orders(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    【核弹级清理】直接调用撤销所有订单接口。
    """
    try:
        await exchange.cancel_all_orders(symbol)
        return True
    except Exception as e:
        err_str = str(e)
        if "No orders" not in err_str:
            # 只有真正的错误才打印，没有订单不算错
            print(f"--- [INFO] {symbol} 撤单返回信息: {err_str} ---")
        return True


async def _cancel_sl_tp_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    普通清理 (保留此函数以兼容旧接口调用，但主逻辑主要用 force_cancel)
    """
    return await _force_cancel_all_orders(exchange, symbol, async_logger)


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
    标准止损/止盈下单
    """
    order_type = 'STOP_MARKET' if is_stop_loss else 'TAKE_PROFIT_MARKET'
    price_str = exchange.price_to_precision(symbol, trigger_price)
    amount_str = exchange.amount_to_precision(symbol, amount)

    params = {
        'stopPrice': price_str,
        'reduceOnly': True,
        'workingType': 'MARK_PRICE',
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            return await exchange.create_order(symbol, order_type, side, amount_str, None, params)
        except ccxt.ExchangeError as e:
            err_msg = str(e)

            if '-4130' in err_msg or '-4045' in err_msg or 'limit' in err_msg.lower():
                await _force_cancel_all_orders(exchange, symbol, async_logger)
                await asyncio.sleep(1.0 * (attempt + 1))
                continue

            elif '-4120' in err_msg:
                limit_type = 'STOP' if is_stop_loss else 'TAKE_PROFIT'
                limit_price = trigger_price * (1.05 if side.upper() == 'BUY' else 0.95)
                limit_price_str = exchange.price_to_precision(symbol, limit_price)
                params_limit = {
                    'stopPrice': price_str, 'reduceOnly': True,
                    'timeInForce': 'GTC', 'workingType': 'MARK_PRICE'
                }
                return await exchange.create_order(symbol, limit_type, side, amount_str, limit_price_str, params_limit)

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
    移动止盈下单
    """
    # 允许最大 20% 回调
    rate = max(0.1, min(20.0, float(callback_rate)))
    amount_str = exchange.amount_to_precision(symbol, amount)

    params = {
        'callbackRate': rate,
        'reduceOnly': True,
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            return await exchange.create_order(symbol, 'TRAILING_STOP_MARKET', side, amount_str, None, params)
        except ccxt.ExchangeError as e:
            err_msg = str(e)

            if '-4130' in err_msg or '-4045' in err_msg or 'limit' in err_msg.lower():
                msg = f"--- [RETRY {attempt + 1}] {symbol} 移动止盈冲突/超限，清理中... ---"
                await _force_cancel_all_orders(exchange, symbol, async_logger)
                await asyncio.sleep(1.0 * (attempt + 1))
                continue
            else:
                raise e
        except Exception as e:
            if attempt == max_retries - 1: return e
            await asyncio.sleep(1)

    return False


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
            await async_logger(f"⚠️ {position.symbol} 仓位已平，清理挂单并跳过。", "warning")
            await _force_cancel_all_orders(exchange, full_symbol, async_logger)
            return True

        # 2. 【关键】先强制撤销所有旧订单 (Clean Slate)
        await _force_cancel_all_orders(exchange, full_symbol, async_logger)
        await asyncio.sleep(0.5)  # 等待撤单生效

        if stop_event.is_set(): raise InterruptedError()

        is_long = position.side == i18n.SIDE_LONG
        side_key = "long" if is_long else "short"

        # --- 策略互斥逻辑 ---

        # A. 检查是否开启了移动止盈 (最高优先级)
        enable_trailing = config.get(f'enable_{side_key}_trailing_stop', False)

        if enable_trailing:
            # === 分支 A：移动止盈模式 ===
            # 在此模式下，只挂一个移动止盈单，不挂固定止损/止盈

            callback_rate = config.get(f'{side_key}_trailing_stop_callback_rate', 1.0)
            ts_side = 'sell' if is_long else 'buy'

            # await async_logger(f"  > {position.symbol} 启用移动止盈 (优先)，跳过固定SL/TP。", "info")

            res = await _place_trailing_stop_order(
                exchange, full_symbol, ts_side, position.contracts, callback_rate, async_logger
            )

            if isinstance(res, dict) and res.get('id'):
                await async_logger(f"✅ {position.symbol} 移动止盈设置成功 (Rate:{callback_rate}%)", "success")
                return True
            else:
                await async_logger(f"❌ {position.symbol} 移动止盈设置失败: {res}", "error")
                return False

        else:
            # === 分支 B：固定止损/止盈模式 ===
            # 只有在移动止盈关闭时，才执行这里的逻辑

            tasks_to_run = []

            if config.get(f'enable_{side_key}_sl_tp', False):
                sl_perc = config.get(f'{side_key}_stop_loss_percentage', 0)
                tp_perc = config.get(f'{side_key}_take_profit_percentage', 0)
                entry_price = position.entry_price
                leverage = config.get('leverage', 1)

                # 固定止损
                if sl_perc > 0:
                    sl_ratio = float(sl_perc) / 100 / leverage
                    target_sl = entry_price * (1 - sl_ratio) if is_long else entry_price * (1 + sl_ratio)
                    sl_side = 'sell' if is_long else 'buy'
                    tasks_to_run.append({
                        "name": "SL",
                        "coro": _place_standard_stop_order(exchange, full_symbol, sl_side, position.contracts,
                                                           target_sl, True, async_logger)
                    })

                # 固定止盈
                if tp_perc > 0:
                    tp_ratio = float(tp_perc) / 100 / leverage
                    target_tp = entry_price * (1 + tp_ratio) if is_long else entry_price * (1 - tp_ratio)
                    tp_side = 'sell' if is_long else 'buy'
                    tasks_to_run.append({
                        "name": "TP",
                        "coro": _place_standard_stop_order(exchange, full_symbol, tp_side, position.contracts,
                                                           target_tp, False, async_logger)
                    })

            if not tasks_to_run:
                # await async_logger(f"ℹ️ {position.symbol} 未配置任何策略。", "info")
                return True

            success_count = 0
            for task_info in tasks_to_run:
                if stop_event.is_set(): break
                try:
                    res = await task_info["coro"]
                    if isinstance(res, dict) and res.get('id'):
                        success_count += 1
                    else:
                        await async_logger(f"  > ❌ {position.symbol} {task_info['name']} 失败: {res}", "error")
                except Exception as e:
                    await async_logger(f"  > ❌ {position.symbol} {task_info['name']} 异常: {e}", "error")
                await asyncio.sleep(0.3)

            if success_count == len(tasks_to_run):
                await async_logger(f"✅ {position.symbol} 固定 SL/TP 设置成功", "success")
            else:
                await async_logger(f"⚠️ {position.symbol} 固定 SL/TP 部分成功", "warning")

            return success_count == len(tasks_to_run)

    except Exception as e:
        await async_logger(f"❌ {position.symbol} 流程异常: {e}", "error")
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