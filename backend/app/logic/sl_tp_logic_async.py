# backend/app/logic/sl_tp_logic_async.py (盲发双杀版)
import asyncio
from typing import Set, List, Dict, Any
import ccxt.async_support as ccxt
from ..config import i18n
from ..models.schemas import Position


async def _ensure_no_open_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    res = await exchange.cancel_all_orders("BTC/USDC:USDC")
    res = await exchange.cancel_all_orders(symbol)
    print(f"   !!! [ERR] 下单失败 ({symbol}): {res}", flush=True)
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

            # 如果是冲突或满了，再盲删一次
            if '-4045' in err or '-4130' in err or 'limit' in err:
                await _ensure_no_open_orders_async(exchange, symbol, async_logger)
                await asyncio.sleep(1.0)  # 等久一点
                continue
            else:
                await async_logger(f"❌ {symbol} 移动止盈下单失败: {err}", "error")
                return False
    return False


async def set_tp_sl_for_position_async(exchange: ccxt.binanceusdm, position: Position, config: dict, async_logger,
                                       stop_event: asyncio.Event) -> bool:
    full_symbol = position.full_symbol

    # 1. 直接盲删
    await _ensure_no_open_orders_async(exchange, full_symbol, async_logger)

    if stop_event.is_set(): return False

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
            return False

    return True


async def cleanup_orphan_sltp_orders_async(exchange: ccxt.binanceusdm, active_symbols: Set[str], async_logger):
    pass
# 移除 _place_standard_stop_order