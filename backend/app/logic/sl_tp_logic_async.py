# backend/app/logic/sl_tp_logic_async.py (底层直连核弹版)
import asyncio
from typing import Set, List, Dict, Any

import ccxt.async_support as ccxt

from .exceptions import InterruptedError
from ..config import i18n
from ..models.schemas import Position


def _get_raw_symbol(ccxt_symbol: str) -> str:
    """
    将 CCXT 格式 (BTC/USDT:USDT) 强制转换为 币安底层格式 (BTCUSDT)。
    不依赖 exchange.markets 的缓存，直接字符串硬转。
    """
    if not ccxt_symbol: return ""
    # 1. 去掉 :USDT 后缀
    base_part = ccxt_symbol.split(':')[0]
    # 2. 去掉 /
    raw = base_part.replace('/', '')
    return raw


async def _ensure_no_open_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    【底层直连清理模式】
    绕过 CCXT 封装，直接向币安发送原始 HTTP 请求。
    """
    max_retries = 5
    raw_symbol = _get_raw_symbol(symbol)

    print(f"\n====== [NUCLEAR START] 目标: {symbol} (原生: {raw_symbol}) ======")

    for i in range(max_retries):
        try:
            # -------------------------------------------------------------
            # 步骤 1: 使用底层接口直接查询 (照妖镜)
            # -------------------------------------------------------------
            native_orders = []
            try:
                # 直接调用 binance fapi 接口，不经过 ccxt 过滤器
                # 参数必须是原生 symbol，例如 'BTCUSDT'
                native_orders = await exchange.fapiPrivateGetOpenOrders({'symbol': raw_symbol})
            except Exception as e:
                print(f"   [WARN] 原生查询失败 ({raw_symbol}): {e}")
                # 如果原生查询失败，尝试不传参查全量
                try:
                    all_raw = await exchange.fapiPrivateGetOpenOrders()
                    # 本地过滤
                    native_orders = [o for o in all_raw if o['symbol'] == raw_symbol]
                except:
                    pass

            count = len(native_orders)

            # 如果真的没订单，且不是第一次尝试（防止并发延迟），则通过
            if count == 0:
                if i > 0:
                    await async_logger(f"✅ {symbol} 挂单清理完毕 (底层核实)。", "info")
                return True

            if i == 0:
                print(f"--- [CLEANUP] 发现 {count} 个顽固订单 (原生接口检出)，准备核打击... ---")
                # 打印第一个订单的详情，看看长什么样
                if count > 0:
                    print(
                        f"   [SAMPLE] ID: {native_orders[0].get('orderId')} Type: {native_orders[0].get('type')} Side: {native_orders[0].get('side')}")

            # -------------------------------------------------------------
            # 步骤 2: 核弹撤单 (Cancel All)
            # -------------------------------------------------------------

            # 方案A: 用 CCXT 标准接口撤 (针对 BTC/USDT:USDT)
            try:
                await exchange.cancel_all_orders(symbol)
            except:
                pass

            # 方案B: 用底层接口撤 (针对 BTCUSDT)
            # fapiPrivateDeleteAllOpenOrders 是币安撤销某币种所有挂单的端点
            try:
                await exchange.fapiPrivateDeleteAllOpenOrders({'symbol': raw_symbol})
                print(f"   >>> [SENT] 原生撤单指令已发送: {raw_symbol}")
            except Exception as e:
                err = str(e)
                if "No orders" not in err:
                    print(f"   !!! [ERR] 原生撤单失败: {err}")

            # -------------------------------------------------------------
            # 步骤 3: 逐个点名撤单 (补刀)
            # -------------------------------------------------------------
            if count > 0:
                cancel_tasks = []
                for o in native_orders:
                    order_id = o['orderId']
                    # 混合使用两种 ID 格式尝试删除
                    cancel_tasks.append(exchange.cancel_order(order_id, symbol))

                if cancel_tasks:
                    await asyncio.gather(*cancel_tasks, return_exceptions=True)

            # 必须等待
            await asyncio.sleep(0.5 + (i * 0.2))

        except Exception as e:
            print(f"--- [FATAL] 清理流程异常: {e} ---")
            await asyncio.sleep(1.0)

    await async_logger(f"❌ {symbol} 底层清理失败，请检查账户权限。", "error")
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

        # 2. 【核心】下单前清理 (调用新版)
        cleaned = await _ensure_no_open_orders_async(exchange, full_symbol, async_logger)
        if not cleaned:
            await async_logger(f"⛔ {position.symbol} 无法清除旧单，跳过。", "error")
            return False

        if stop_event.is_set(): raise InterruptedError()

        is_long = position.side == i18n.SIDE_LONG
        side_key = "long" if is_long else "short"

        enable_trailing = config.get(f'enable_{side_key}_trailing_stop', False)

        if enable_trailing:
            # === 移动止盈模式 ===
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
            # === 固定止损模式 ===
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