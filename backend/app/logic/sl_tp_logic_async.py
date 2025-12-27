# backend/app/logic/sl_tp_logic_async.py (底层日志版)
import asyncio
import json
from typing import Set, List, Dict, Any

import ccxt.async_support as ccxt

from .exceptions import InterruptedError
from ..config import i18n
from ..models.schemas import Position


def _get_raw_symbol(ccxt_symbol: str) -> str:
    """
    将 CCXT 格式 (BTC/USDT:USDT) 强制转换为 币安底层格式 (BTCUSDT)。
    """
    if not ccxt_symbol: return ""
    # 1. 取冒号前面
    base_part = ccxt_symbol.split(':')[0]
    # 2. 去掉斜杠
    raw = base_part.replace('/', '')
    return raw


async def _ensure_no_open_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    【底层直连清理模式】
    绕过 CCXT 封装，直接向币安发送原始 HTTP 请求，并强制打印日志。
    """
    max_retries = 3
    raw_symbol = _get_raw_symbol(symbol)

    print(f"\n====== [LOG-START] 处理 {symbol} (原生: {raw_symbol}) ======", flush=True)

    for i in range(max_retries):
        try:
            # -------------------------------------------------------------
            # 1. 尝试用原生接口查询 (照妖镜)
            # -------------------------------------------------------------
            print(f"   >>> [REQ] 正在调用 fapiPrivateGetOpenOrders (symbol={raw_symbol})...", flush=True)
            native_orders = []
            try:
                # 直接调用 binance fapi 接口
                native_orders = await exchange.fapiPrivateGetOpenOrders({'symbol': raw_symbol})
                print(f"   <<< [RES] 原生接口返回: 找到 {len(native_orders)} 个订单", flush=True)

                if len(native_orders) > 0:
                    # 打印前2个订单的详细信息，看看是不是我们找的
                    print(f"       [DUMP] 第1个订单详情: {json.dumps(native_orders[0])}", flush=True)

            except Exception as e:
                print(f"   !!! [ERR] 原生查询报错: {e}", flush=True)

            # 如果没订单，直接返回
            if len(native_orders) == 0:
                if i > 0:
                    await async_logger(f"✅ {symbol} 底层查询无挂单。", "info")
                return True

            # -------------------------------------------------------------
            # 2. 尝试用原生接口撤销全部 (核弹)
            # -------------------------------------------------------------
            print(f"   >>> [REQ] 正在调用 fapiPrivateDeleteAllOpenOrders (symbol={raw_symbol})...", flush=True)
            try:
                await exchange.fapiPrivateDeleteAllOpenOrders({'symbol': raw_symbol})
                print(f"   <<< [RES] 原生撤单指令发送成功。", flush=True)
                await async_logger(f"⚠️ 已发送 {raw_symbol} 强力撤单指令。", "warning")
            except Exception as e:
                err = str(e)
                if "No orders" in err:
                    print(f"   <<< [RES] 交易所提示无订单可撤。", flush=True)
                else:
                    print(f"   !!! [ERR] 原生撤单失败: {err}", flush=True)

            # -------------------------------------------------------------
            # 3. 尝试按 ID 补刀 (防止 CancelAll 失效)
            # -------------------------------------------------------------
            if len(native_orders) > 0:
                print(f"   >>> [REQ] 执行 ID 补刀...", flush=True)
                tasks = []
                for o in native_orders:
                    oid = o['orderId']
                    # 注意：这里传给 CCXT 的是 CCXT 格式的 symbol，这是 cancel_order 要求的
                    tasks.append(exchange.cancel_order(oid, symbol))

                await asyncio.gather(*tasks, return_exceptions=True)

            # 等待
            await asyncio.sleep(1.0)

        except Exception as e:
            print(f"--- [FATAL] 清理流程异常: {e} ---", flush=True)
            await asyncio.sleep(1.0)

    await async_logger(f"❌ {symbol} 清理失败，原生接口仍返回有残留。", "error")
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
            print(f"   !!! [ERR] 固定SL下单失败: {err_msg}", flush=True)

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
            print(f"   >>> [REQ] 下移动止盈单 {symbol} (Rate:{rate}%)...", flush=True)
            return await exchange.create_order(symbol, 'TRAILING_STOP_MARKET', side, amount_str, None, params)
        except ccxt.ExchangeError as e:
            err_msg = str(e)
            print(f"   !!! [ERR] 移动止盈下单失败: {err_msg}", flush=True)

            if '-4130' in err_msg or '-4045' in err_msg or 'limit' in err_msg.lower():
                await async_logger(f"--- [RETRY {attempt + 1}] {symbol} 订单拥堵，执行底层清理... ---", "warning")
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

        # 2. 【核心】下单前，强制执行底层清理
        cleaned = await _ensure_no_open_orders_async(exchange, full_symbol, async_logger)
        if not cleaned:
            await async_logger(f"⛔ {position.symbol} 原生接口显示仍有残留，跳过下单。", "error")
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