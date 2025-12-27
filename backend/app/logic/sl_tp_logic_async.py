# backend/app/logic/sl_tp_logic_async.py (强制 U 本位全量版)
import asyncio
import json
from typing import Set, List, Dict, Any

import ccxt.async_support as ccxt

from .exceptions import InterruptedError
from ..config import i18n
from ..models.schemas import Position


def _normalize_symbol(s: str) -> str:
    """
    将 symbol 简化为纯字母形式
    """
    if not s: return ""
    return s.split(':')[0].replace('/', '')


async def _ensure_no_open_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    【强制 U 本位全量清理】
    尝试多种手段拉取订单，包括原生接口。
    """
    max_retries = 5
    target_clean = _normalize_symbol(symbol)

    print(f"\n====== [DEBUG START] 清理 {symbol} ======")

    for i in range(max_retries):
        try:
            all_orders = []

            # 1. 尝试 CCXT 标准接口
            try:
                # 显式传入 None，确保查所有
                orders_ccxt = await exchange.fetch_open_orders(symbol=None)
                all_orders.extend(orders_ccxt)
            except Exception as e:
                print(f"   [WARN] CCXT fetch_open_orders 失败: {e}")

            # 2. 【核心】尝试币安原生 U 本位接口 (如果CCXT查不到，这个通常能查到)
            if len(all_orders) == 0:
                try:
                    # fapiPrivateGetOpenOrders 是币安合约的底层接口
                    # 它不经过 CCXT 的过滤器
                    raw_orders = await exchange.fapiPrivateGetOpenOrders()
                    # 转换原生订单格式为 CCXT 简易格式以便后续处理
                    for raw in raw_orders:
                        # 币安原生 symbol 是不带 / 的，如 BTCUSDT
                        all_orders.append({
                            'id': raw['orderId'],
                            'symbol': raw['symbol'],  # 注意：这里是原始 symbol
                            'info': raw
                        })
                    if len(all_orders) > 0:
                        print(f"   [INFO] 原生接口查到了 {len(all_orders)} 个订单！")
                except Exception as e:
                    # 有些版本的 ccxt 方法名可能不同，或者权限问题
                    print(f"   [WARN] 原生接口调用失败: {e}")

            # 3. 如果第一次查完还是 0，那就真的见了鬼了
            if i == 0:
                print(f"--- [INFO] 账户总挂单数: {len(all_orders)} ---")

            orders_to_delete = []

            # 4. 遍历匹配
            for order in all_orders:
                o_id = order['id']
                # 注意：如果是原生接口来的，symbol 可能是 BTCUSDT
                o_symbol = order.get('symbol', '')

                # 统一转为 clean 格式比较
                o_clean = _normalize_symbol(o_symbol)

                is_match = False
                if o_clean == target_clean:
                    is_match = True
                elif symbol in o_symbol:  # 简单的包含关系
                    is_match = True

                if is_match:
                    orders_to_delete.append(order)

            count = len(orders_to_delete)

            if count == 0:
                if i > 0:
                    await async_logger(f"✅ {symbol} 挂单已清零。", "info")
                return True

            if i == 0:
                print(f"--- [ACTION] 发现 {count} 个目标订单，执行删除... ---")

            # 5. 执行删除
            # 注意：cancel_order 需要标准的 symbol。
            # 如果我们是从原生接口拿到的 'BTCUSDT'，传给 ccxt 可能会报错 "Symbol not found"
            # 所以我们要尽量用传入参数的 `symbol` (即 BTC/USDT:USDT) 去删
            cancel_tasks = []
            for o in orders_to_delete:
                # 优先使用传入的规范 symbol，如果失败再试原始 symbol
                cancel_tasks.append(exchange.cancel_order(o['id'], symbol))

            results = await asyncio.gather(*cancel_tasks, return_exceptions=True)

            for idx, res in enumerate(results):
                if isinstance(res, Exception):
                    err = str(res)
                    if "Unknown order" not in err and "Order was not found" not in err:
                        print(f"   !!! [ERROR] 删除失败 ID {orders_to_delete[idx]['id']}: {err}")

            await asyncio.sleep(0.5)

        except Exception as e:
            print(f"--- [FATAL] 清理流程异常: {e} ---")
            await asyncio.sleep(1.0)

    await async_logger(f"❌ {symbol} 清理失败，跳过下单。", "error")
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

            # 冲突或超限 -> 清理
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
            return await exchange.create_order(symbol, 'TRAILING_STOP_MARKET', side, amount_str, None, params)
        except ccxt.ExchangeError as e:
            err_msg = str(e)

            if '-4130' in err_msg or '-4045' in err_msg or 'limit' in err_msg.lower():
                await async_logger(f"--- [RETRY {attempt + 1}] {symbol} 订单拥堵，执行深度清理... ---", "warning")
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

        # 2. 【核心】下单前清理
        cleaned = await _ensure_no_open_orders_async(exchange, full_symbol, async_logger)
        if not cleaned:
            await async_logger(f"⛔ {position.symbol} 无法清除旧单，跳过。", "error")
            return False

        if stop_event.is_set(): raise InterruptedError()

        is_long = position.side == i18n.SIDE_LONG
        side_key = "long" if is_long else "short"

        enable_trailing = config.get(f'enable_{side_key}_trailing_stop', False)

        if enable_trailing:
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
            tasks_to_run = []
            if config.get(f'enable_{side_key}_sl_tp', False):
                sl_perc = config.get(f'{side_key}_stop_loss_percentage', 0)
                leverage = config.get('leverage', 1)

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
    清理无主订单
    """
    try:
        all_open_orders = await exchange.fetch_open_orders()
        orphan_orders = [
            o for o in all_open_orders
            if (o.get('reduceOnly') or o.get('info', {}).get('closePosition')) and o['symbol'] not in active_symbols
        ]
        if not orphan_orders: return

        await async_logger(f"发现 {len(orphan_orders)} 个无主订单，正在清理...", "warning")

        for sym in set(o['symbol'] for o in orphan_orders):
            await _ensure_no_open_orders_async(exchange, sym, async_logger)
            await asyncio.sleep(0.1)

    except:
        pass