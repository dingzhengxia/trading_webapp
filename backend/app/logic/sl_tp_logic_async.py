# backend/app/logic/sl_tp_logic_async.py (盲删版)
import asyncio
from typing import Set, List, Dict, Any
import ccxt.async_support as ccxt
from ..config import i18n
from ..models.schemas import Position


def _get_raw_symbol(ccxt_symbol: str) -> str:
    """
    ADA/USDC:USDC -> ADAUSDC
    """
    if not ccxt_symbol: return ""
    return ccxt_symbol.split(':')[0].replace('/', '')


async def _ensure_no_open_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    【盲删模式】
    不查询，不比对，直接发送删除指令。
    针对 USDC 交易对做了特别适配。
    """
    # 1. 解析出原生 Symbol (例如 ADAUSDC)
    raw_symbol = _get_raw_symbol(symbol)

    # print(f"--- [KILL] 正在清理 {symbol} (原生: {raw_symbol}) ---")

    # 2. 连续发送 3 次撤单指令，防止网络丢包
    # 只要有一次成功，目的就达到了
    for i in range(3):
        try:
            # 方案A: 币安底层接口 (最可靠)
            # fapiPrivateDeleteAllOpenOrders 既支持 USDT 也支持 USDC 合约
            await exchange.fapiPrivateDeleteAllOpenOrders({'symbol': raw_symbol})
            # print(f"   >>> [SENT] 原生撤单成功 ({i+1}/3)")

            # 如果成功了，稍微等一下让交易所处理，然后直接返回
            await asyncio.sleep(0.5)
            return True

        except Exception as e:
            err = str(e)
            # 如果报错 "No orders"，说明已经干净了，直接成功
            if "No orders" in err:
                return True

            # 其他错误 (比如网络超时)，打印一下，继续重试
            # print(f"   [RETRY] 撤单报错: {err}")

            # 方案B: 如果原生失败，尝试 CCXT 标准接口补刀
            try:
                await exchange.cancel_all_orders(symbol)
            except:
                pass

            await asyncio.sleep(0.5)

    return True  # 默认放行，不再阻塞下单，依靠下单时的错误重试来兜底


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
    # 1. 放宽限制到 20%
    rate = max(0.1, min(20.0, float(callback_rate)))
    amount_str = exchange.amount_to_precision(symbol, amount)

    # 2. 这里的 symbol 必须是 CCXT 格式 (ADA/USDC:USDC)
    params = {
        'callbackRate': rate,
        'reduceOnly': True,
    }

    # 3. 极简重试逻辑
    try:
        return await exchange.create_order(symbol, 'TRAILING_STOP_MARKET', side, amount_str, None, params)
    except Exception as e:
        err = str(e)
        # 如果是因为满了或者冲突，再清理一次
        if '-4045' in err or '-4130' in err or 'limit' in err:
            await async_logger(f"⚠️ {symbol} 订单拥堵，再次清理...", "warning")
            await _ensure_no_open_orders_async(exchange, symbol, async_logger)
            # 再试一次
            await asyncio.sleep(1.0)
            try:
                return await exchange.create_order(symbol, 'TRAILING_STOP_MARKET', side, amount_str, None, params)
            except Exception as final_e:
                await async_logger(f"❌ {symbol} 最终下单失败: {final_e}", "error")
                return False

        await async_logger(f"❌ {symbol} 下单报错: {e}", "error")
        return False


async def set_tp_sl_for_position_async(exchange: ccxt.binanceusdm, position: Position, config: dict, async_logger,
                                       stop_event: asyncio.Event) -> bool:
    full_symbol = position.full_symbol

    # 1. 上来先清理，不管有没有单
    await _ensure_no_open_orders_async(exchange, full_symbol, async_logger)

    if stop_event.is_set(): return False

    is_long = position.side == i18n.SIDE_LONG
    side_key = "long" if is_long else "short"

    enable_trailing = config.get(f'enable_{side_key}_trailing_stop', False)

    # 2. 只处理移动止盈
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

    return True  # 如果没开启移动止盈，也算成功


async def cleanup_orphan_sltp_orders_async(exchange: ccxt.binanceusdm, active_symbols: Set[str], async_logger):
    pass
# 移除 _place_standard_stop_order 以简化文件，反正不用了