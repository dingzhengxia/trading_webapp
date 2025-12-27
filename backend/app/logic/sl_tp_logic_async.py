# backend/app/logic/sl_tp_logic_async.py (完全透视调试版)
import asyncio
from typing import Set, List, Dict, Any

import ccxt.async_support as ccxt

from .exceptions import InterruptedError
from ..config import i18n
from ..models.schemas import Position


def _normalize_symbol(s: str) -> str:
    """
    将 symbol 简化为纯字母形式，用于宽松匹配。
    例如: 'BTC/USDT:USDT' -> 'BTCUSDT'
          'ETH/USDC'      -> 'ETHUSDC'
    """
    if not s: return ""
    # 1. 去掉后缀 :USDT
    s = s.split(':')[0]
    # 2. 去掉斜杠 /
    s = s.replace('/', '')
    return s


async def _ensure_no_open_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    【完全透视清理模式】
    拉取全量订单，并打印每一个订单的比对细节，彻底找出为什么删不掉。
    """
    max_retries = 5

    # 目标 symbol 的简化版 (例如 BTCUSDT)
    target_clean = _normalize_symbol(symbol)

    print(f"\n====== [DEBUG START] 正在为 {symbol} (简化:{target_clean}) 清理挂单 ======")

    for i in range(max_retries):
        try:
            # 1. 全量拉取
            all_open_orders = await exchange.fetch_open_orders()

            # 如果是第一次尝试，打印一下账户总单数，确认为什么这里有单子
            if i == 0:
                print(f"--- [INFO] 账户当前未完成订单总数: {len(all_open_orders)} ---")

            orders_to_delete = []

            # 2. 遍历比对 (核心调试区)
            for order in all_open_orders:
                o_id = order['id']
                o_symbol = order['symbol']  # CCXT 解析后的 symbol
                o_raw_symbol = order['info'].get('symbol', '')  # 交易所原始 symbol

                o_symbol_clean = _normalize_symbol(o_symbol)

                # 判断逻辑
                is_match = False
                match_reason = ""

                # 规则1: CCXT symbol 直接相等
                if o_symbol == symbol:
                    is_match = True
                    match_reason = "Strict Match"
                # 规则2: 原始 symbol 相等 (例如 BTCUSDT == BTCUSDT)
                elif o_raw_symbol == target_clean:
                    is_match = True
                    match_reason = "Raw Match"
                # 规则3: 简化后相等 (例如 BTC/USDT == BTCUSDT)
                elif o_symbol_clean == target_clean:
                    is_match = True
                    match_reason = "Clean Match"

                # --- 关键日志：打印那些“看起来像”但不匹配的，或者匹配成功的 ---
                # 只打印相关的币种，防止 153 个订单刷屏太快看不清
                if is_match or target_clean in o_symbol_clean or o_symbol_clean in target_clean:
                    print(
                        f"   [CHECK] ID:{o_id} | OrderSym:{o_symbol} | Raw:{o_raw_symbol} | Target:{symbol} | 结果: {'✅ 匹配 (' + match_reason + ')' if is_match else '❌ 不匹配'}")

                if is_match:
                    orders_to_delete.append(order)

            count = len(orders_to_delete)

            if count == 0:
                if i > 0:
                    await async_logger(f"✅ {symbol} 挂单已清零。", "info")
                print(f"====== [DEBUG END] {symbol} 没有发现匹配订单，清理结束 ======\n")
                return True

            if i == 0:
                print(f"--- [ACTION] 锁定 {count} 个目标订单，执行删除... ---")

            # 3. 执行删除
            cancel_tasks = [exchange.cancel_order(o['id'], symbol) for o in orders_to_delete]
            results = await asyncio.gather(*cancel_tasks, return_exceptions=True)

            # 打印删除结果
            for idx, res in enumerate(results):
                if isinstance(res, Exception):
                    # 只有真正的错误才打印
                    if "Unknown order" not in str(res) and "Order was not found" not in str(res):
                        print(f"   !!! [ERROR] 删除订单 {orders_to_delete[idx]['id']} 失败: {res}")

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
                await async_logger(f"--- [RETRY {attempt + 1}] {symbol} 订单拥堵，执行清理... ---", "warning")
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

        # 逐个击杀
        cancel_tasks = [exchange.cancel_order(o['id'], o['symbol']) for o in orphan_orders]
        await asyncio.gather(*cancel_tasks, return_exceptions=True)

    except:
        pass