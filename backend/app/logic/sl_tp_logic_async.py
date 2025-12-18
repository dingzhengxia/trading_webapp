# backend/app/logic/sl_tp_logic_async.py (CCXT升级适配 + 原生参数修正版)
import asyncio
import json
from typing import Set, List, Dict, Any

import ccxt.async_support as ccxt

from .exceptions import InterruptedError
from ..config import i18n
from ..models.schemas import Position


async def _cancel_sl_tp_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    try:
        open_orders = await exchange.fetch_open_orders(symbol)
        # 清理所有带 reduceOnly 属性的条件单
        orders_to_cancel = [
            order for order in open_orders
            if (order.get('reduceOnly') or order.get('info', {}).get('reduceOnly'))
               and order['type'] in ['STOP', 'TAKE_PROFIT', 'STOP_MARKET', 'TAKE_PROFIT_MARKET', 'stop', 'take_profit']
        ]
        if not orders_to_cancel:
            return True

        tasks = [exchange.cancel_order(order['id'], symbol) for order in orders_to_cancel]
        await asyncio.gather(*tasks, return_exceptions=True)
        return True
    except Exception as e:
        await async_logger(f"  > ❌ 为 {symbol} 清理SL/TP订单时出错: {e}", "error")
        return False


async def _place_raw_order(
        exchange: ccxt.binanceusdm,
        full_symbol: str,
        side: str,
        amount: float,
        trigger_price: float,
        limit_price: float,
        is_stop_loss: bool,
        async_logger
):
    """
    使用 private_post_order 发送最底层的限价止损/止盈单。
    """

    # 1. 获取币安原生 Symbol (例如 "WLDUSDC")
    # full_symbol 是 "WLD/USDC:USDC"
    try:
        market = exchange.market(full_symbol)
        raw_symbol = market['id']  # 这里拿到的就是 "WLDUSDC"
    except Exception as e:
        await async_logger(f"  > ❌ 无法解析 Symbol {full_symbol}: {e}", "error")
        return False

    # 2. 确定原生类型字符串 (币安合约API仅识别 STOP 和 TAKE_PROFIT)
    order_type = 'STOP' if is_stop_loss else 'TAKE_PROFIT'

    # 3. 格式化参数为字符串 (防止 -1104 错误)
    str_qty = exchange.amount_to_precision(full_symbol, amount)
    str_stop_price = exchange.price_to_precision(full_symbol, trigger_price)
    str_limit_price = exchange.price_to_precision(full_symbol, limit_price)

    # 4. 构造请求参数字典 (单向持仓模式)
    # 必须严格遵守：reduceOnly="true" (string), timeInForce="GTC"
    params = {
        'symbol': raw_symbol,
        'side': side.upper(),
        'type': order_type,
        'quantity': str_qty,
        'price': str_limit_price,  # 限价单价格
        'stopPrice': str_stop_price,  # 触发价格
        'timeInForce': 'GTC',
        'reduceOnly': 'true',  # 注意：传字符串 true
        'workingType': 'MARK_PRICE'
    }

    # 调试日志：打印出我们要发的原生 ID 和参数
    # print(f"--- [RAW DEBUG] Symbol: {raw_symbol} | Type: {order_type} ---")
    # print(json.dumps(params, indent=2))

    try:
        # 直接调用私有接口
        return await exchange.private_post_order(params)

    except Exception as e:
        error_msg = str(e)

        # 兜底：如果报 -4061 (Hedge Mode)，说明用户账户其实是双向持仓
        if '-4061' in error_msg:
            print(f"--- [DEBUG] {raw_symbol} 检测到 Hedge Mode，重试 ---")

            params_hedge = params.copy()
            del params_hedge['reduceOnly']  # Hedge 模式不能有 reduceOnly
            # 自动判断 positionSide
            params_hedge['positionSide'] = 'LONG' if side.upper() == 'SELL' else 'SHORT'

            return await exchange.private_post_order(params_hedge)
        else:
            # 抛出异常供上层记录
            raise e


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
            await async_logger(f"⚠️ {position.symbol} 仓位不存在。", "warning")
            await _cancel_sl_tp_orders_async(exchange, full_symbol, async_logger)
            return True

        # 2. 清理旧订单
        await _cancel_sl_tp_orders_async(exchange, full_symbol, async_logger)
        if stop_event.is_set(): raise InterruptedError()

        is_long = position.side == i18n.SIDE_LONG
        side_key = "long" if is_long else "short"

        # 3. 检查开关
        sl_tp_enabled = config.get(f'enable_{side_key}_sl_tp', False)
        if not sl_tp_enabled:
            return True

        sl_perc = config.get(f'{side_key}_stop_loss_percentage', 0)
        tp_perc = config.get(f'{side_key}_take_profit_percentage', 0)

        tasks: List[Any] = []

        # 计算滑点缓冲 (5%) - 确保限价单能成交
        SLIPPAGE = 0.05

        # --- 止损 ---
        if sl_perc > 0:
            leverage = config.get('leverage', 1)
            sl_ratio = float(sl_perc) / 100 / leverage
            entry_price = position.entry_price

            if is_long:
                # 多单止损：向下触发，卖出。限价要比触发价低
                target_trigger = entry_price * (1 - sl_ratio)
                target_limit = target_trigger * (1 - SLIPPAGE)
                sl_side = 'SELL'
            else:
                # 空单止损：向上触发，买入。限价要比触发价高
                target_trigger = entry_price * (1 + sl_ratio)
                target_limit = target_trigger * (1 + SLIPPAGE)
                sl_side = 'BUY'

            # 打印日志确认价格
            # await async_logger(f"  > 准备提交 {position.symbol} SL (触发: {target_trigger:.4f}, 限价: {target_limit:.4f})")

            tasks.append(_place_raw_order(
                exchange, full_symbol, sl_side, position.contracts,
                target_trigger, target_limit, is_stop_loss=True, async_logger=async_logger
            ))

        # --- 止盈 ---
        if tp_perc > 0:
            leverage = config.get('leverage', 1)
            tp_ratio = float(tp_perc) / 100 / leverage
            entry_price = position.entry_price

            if is_long:
                # 多单止盈：向上触发，卖出。限价通常等于或略低于触发价(为了成交)
                target_trigger = entry_price * (1 + tp_ratio)
                # 这里设为相同，或者略低一点点保证成交
                target_limit = target_trigger
                tp_side = 'SELL'
            else:
                # 空单止盈：向下触发，买入
                target_trigger = entry_price * (1 - tp_ratio)
                target_limit = target_trigger
                tp_side = 'BUY'

            # await async_logger(f"  > 准备提交 {position.symbol} TP (触发: {target_trigger:.4f}, 限价: {target_limit:.4f})")

            tasks.append(_place_raw_order(
                exchange, full_symbol, tp_side, position.contracts,
                target_trigger, target_limit, is_stop_loss=False, async_logger=async_logger
            ))

        if not tasks:
            return True

        # 4. 执行
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = 0
        total_tasks = len(tasks)

        for res in results:
            if isinstance(res, dict) and res.get('orderId'):
                success_count += 1
            elif isinstance(res, Exception):
                await async_logger(f"  > ❌ {position.symbol} 订单失败: {res}", "error")

        if success_count < total_tasks:
            await async_logger(f"⚠️ {position.symbol} SL/TP 不完整 ({success_count}/{total_tasks})", "warning")
        else:
            await async_logger(f"✅ {position.symbol} 校准成功！", "success")

        return success_count == total_tasks

    except InterruptedError:
        return False
    except Exception as e:
        await async_logger(f"❌ 设置 {position.symbol} SL/TP 严重错误: {e}", "error")
        return False


async def cleanup_orphan_sltp_orders_async(exchange: ccxt.binanceusdm, active_symbols: Set[str], async_logger):
    try:
        all_open_orders = await exchange.fetch_open_orders()
        orphan_orders = [
            order for order in all_open_orders
            if order.get('reduceOnly') and order['symbol'] not in active_symbols
        ]
        if not orphan_orders:
            return
        await async_logger(f"清理 {len(orphan_orders)} 个无主订单...", "warning")
        tasks = [exchange.cancel_order(order['id'], order['symbol']) for order in orphan_orders]
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception:
        pass