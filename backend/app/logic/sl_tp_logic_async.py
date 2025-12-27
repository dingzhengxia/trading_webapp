# backend/app/logic/sl_tp_logic_async.py (调试诊断版)
import asyncio
from typing import Set, List, Dict, Any

import ccxt.async_support as ccxt

from .exceptions import InterruptedError
from ..config import i18n
from ..models.schemas import Position


async def _ensure_no_open_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    【严防死守清理模式】
    1. 查单 -> 2. 有单就撤 -> 3. 再查 -> 4. 还不干净？报错并返回 False。
    绝不吞掉任何错误。
    """
    max_retries = 5
    for i in range(max_retries):
        try:
            # 1. 查询 (带日志)
            # print(f"--- [DEBUG] {symbol} 第 {i+1} 次检查挂单... ---")
            open_orders = await exchange.fetch_open_orders(symbol)

            if len(open_orders) == 0:
                if i > 0:
                    await async_logger(f"✅ {symbol} 挂单已清零。", "info")
                return True

            # 2. 发现残留，开始清理
            if i == 0:
                print(f"--- [CLEANUP] {symbol} 现有 {len(open_orders)} 个挂单，开始清理... ---")

            # 3. 尝试 Cancel All
            try:
                await exchange.cancel_all_orders(symbol)
            except Exception as e:
                # 只有 "No orders" 错误是可以原谅的，其他错误必须打印
                if "No orders" not in str(e):
                    print(f"--- [ERROR] {symbol} cancel_all_orders 失败: {e} ---")

            # 4. 双重保险：无论 Cancel All 是否成功，都尝试通过 ID 再次撤销
            # (因为有时候 cancel_all_orders 响应慢，或者某些特殊单子撤不掉)
            if len(open_orders) > 0:
                ids = [o['id'] for o in open_orders]
                # print(f"--- [DEBUG] {symbol} 尝试逐个撤销 ID: {ids} ---")

                # 并发执行逐个撤单
                tasks = [exchange.cancel_order(oid, symbol) for oid in ids]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # 检查结果
                for idx, res in enumerate(results):
                    if isinstance(res, Exception):
                        err_msg = str(res)
                        if "Unknown order" not in err_msg and "Order was not found" not in err_msg:
                            print(f"--- [ERROR] {symbol} 撤销订单 {ids[idx]} 失败: {err_msg} ---")

            # 5. 必须等待
            await asyncio.sleep(0.5)

        except Exception as e:
            print(f"--- [FATAL] {symbol} 清理流程发生未捕获异常: {e} ---")
            await asyncio.sleep(1.0)

    # 如果循环结束还没 return True，说明清理失败
    await async_logger(f"❌ {symbol} 清理失败！仍有挂单残留，已停止后续下单操作。", "error")
    return False


# --- 兼容性包装器 ---
async def _cancel_sl_tp_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    return await _ensure_no_open_orders_async(exchange, symbol, async_logger)


async def _force_cancel_all_orders(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    return await _ensure_no_open_orders_async(exchange, symbol, async_logger)


# ------------------


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
    标准止损下单 (固定SL)
    """
    order_type = 'STOP_MARKET'
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

            # 冲突或超限 -> 再次调用清理
            if '-4130' in err_msg or '-4045' in err_msg or 'limit' in err_msg.lower():
                print(f"--- [RETRY] {symbol} 下单遇阻 ({err_msg})，执行清理后重试... ---")
                cleaned = await _ensure_no_open_orders_async(exchange, symbol, async_logger)
                if not cleaned:
                    return False  # 清理失败则放弃
                continue

            elif '-4120' in err_msg:
                # 降级为限价
                limit_type = 'STOP'
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
    移动止盈下单 (Trailing Stop)
    """
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
                print(f"--- [RETRY] {symbol} 移动止盈下单遇阻 ({err_msg})，执行清理后重试... ---")
                cleaned = await _ensure_no_open_orders_async(exchange, symbol, async_logger)
                if not cleaned:
                    return False
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
            await async_logger(f"⚠️ {position.symbol} 仓位已平，清理挂单。", "warning")
            await _ensure_no_open_orders_async(exchange, full_symbol, async_logger)
            return True

        # 2. 【严防死守】下单前，必须死磕直到订单清空
        # 如果这里返回 False，直接 return，绝对不下单！
        cleaned = await _ensure_no_open_orders_async(exchange, full_symbol, async_logger)

        if not cleaned:
            # 这里的日志会告诉你为什么失败
            await async_logger(f"⛔ {position.symbol} 旧订单清理失败，为防止堆积，已跳过下单。", "error")
            return False

        if stop_event.is_set(): raise InterruptedError()

        is_long = position.side == i18n.SIDE_LONG
        side_key = "long" if is_long else "short"

        # --- 策略互斥逻辑 ---

        # A. 检查是否开启了移动止盈 (最高优先级)
        enable_trailing = config.get(f'enable_{side_key}_trailing_stop', False)

        if enable_trailing:
            # === 分支 A：移动止盈模式 ===
            callback_rate = config.get(f'{side_key}_trailing_stop_callback_rate', 1.0)
            ts_side = 'sell' if is_long else 'buy'

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
            # === 分支 B：固定止损模式 (无TP) ===
            tasks_to_run = []

            if config.get(f'enable_{side_key}_sl_tp', False):
                sl_perc = config.get(f'{side_key}_stop_loss_percentage', 0)
                leverage = config.get('leverage', 1)

                # 固定止损
                if sl_perc > 0:
                    sl_ratio = float(sl_perc) / 100 / leverage
                    entry_price = position.entry_price

                    target_sl = entry_price * (1 - sl_ratio) if is_long else entry_price * (1 + sl_ratio)
                    sl_side = 'sell' if is_long else 'buy'
                    tasks_to_run.append({
                        "name": "SL",
                        "coro": _place_standard_stop_order(exchange, full_symbol, sl_side, position.contracts,
                                                           target_sl, True, async_logger)
                    })

            if not tasks_to_run:
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
                await async_logger(f"✅ {position.symbol} 固定 SL 设置成功", "success")
            else:
                await async_logger(f"⚠️ {position.symbol} 固定 SL 部分成功", "warning")

            return success_count == len(tasks_to_run)

    except Exception as e:
        await async_logger(f"❌ {position.symbol} 流程异常: {e}", "error")
        return False


async def cleanup_orphan_sltp_orders_async(exchange: ccxt.binanceusdm, active_symbols: Set[str], async_logger):
    """
    清理无主订单 (不在 active_symbols 列表中的币种)
    """
    try:
        all_open_orders = await exchange.fetch_open_orders()
        orphan_orders = [
            o for o in all_open_orders
            if (o.get('reduceOnly') or o.get('info', {}).get('closePosition')) and o['symbol'] not in active_symbols
        ]
        if not orphan_orders: return

        orphan_symbols = set(o['symbol'] for o in orphan_orders)
        await async_logger(f"发现 {len(orphan_symbols)} 个币种有残留订单，正在清理...", "warning")

        for sym in orphan_symbols:
            await _ensure_no_open_orders_async(exchange, sym, async_logger)
            await asyncio.sleep(0.1)

    except:
        pass