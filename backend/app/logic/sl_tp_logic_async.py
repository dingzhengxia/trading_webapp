# backend/app/logic/sl_tp_logic_async.py (全日志标准版)
import asyncio
from typing import Set, List, Dict, Any
import ccxt.async_support as ccxt
from ..config import i18n
from ..models.schemas import Position


async def _ensure_no_open_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger):
    """
    【全日志标准清理】
    1. 拉取全量订单 (不传 symbol)。
    2. 打印比对日志。
    3. 使用标准 cancel_order 删除。
    """
    max_retries = 5

    # 提取简单的特征，例如 "ADA/USDC:USDC" -> "ADA"
    try:
        simple_base = symbol.split('/')[0]  # ADA
    except:
        simple_base = symbol

    print(f"\n====== [DEBUG] 准备清理 {symbol} (特征: {simple_base}) ======", flush=True)

    for i in range(max_retries):
        try:
            # 1. 全量拉取 (不带参数!)
            # print(f"   >>> [REQ] fetch_open_orders()...", flush=True)
            all_orders = await exchange.fetch_open_orders()

            # 2. 打印前几个订单看看长什么样 (仅第一轮打印)
            if i == 0:
                print(f"   <<< [RES] 账户总订单数: {len(all_orders)}", flush=True)
                if len(all_orders) > 0:
                    sample = all_orders[0]
                    print(f"       [样板] ID: {sample['id']} | Symbol: {sample['symbol']} | Type: {sample['type']}",
                          flush=True)

            # 3. 本地筛选
            orders_to_cancel = []
            for o in all_orders:
                o_symbol = o['symbol']

                # --- 核心比对逻辑 ---
                # 只要订单的 symbol 包含我们的基础币种 (例如 ADAUSDC 包含 ADA)，就视为目标
                # 这种匹配非常宽泛，绝对不会漏掉
                if simple_base in o_symbol:
                    orders_to_cancel.append(o)
                    if i == 0:
                        print(f"       [MATCH] 命中需删除订单: {o_symbol} (ID: {o['id']})", flush=True)

            count = len(orders_to_cancel)

            if count == 0:
                if i > 0:
                    await async_logger(f"✅ {symbol} 挂单已清零。", "info")
                return True

            if i == 0:
                print(f"--- [CLEANUP] 锁定 {count} 个目标订单，执行逐个撤单... ---", flush=True)

            # 4. 逐个撤单 (标准接口)
            tasks = []
            for o in orders_to_cancel:
                # 这里的 symbol 传入订单自带的 symbol，确保不出错
                tasks.append(exchange.cancel_order(o['id'], o['symbol']))

            # 并发执行
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 检查结果
            for idx, res in enumerate(results):
                if isinstance(res, Exception):
                    err = str(res)
                    # 忽略 "Unknown order" (可能已经成交或被撤)
                    if "Unknown order" not in err and "Order was not found" not in err:
                        print(f"   !!! [ERR] 撤单失败 ID {orders_to_cancel[idx]['id']}: {err}", flush=True)

            # 5. 等待
            await asyncio.sleep(0.5 + (i * 0.2))

        except Exception as e:
            print(f"--- [FATAL] 清理异常: {e} ---", flush=True)
            await asyncio.sleep(1.0)

    await async_logger(f"❌ {symbol} 清理多次仍有残留，跳过下单。", "error")
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
    rate = max(0.1, min(20.0, float(callback_rate)))
    amount_str = exchange.amount_to_precision(symbol, amount)

    params = {
        'callbackRate': rate,
        'reduceOnly': True,
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"   >>> [REQ] 下单 {symbol} (Rate:{rate}%)...", flush=True)
            return await exchange.create_order(symbol, 'TRAILING_STOP_MARKET', side, amount_str, None, params)
        except Exception as e:
            err = str(e)
            print(f"   !!! [ERR] 下单失败: {err}", flush=True)

            # 冲突或超限 -> 清理
            if '-4045' in err or '-4130' in err or 'limit' in err:
                await _ensure_no_open_orders_async(exchange, symbol, async_logger)
                continue
            else:
                await async_logger(f"❌ {symbol} 下单失败: {err}", "error")
                return False
    return False


async def set_tp_sl_for_position_async(exchange: ccxt.binanceusdm, position: Position, config: dict, async_logger,
                                       stop_event: asyncio.Event) -> bool:
    full_symbol = position.full_symbol

    # 1. 清理
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
# 移除了 _place_standard_stop_order，只保留移动止盈