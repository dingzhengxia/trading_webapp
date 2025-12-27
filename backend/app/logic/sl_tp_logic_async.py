# backend/app/logic/sl_tp_logic_async.py (全账户地毯式扫描版)
import asyncio
import json
from typing import Set, List, Dict, Any

import ccxt.async_support as ccxt

from .exceptions import InterruptedError
from ..config import i18n
from ..models.schemas import Position


async def _ensure_no_open_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    【地毯式清理模式】
    1. 拉取账户所有订单。
    2. 打印清单。
    3. 只要订单属于该币种（模糊匹配），直接用订单自带的参数进行删除。
    """
    max_retries = 5

    # 提取特征：比如 "BTC/USDC:USDC" -> base="BTC", quote="USDC"
    try:
        parts = symbol.split(':')[0].split('/')
        target_base = parts[0]  # BTC
        target_quote = parts[1]  # USDC
    except:
        target_base = symbol
        target_quote = ""

    print(f"\n====== [SCAN START] 正在扫描目标: {target_base} + {target_quote} ======", flush=True)

    for i in range(max_retries):
        try:
            # 1. 没有任何过滤，拉取全账户所有挂单
            # print(f"   >>> [REQ] 拉取全量订单...", flush=True)
            all_orders = await exchange.fapiPrivateGetOpenOrders()

            # 2. 筛选出我们要杀的单子
            orders_to_kill = []

            for o in all_orders:
                o_symbol = o['symbol']  # 比如 "BTCUSDC"

                # 匹配逻辑：
                # 如果 target_base (BTC) 在 o_symbol 里，且 target_quote (USDC) 也在 o_symbol 里
                # 那么这个单子就是我们要找的 BTCUSDC
                if target_base in o_symbol and target_quote in o_symbol:
                    orders_to_kill.append(o)
                # 容错：如果 quote 没解析出来，只要 base 完全匹配也行 (防止 BTCUSDT 被漏掉)
                elif target_base in o_symbol and not target_quote:
                    orders_to_kill.append(o)

            count = len(orders_to_kill)

            # 如果没找到，退出
            if count == 0:
                if i == 0:
                    # 只有第一轮没找到才值得打印，证明真的干净
                    # 顺便打印一下当前账户里到底有啥，方便排查
                    print(f"   [INFO] 未发现目标订单。当前账户持单总数: {len(all_orders)}", flush=True)
                    if len(all_orders) > 0 and len(all_orders) < 20:
                        print(f"   [DUMP] 现有订单Symbols: {[x['symbol'] for x in all_orders]}", flush=True)
                return True

            if i == 0:
                print(f"--- [FOUND] 发现 {count} 个目标订单! ---", flush=True)
                # 打印第一个，确认一下眼神
                print(f"    样本: ID={orders_to_kill[0]['orderId']} Symbol={orders_to_kill[0]['symbol']}", flush=True)

            # 3. 这里的关键：使用订单自带的 symbol 去删除，不要用我们传进来的 symbol
            # 这样能 100% 避免格式错误
            tasks = []
            for o in orders_to_kill:
                real_symbol = o['symbol']  # BTCUSDC
                real_id = o['orderId']
                # 调用底层接口删除，不经过 CCXT 包装
                tasks.append(exchange.fapiPrivateDeleteOrder({
                    'symbol': real_symbol,
                    'orderId': real_id
                }))

            # 并发执行
            results = await asyncio.gather(*tasks, return_exceptions=True)

            success = 0
            for res in results:
                if not isinstance(res, Exception):
                    success += 1
                else:
                    print(f"   !!! [ERR] 删除失败: {res}", flush=True)

            print(f"   >>> [RESULT] 成功发送删除指令: {success}/{count}", flush=True)

            # 等待
            await asyncio.sleep(0.5)

        except Exception as e:
            print(f"--- [FATAL] 扫描清理异常: {e} ---", flush=True)
            await asyncio.sleep(1.0)

    await async_logger(f"❌ {symbol} 清理尝试多次未果。", "error")
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
                await async_logger(f"--- [RETRY {attempt + 1}] {symbol} 订单拥堵，执行地毯式清理... ---", "warning")
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

        # 2. 【核心】下单前全频段清理
        cleaned = await _ensure_no_open_orders_async(exchange, full_symbol, async_logger)
        if not cleaned:
            # 如果清理失败，为了不报错，我们还是尝试下一次单，但在日志里警告
            pass

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
        all_orders = await exchange.fapiPrivateGetOpenOrders()
        orphan_orders = [o for o in all_orders if o['symbol'] not in active_symbols and "USDT" in o['symbol']]  # 简单过滤

        if not orphan_orders: return

        await async_logger(f"发现 {len(orphan_orders)} 个无主订单，正在清理...", "warning")

        for o in orphan_orders:
            await exchange.fapiPrivateDeleteOrder({'symbol': o['symbol'], 'orderId': o['orderId']})

    except:
        pass