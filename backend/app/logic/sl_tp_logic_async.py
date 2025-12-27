# backend/app/logic/sl_tp_logic_async.py (深度诊断版)
import asyncio
from typing import Set, List, Dict, Any

import ccxt.async_support as ccxt

from .exceptions import InterruptedError
from ..config import i18n
from ..models.schemas import Position


async def _ensure_no_open_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    【深度诊断清理模式】
    带有详细的调试日志，用于排查为什么订单删不掉。
    """
    max_retries = 5

    print(f"\n====== [DIAG-START] 开始清理 {symbol} ======")

    for i in range(max_retries):
        print(f"--- [DIAG] {symbol} 第 {i + 1}/{max_retries} 次尝试 ---")

        try:
            # 1. 无论如何，先发一个 Cancel All
            # print(f"   >>> [REQ] 发送 cancel_all_orders({symbol})...")
            try:
                await exchange.cancel_all_orders(symbol)
                # print(f"   <<< [RES] cancel_all_orders({symbol}) 请求发送成功。")
            except Exception as e:
                err_msg = str(e)
                if "No orders" in err_msg:
                    pass  # 这是正常的
                else:
                    print(f"   !!! [ERR] cancel_all_orders 异常: {err_msg}")

            # 2. 等待撮合引擎
            await asyncio.sleep(1.0)

            # 3. 查单验证
            # print(f"   >>> [REQ] 发送 fetch_open_orders({symbol})...")
            open_orders = await exchange.fetch_open_orders(symbol)
            count = len(open_orders)

            if count == 0:
                print(f"   <<< [RES] {symbol} 当前挂单数: 0。清理成功。")
                print(f"====== [DIAG-END] {symbol} 清理完毕 ======\n")
                return True

            # 4. 如果还有单子，打印出来看看是何方神圣
            order_ids = [o['id'] for o in open_orders]
            order_types = [o['type'] for o in open_orders]
            print(f"   !!! [WARN] {symbol} 盲撤后仍有 {count} 个订单滞留！")
            print(f"       ID列表: {order_ids}")
            print(f"       类型列表: {order_types}")

            # 5. 执行点名枪毙 (Cancel by ID)
            print(f"   >>> [REQ] 执行逐个删除 (Cancel by ID)...")
            cancel_tasks = [exchange.cancel_order(oid, symbol) for oid in order_ids]
            results = await asyncio.gather(*cancel_tasks, return_exceptions=True)

            err_count = 0
            for idx, res in enumerate(results):
                if isinstance(res, Exception):
                    # 忽略找不到订单的错误（可能被CancelAll删了）
                    if "Unknown order" not in str(res) and "Order was not found" not in str(res):
                        print(f"       [ERR] 删除 ID {order_ids[idx]} 失败: {res}")
                        err_count += 1

            if err_count == 0:
                print(f"   <<< [RES] 逐个删除请求全部发送完毕。")

            # 再次等待
            await asyncio.sleep(0.5)

        except Exception as e:
            print(f"   !!! [FATAL] 清理循环发生严重错误: {e}")
            await asyncio.sleep(1.0)

    print(f"!!! [DIAG-FAIL] {symbol} {max_retries} 次尝试后仍未清理干净，禁止下单！\n")
    await async_logger(f"⛔ {symbol} 顽固订单无法清除，已跳过下单。", "error")
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
            print(f"--- [ERR-PLACE] {symbol} 固定SL下单失败: {err_msg}")

            if '-4130' in err_msg or '-4045' in err_msg or 'limit' in err_msg.lower():
                await _ensure_no_open_orders_async(exchange, symbol, async_logger)
                continue

            elif '-4120' in err_msg:
                # 降级
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
            print(f"--- [REQ] {symbol} 尝试下移动止盈单 (Rate:{rate}%)...")
            return await exchange.create_order(symbol, 'TRAILING_STOP_MARKET', side, amount_str, None, params)
        except ccxt.ExchangeError as e:
            err_msg = str(e)
            print(f"--- [ERR-PLACE] {symbol} 移动止盈下单失败: {err_msg}")

            if '-4130' in err_msg or '-4045' in err_msg or 'limit' in err_msg.lower():
                await async_logger(f"--- [RETRY {attempt + 1}] {symbol} 订单拥堵/冲突，执行清理... ---", "warning")
                await _ensure_no_open_orders_async(exchange, symbol, async_logger)
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
        cleaned = await _ensure_no_open_orders_async(exchange, full_symbol, async_logger)

        if not cleaned:
            # 这里的日志会告诉你为什么失败
            print(f"!!! [ABORT] {position.symbol} 清理未通过，放弃下单 !!!")
            await async_logger(f"⛔ {position.symbol} 挂单清理失败，已跳过下单。", "error")
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