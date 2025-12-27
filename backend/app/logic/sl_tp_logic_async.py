# backend/app/logic/sl_tp_logic_async.py (法医鉴定版)
import asyncio
from typing import Set, List, Dict, Any

import ccxt.async_support as ccxt

from .exceptions import InterruptedError
from ..config import i18n
from ..models.schemas import Position


async def _ensure_no_open_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    【法医鉴定清理模式】
    详细打印比对过程，找出为什么删不掉订单。
    """
    max_retries = 5  # 减少重试次数，专注诊断

    print(f"\n====== [DIAG-START] 准备清理 {symbol} ======")

    for i in range(max_retries):
        try:
            # 1. 全量拉取
            # print(f"   >>> [REQ] 拉取全账户所有挂单 (不按Symbol过滤)...")
            all_open_orders = await exchange.fetch_open_orders()
            total_count = len(all_open_orders)

            # print(f"   <<< [RES] 账户当前总挂单数: {total_count}")

            # 2. 本地匹配逻辑 (带详细日志)
            target_orders = []

            # 打印前3个订单的样本，看看格式长啥样
            if i == 0 and total_count > 0:
                sample = all_open_orders[0]
                print(
                    f"   --- [SAMPLE] 订单样本: ID={sample['id']}, Symbol='{sample['symbol']}' (Type: {type(sample['symbol'])})")

            for order in all_open_orders:
                o_symbol = order['symbol']
                o_id = order['id']

                # 严格匹配
                if o_symbol == symbol:
                    target_orders.append(order)
                else:
                    # 模糊匹配调试：如果包含 target 字符串，说明可能格式不对
                    # 例如 target="BTC/USDT:USDT", order="BTC/USDT"
                    if symbol in o_symbol or o_symbol in symbol:
                        if i == 0:  # 只在第一轮打印，防止刷屏
                            print(f"   ??? [MISMATCH] 发现疑似订单但不匹配: ID={o_id}")
                            print(f"       Order Symbol : '{o_symbol}'")
                            print(f"       Target Symbol: '{symbol}'")

            count = len(target_orders)

            if count == 0:
                if i > 0:
                    await async_logger(f"✅ {symbol} 清理完毕 (本地比对0个)。", "info")
                print(f"====== [DIAG-END] {symbol} 匹配数为0，结束 ======\n")
                return True

            if i == 0:
                print(f"--- [CLEANUP] {symbol} 匹配到 {count} 个目标订单，准备击杀... ---")

            # 3. 逐个击杀
            # 注意：这里使用 cancel_order(id, symbol)
            # 有时候传入 symbol 有助于加速，但有时候 symbol 不对会导致报错
            # 我们先尝试带 symbol
            cancel_tasks = [exchange.cancel_order(o['id'], symbol) for o in target_orders]

            results = await asyncio.gather(*cancel_tasks, return_exceptions=True)

            success_cnt = 0
            for idx, res in enumerate(results):
                if isinstance(res, Exception):
                    err = str(res)
                    if "Unknown order" not in err and "Order was not found" not in err:
                        print(f"   !!! [ERR] 删除 ID {target_orders[idx]['id']} 失败: {err}")
                else:
                    success_cnt += 1

            print(f"   >>> [RESULT] 本轮尝试删除 {count} 个，成功发送指令 {success_cnt} 个")

            # 4. 等待
            await asyncio.sleep(0.5 + (i * 0.2))

        except Exception as e:
            print(f"   !!! [FATAL] 清理流程异常: {e}")
            await asyncio.sleep(1.0)

    await async_logger(f"❌ {symbol} 清理失败，无法消除 {len(target_orders)} 个残留订单。", "error")
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
                await async_logger(f"--- [RETRY {attempt + 1}] {symbol} 订单拥堵，执行全量清理... ---", "warning")
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

        # 2. 【核心】下单前，强制执行全量清理
        cleaned = await _ensure_no_open_orders_async(exchange, full_symbol, async_logger)
        if not cleaned:
            await async_logger(f"⛔ {position.symbol} 无法清除旧单，跳过。", "error")
            return False

        if stop_event.is_set(): raise InterruptedError()

        is_long = position.side == i18n.SIDE_LONG
        side_key = "long" if is_long else "short"

        # --- 策略互斥逻辑 ---

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
        # 全量拉取
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