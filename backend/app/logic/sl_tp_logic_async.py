# backend/app/logic/sl_tp_logic_async.py (模糊匹配+全量清理版)
import asyncio
from typing import Set, List, Dict, Any

import ccxt.async_support as ccxt

from .exceptions import InterruptedError
from ..config import i18n
from ..models.schemas import Position


def _is_symbol_match(target_symbol: str, order: dict) -> bool:
    """
    【模糊匹配逻辑】
    判断订单是否属于目标交易对。
    解决 CCXT symbol 格式 (BTC/USDT:USDT) 与 订单 symbol (BTC/USDT) 不一致的问题。
    """
    order_symbol = order['symbol']

    # 1. 严格匹配
    if order_symbol == target_symbol:
        return True

    # 2. 原始 ID 匹配 (查看 binance 返回的原始 symbol，如 'BTCUSDT')
    if 'info' in order and 'symbol' in order['info']:
        # 将 target_symbol (BTC/USDT:USDT) 简化为 BTCUSDT 格式尝试匹配
        normalized_target = target_symbol.split(':')[0].replace('/', '')
        if order['info']['symbol'] == normalized_target:
            return True

    # 3. 结构化模糊匹配
    # 提取目标币种的基础和计价货币
    # 假设 target_symbol 格式为 BASE/QUOTE:QUOTE 或 BASE/QUOTE
    try:
        parts = target_symbol.split(':')[0].split('/')
        if len(parts) == 2:
            base, quote = parts[0], parts[1]
            # 如果订单 symbol 同时也包含这两个部分
            if base in order_symbol and quote in order_symbol:
                return True
    except:
        pass

    return False


async def _ensure_no_open_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    【智能全量清理】
    拉取全账户订单 -> 使用模糊匹配找出目标 -> 逐个删除。
    """
    max_retries = 5

    # print(f"\n====== [CLEAN-START] 准备清理 {symbol} ======")

    for i in range(max_retries):
        try:
            # 1. 全量拉取 (这是目前最可靠获取订单的方法)
            # 虽然效率低，但能保证拿到数据
            all_open_orders = await exchange.fetch_open_orders()

            # 2. 使用模糊匹配筛选
            target_orders = []
            for order in all_open_orders:
                if _is_symbol_match(symbol, order):
                    target_orders.append(order)

            count = len(target_orders)

            # 如果没找到，说明干净了
            if count == 0:
                if i > 0:
                    await async_logger(f"✅ {symbol} 挂单已清零。", "info")
                return True

            if i == 0:
                print(f"--- [CLEANUP] {symbol} 匹配到 {count} 个关联订单，执行删除... ---")

            # 3. 逐个击杀 (Cancel by ID)
            # 使用并发加速删除过程
            cancel_tasks = [exchange.cancel_order(o['id'], symbol) for o in target_orders]

            results = await asyncio.gather(*cancel_tasks, return_exceptions=True)

            success_cnt = 0
            for res in results:
                if not isinstance(res, Exception):
                    success_cnt += 1
                else:
                    # 忽略 "Unknown order" (可能已经被成交或被取消)
                    if "Unknown order" not in str(res) and "Order was not found" not in str(res):
                        print(f"--- [ERR] 撤单报错: {res} ---")

            # 4. 这里的等待是为了防止API频率限制 (Rate Limit)
            # 对于50个仓位，如果这里不等待，很容易触发 IP Ban
            await asyncio.sleep(0.2)

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
                await async_logger(f"--- [RETRY {attempt + 1}] {symbol} 订单拥堵，执行模糊清理... ---", "warning")
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