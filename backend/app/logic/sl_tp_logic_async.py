# backend/app/logic/sl_tp_logic_async.py (最终修正：通过 create_order 强行注入 STOP/TAKE_PROFIT 类型)
import asyncio
from typing import Set, List, Any

import ccxt.async_support as ccxt

from .exceptions import InterruptedError
from ..config import i18n
from ..models.schemas import Position


async def _cancel_sl_tp_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    清理旧订单
    """
    try:
        open_orders = await exchange.fetch_open_orders(symbol)
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


async def _place_limit_stop_official(
        exchange: ccxt.binanceusdm,
        full_symbol: str,
        side: str,
        amount: float,
        trigger_price: float,
        is_stop_loss: bool,
        async_logger
):
    """
    使用标准的 create_order 接口，但通过 params 强行指定 API 真实类型。
    这是解决 -4120 和 -1104 的最稳妥方案。
    """

    # 1. 确定币安合约 API 的真实类型字符串 (Limit Stop/TP)
    # STOP = 限价止损
    # TAKE_PROFIT = 限价止盈
    real_api_type = 'STOP' if is_stop_loss else 'TAKE_PROFIT'

    # 2. 计算激进的限价 (模拟市价成交)
    # 5% 的滑点缓冲，保证触发后立即成交
    SLIPPAGE = 0.05
    if side.upper() == 'BUY':
        raw_limit_price = trigger_price * (1 + SLIPPAGE)
    else:
        raw_limit_price = trigger_price * (1 - SLIPPAGE)

    # 3. 精度处理
    limit_price = float(exchange.price_to_precision(full_symbol, raw_limit_price))
    trigger_price = float(exchange.price_to_precision(full_symbol, trigger_price))
    amount = float(exchange.amount_to_precision(full_symbol, amount))

    # 4. 构造 params
    # 关键：我们告诉 create_order 这是一个 'LIMIT' 单，但用 params 中的 'type' 覆盖它。
    # 这样 ccxt 会正确处理签名和参数结构，而币安会收到正确的 STOP 类型。
    params = {
        'type': real_api_type,  # <--- 核心：覆盖类型
        'stopPrice': trigger_price,  # 触发价
        'reduceOnly': True,  # 单向持仓必须
        'timeInForce': 'GTC'  # 限价单必须
    }

    try:
        # 使用 'LIMIT' 作为基础类型调用，确保 ccxt 包含 price 参数
        return await exchange.create_order(full_symbol, 'LIMIT', side, amount, limit_price, params)

    except ccxt.ExchangeError as e:
        error_msg = str(e)

        # 兜底：如果报 -4061 (Hedge Mode 冲突)
        if '-4061' in error_msg:
            # print(f"--- [DEBUG] 检测到 Hedge Mode，重试 {full_symbol} ---")
            params_hedge = params.copy()
            del params_hedge['reduceOnly']  # Hedge 模式移除 reduceOnly
            params_hedge['positionSide'] = 'LONG' if side.upper() == 'SELL' else 'SHORT'

            return await exchange.create_order(full_symbol, 'LIMIT', side, amount, limit_price, params_hedge)
        else:
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

        # 止损
        if sl_perc > 0:
            leverage = config.get('leverage', 1)
            sl_ratio = float(sl_perc) / 100 / leverage
            entry_price = position.entry_price

            if is_long:
                target_sl_price = entry_price * (1 - sl_ratio)
                sl_side = 'sell'
            else:
                target_sl_price = entry_price * (1 + sl_ratio)
                sl_side = 'buy'

            await async_logger(f"  > 准备提交 {position.symbol} SL (Limit Stop)...")
            tasks.append(_place_limit_stop_official(
                exchange, full_symbol, sl_side, position.contracts,
                target_sl_price, is_stop_loss=True, async_logger=async_logger
            ))

        # 止盈
        if tp_perc > 0:
            leverage = config.get('leverage', 1)
            tp_ratio = float(tp_perc) / 100 / leverage
            entry_price = position.entry_price

            if is_long:
                target_tp_price = entry_price * (1 + tp_ratio)
                tp_side = 'sell'
            else:
                target_tp_price = entry_price * (1 - tp_ratio)
                tp_side = 'buy'

            await async_logger(f"  > 准备提交 {position.symbol} TP (Limit TP)...")
            tasks.append(_place_limit_stop_official(
                exchange, full_symbol, tp_side, position.contracts,
                target_tp_price, is_stop_loss=False, async_logger=async_logger
            ))

        if not tasks:
            return True

        # 4. 执行
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = 0
        total_tasks = len(tasks)

        for res in results:
            if isinstance(res, dict) and res.get('id'):
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