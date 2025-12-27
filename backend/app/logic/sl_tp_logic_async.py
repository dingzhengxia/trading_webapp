# backend/app/logic/sl_tp_logic_async.py (回归标准版)
import asyncio
from typing import Set, List, Dict, Any
import ccxt.async_support as ccxt
from ..config import i18n
from ..models.schemas import Position


async def _ensure_no_open_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    【标准清理模式】
    只使用 CCXT 标准方法。
    逻辑：先尝试 CancelAll -> 等待 -> 查单 -> 如果还有，按 ID 逐个撤销。
    """
    max_retries = 5

    for i in range(max_retries):
        try:
            # 1. 先尝试标准的一键全撤
            try:
                await exchange.cancel_all_orders(symbol)
                # print(f"   >>> [标准接口] 已发送 cancel_all_orders({symbol})")
            except Exception as e:
                # 如果报错 "No orders" 是正常的
                if "No orders" not in str(e):
                    print(f"   [WARN] cancel_all_orders 报错: {e}")

            # 2. 稍等片刻，让交易所飞一会儿
            await asyncio.sleep(0.5)

            # 3. 查单核实
            open_orders = await exchange.fetch_open_orders(symbol)

            if len(open_orders) == 0:
                if i > 0:
                    await async_logger(f"✅ {symbol} 挂单已清理。", "info")
                return True

            if i == 0:
                print(f"--- [CLEANUP] {symbol} 发现 {len(open_orders)} 个残留订单，执行 ID 补刀... ---")

            # 4. 如果还有，使用 ID 逐个撤销 (这是标准接口中最稳的)
            tasks = [exchange.cancel_order(o['id'], symbol) for o in open_orders]
            await asyncio.gather(*tasks, return_exceptions=True)

            # 5. 再等一下
            await asyncio.sleep(0.5)

        except Exception as e:
            print(f"--- [ERR] 清理异常: {e}")
            await asyncio.sleep(1.0)

    # 如果最后还有单子，为了防止下单报错，返回 False
    await async_logger(f"❌ {symbol} 清理超时，仍有挂单。", "error")
    return False


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
    # 限制范围
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
            # 冲突或超限 -> 再清理一次
            if '-4045' in err or '-4130' in err or 'limit' in err:
                print(f"--- [RETRY] {symbol} 下单拥堵，再次清理... ---")
                await _ensure_no_open_orders_async(exchange, symbol, async_logger)
                await asyncio.sleep(1.0)
                continue  # 重试
            else:
                # 其他错误 (如参数错误) 直接记录
                await async_logger(f"❌ {symbol} 移动止盈下单失败: {e}", "error")
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

    if enable_trailing:
        # === 移动止盈 ===
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

    # 如果没开启移动止盈，这里为了简单起见就不下固定止损了 (根据你之前的要求只保留移动止盈)
    # 且因为前面执行了清理，相当于把旧的固定止损也撤了
    return True


async def cleanup_orphan_sltp_orders_async(exchange: ccxt.binanceusdm, active_symbols: Set[str], async_logger):
    pass
# 移除 _place_standard_stop_order，既然只要移动止盈，那个就没用了