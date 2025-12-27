# backend/app/logic/sl_tp_logic_async.py (阶梯降级版)
import asyncio
from typing import Set, List, Dict, Any
import ccxt.async_support as ccxt
from ..config import i18n
from ..models.schemas import Position


async def _ensure_no_open_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    【精准清理模式】
    调用两次 cancel_all_orders，第二次必须传入 {'stop': True} 以撤销条件单。
    """
    # 1. 确定目标列表 (同时处理 USDT 和 USDC)
    targets = [symbol]
    if "/USDC" in symbol:
        targets.append(symbol.replace("/USDC", "/USDT").replace(":USDC", ":USDT"))
    elif "/USDT" in symbol:
        targets.append(symbol.replace("/USDT", "/USDC").replace(":USDT", ":USDC"))

    # 2. 循环尝试 3 次
    for i in range(3):
        for target_sym in targets:
            try:
                # 撤销普通订单
                try:
                    await exchange.cancel_all_orders(target_sym)
                except Exception:
                    pass

                # 撤销条件订单 (关键)
                try:
                    await exchange.cancel_all_orders(target_sym, {'stop': True})
                except Exception:
                    pass
            except Exception:
                pass

        await asyncio.sleep(0.5)

    return True


# --- 兼容性包装器 ---
async def _cancel_sl_tp_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    return await _ensure_no_open_orders_async(exchange, symbol, async_logger)


async def _force_cancel_all_orders(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    return await _ensure_no_open_orders_async(exchange, symbol, async_logger)


# ------------------


async def _place_trailing_stop_order(
        exchange: ccxt.binanceusdm,
        symbol: str,
        side: str,
        amount: float,
        callback_rate: float,
        async_logger
):
    """
    移动止盈下单 (阶梯式降级)
    """
    amount_str = exchange.amount_to_precision(symbol, amount)

    # --- 构建重试阶梯 ---
    user_rate = max(0.1, min(20.0, float(callback_rate)))
    rates_to_try = [user_rate]

    # 如果用户设定值大于 5.0，进行细粒度降级 (每 1% 降一档)
    if user_rate > 5.0:
        curr = user_rate - 1.0
        while curr > 5.0:
            rates_to_try.append(round(curr, 1))
            curr -= 1.0
        rates_to_try.append(5.0)

    # 添加保底
    if 2.0 not in rates_to_try and user_rate > 2.0:
        rates_to_try.append(2.0)

    # ------------------

    for rate in rates_to_try:
        params = {
            'callbackRate': rate,
            'reduceOnly': True,
        }

        # 每个比率尝试 2 次 (处理网络或并发问题)
        for attempt in range(2):
            try:
                # print(f"   >>> [REQ] 下单 {symbol} (Rate:{rate}%)")
                return await exchange.create_order(symbol, 'TRAILING_STOP_MARKET', side, amount_str, None, params)

            except Exception as e:
                err = str(e)

                # 情况A: 交易所明确拒绝这个比率 (-2007)
                if '-2007' in err or 'Invalid callBack rate' in err:
                    print(f"   [WARN] {symbol} {rate}% 被拒，尝试降低...")
                    break  # 跳出内层循环，直接试下一个更小的比率

                # 情况B: 订单拥堵 (-4045 / -4130) -> 清理并重试当前比率
                elif '-4045' in err or '-4130' in err or 'limit' in err:
                    # print(f"   [RETRY] {symbol} 拥堵，清理后重试 {rate}%...")
                    await _ensure_no_open_orders_async(exchange, symbol, async_logger)
                    await asyncio.sleep(1.0)
                    continue

                    # 情况C: 其他错误
                else:
                    await async_logger(f"❌ {symbol} 移动止盈出错: {err}", "error")
                    return False

    await async_logger(f"❌ {symbol} 即使降级到 {rates_to_try[-1]}% 也无法下单。", "error")
    return False


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
    标准止损 (备用)
    """
    order_type = 'STOP_MARKET'
    price_str = exchange.price_to_precision(symbol, trigger_price)
    amount_str = exchange.amount_to_precision(symbol, amount)
    params = {'stopPrice': price_str, 'reduceOnly': True, 'workingType': 'MARK_PRICE'}

    for attempt in range(3):
        try:
            return await exchange.create_order(symbol, order_type, side, amount_str, None, params)
        except Exception as e:
            err = str(e)
            if '-4045' in err or '-4130' in err or 'limit' in err:
                await _ensure_no_open_orders_async(exchange, symbol, async_logger)
                await asyncio.sleep(1.0)
                continue
            return False
    return False


async def set_tp_sl_for_position_async(exchange: ccxt.binanceusdm, position: Position, config: dict, async_logger,
                                       stop_event: asyncio.Event) -> bool:
    full_symbol = position.full_symbol

    # 1. 启动前先清理
    await _ensure_no_open_orders_async(exchange, full_symbol, async_logger)

    if stop_event.is_set(): return False

    is_long = position.side == i18n.SIDE_LONG
    side_key = "long" if is_long else "short"

    enable_trailing = config.get(f'enable_{side_key}_trailing_stop', False)

    # 2. 下单
    if enable_trailing:
        callback_rate = config.get(f'{side_key}_trailing_stop_callback_rate', 1.0)
        ts_side = 'sell' if is_long else 'buy'

        res = await _place_trailing_stop_order(
            exchange, full_symbol, ts_side, position.contracts, callback_rate, async_logger
        )

        if isinstance(res, dict) and res.get('id'):
            # 获取最终成功的比率 (可能被降级了)
            final_rate = res.get('info', {}).get('priceRate')
            if not final_rate: final_rate = callback_rate

            # 如果成功，即使降级了也标记为绿色
            await async_logger(f"✅ {position.symbol} 移动止盈成功 (Rate:{final_rate}%)", "success")
            return True
        else:
            return False

    # 3. 备用固定止损
    else:
        if config.get(f'enable_{side_key}_sl_tp', False):
            sl_perc = config.get(f'{side_key}_stop_loss_percentage', 0)
            leverage = config.get('leverage', 1)

            if sl_perc > 0:
                sl_ratio = float(sl_perc) / 100 / leverage
                target_sl = position.entry_price * (1 - sl_ratio) if is_long else position.entry_price * (1 + sl_ratio)
                sl_side = 'sell' if is_long else 'buy'

                res = await _place_standard_stop_order(
                    exchange, full_symbol, sl_side, position.contracts, target_sl, True, async_logger
                )
                if isinstance(res, dict) and res.get('id'):
                    await async_logger(f"✅ {position.symbol} 固定止损成功", "success")
                    return True

    return True


async def cleanup_orphan_sltp_orders_async(exchange: ccxt.binanceusdm, active_symbols: Set[str], async_logger):
    pass