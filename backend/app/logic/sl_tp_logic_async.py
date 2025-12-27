# backend/app/logic/sl_tp_logic_async.py (精准清理版)
import asyncio
from typing import Set, List, Dict, Any
import ccxt.async_support as ccxt
from ..config import i18n
from ..models.schemas import Position


async def _ensure_no_open_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    【精准清理模式】
    只清理传入的 symbol。
    关键点：必须传入 params={'stop': True} 才能撤销移动止盈(条件单)。
    """
    # 用户要求：不需要拼装两种，只用传进来的 symbol
    target_sym = symbol

    # 循环尝试 3 次，防止网络抖动
    for i in range(3):
        try:
            # --- 第一刀：撤销普通订单 (Limit/Market) ---
            # 即使你没有普通单，发一下也无妨，防止有残留
            try:
                await exchange.cancel_all_orders(target_sym)
            except Exception as e:
                # 忽略 "No orders" 和 "Symbol not found"
                if "No orders" not in str(e) and "Symbol" not in str(e):
                    print(f"   [WARN] 普通撤单异常 ({target_sym}): {e}", flush=True)

            # --- 第二刀：撤销条件订单 (Trailing Stop/Stop Loss) ---
            # 【这是关键！】必须传 {'stop': True} CCXT 才会去调撤销条件单的接口
            try:
                await exchange.cancel_all_orders(target_sym, {'stop': True})
                # print(f"   >>> [SENT] 条件单撤销指令: {target_sym}")
            except Exception as e:
                if "No orders" not in str(e) and "Symbol" not in str(e):
                    print(f"   [WARN] 条件单撤单异常 ({target_sym}): {e}", flush=True)

        except Exception:
            pass

        # 稍等一下让交易所处理
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
    移动止盈下单
    """
    rate = max(0.1, min(20.0, float(callback_rate)))
    amount_str = exchange.amount_to_precision(symbol, amount)

    params = {
        'callbackRate': rate,
        'reduceOnly': True,
    }

    # 重试逻辑
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return await exchange.create_order(symbol, 'TRAILING_STOP_MARKET', side, amount_str, None, params)
        except Exception as e:
            err = str(e)
            print(f"   !!! [ERR] 下单失败 ({symbol}): {err}", flush=True)

            # 如果是冲突或满了，再清理一次 (带 stop 参数)
            if '-4045' in err or '-4130' in err or 'limit' in err:
                await _ensure_no_open_orders_async(exchange, symbol, async_logger)
                await asyncio.sleep(1.0)
                continue
            else:
                await async_logger(f"❌ {symbol} 移动止盈下单失败: {err}", "error")
                return False
    return False


async def set_tp_sl_for_position_async(exchange: ccxt.binanceusdm, position: Position, config: dict, async_logger,
                                       stop_event: asyncio.Event) -> bool:
    full_symbol = position.full_symbol

    # 1. 清理 (普通+条件)
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
            await async_logger(f"✅ {position.symbol} 移动止盈设置成功 (Rate:{callback_rate}%)", "success")
            return True
        else:
            return False

    return True


async def cleanup_orphan_sltp_orders_async(exchange: ccxt.binanceusdm, active_symbols: Set[str], async_logger):
    pass