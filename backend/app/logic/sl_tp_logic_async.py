# backend/app/logic/sl_tp_logic_async.py
import asyncio
from typing import Set

import ccxt.async_support as ccxt

from ..config import constants
from ..core import exit_rules
from ..models.schemas import Position


def _amount_to_precision(exchange: ccxt.binanceusdm, symbol: str, amount: float) -> str:
    """数量精度转换，兼容离线 fake exchange 未实现该方法的场景。"""
    try:
        return str(exchange.amount_to_precision(symbol, amount))
    except Exception:
        return str(amount)


def _price_to_precision(exchange: ccxt.binanceusdm, symbol: str, price: float) -> str:
    """价格精度转换，兼容离线 fake exchange 未实现该方法的场景。"""
    try:
        return str(exchange.price_to_precision(symbol, price))
    except Exception:
        return str(price)


async def cancel_all_orders_async(exchange: ccxt.binanceusdm, symbol: str, async_logger=None) -> bool:
    """撤销指定交易对上的全部挂单（普通单 + 条件单）。

    ccxt 的 Binance 条件单需要传 {'stop': True} 才会走到撤销条件单的接口，
    因此这里保留两次调用；P1-7 已合并原先重复的两层包装与 3 次无谓循环。

    返回值：两次调用都成功才为 True。调用方在下单前应检查返回值，
    撤单失败时不得继续挂新单，否则会与旧条件单叠加。
    """
    ok = True
    for stop_params in (None, {'stop': True}):
        try:
            if stop_params is None:
                await exchange.cancel_all_orders(symbol)
            else:
                await exchange.cancel_all_orders(symbol, stop_params)
        except Exception as e:
            ok = False
            if async_logger:
                await async_logger(f"⚠️ {symbol} 撤销挂单失败: {e}", "warning")
    return ok


async def _place_trailing_stop_order(
        exchange: ccxt.binanceusdm,
        symbol: str,
        side: str,
        amount: float,
        callback_rate: float,
        async_logger
):
    """移动止盈下单（阶梯式降级）。"""
    amount_str = _amount_to_precision(exchange, symbol, amount)

    user_rate = max(0.1, min(20.0, float(callback_rate)))
    rates_to_try = [user_rate]

    # 用户设定大于 5.0 时进行细粒度降级：10 -> 9 -> ... -> 5
    if user_rate > 5.0:
        curr = user_rate - 1.0
        while curr > 5.0:
            rates_to_try.append(round(curr, 1))
            curr -= 1.0
        rates_to_try.append(5.0)

    # 添加保底
    if 2.0 not in rates_to_try and user_rate > 2.0:
        rates_to_try.append(2.0)

    for rate in rates_to_try:
        params = {
            'callbackRate': rate,
            'reduceOnly': True,
        }
        for attempt in range(2):
            try:
                return await exchange.create_order(
                    symbol, constants.ORDER_TYPE_TRAILING_STOP, side, amount_str, None, params
                )
            except Exception as e:
                err = str(e)
                # 情况A: 交易所明确拒绝这个比率 (-2007)，降级到下一个比率
                if '-2007' in err or 'Invalid callBack rate' in err:
                    await async_logger(f"⚠️ {symbol} 移动止盈回调率 {rate}% 被拒，尝试降级。", "warning")
                    break
                # 情况B: 订单拥堵 (-4045 / -4130)，清理后重试当前比率
                elif '-4045' in err or '-4130' in err:
                    await cancel_all_orders_async(exchange, symbol, async_logger)
                    await asyncio.sleep(1.0)
                    continue
                # 情况C: 其他错误
                else:
                    await async_logger(f"❌ {symbol} 移动止盈出错: {err}", "error")
                    return False

    await async_logger(f"❌ {symbol} 即使降级到 {rates_to_try[-1]}% 也无法下单。", "error")
    return False


async def _place_conditional_order_async(
        exchange: ccxt.binanceusdm,
        symbol: str,
        side: str,
        amount: float,
        trigger_price: float,
        order_type: str,
        async_logger
):
    """提交 reduce-only 条件单（STOP_MARKET / TAKE_PROFIT_MARKET）。"""
    price_str = _price_to_precision(exchange, symbol, trigger_price)
    amount_str = _amount_to_precision(exchange, symbol, amount)
    params = {'stopPrice': price_str, 'reduceOnly': True, 'workingType': 'MARK_PRICE'}

    for attempt in range(3):
        try:
            return await exchange.create_order(symbol, order_type, side, amount_str, None, params)
        except Exception as e:
            err = str(e)
            if '-4045' in err or '-4130' in err or 'limit' in err:
                await cancel_all_orders_async(exchange, symbol, async_logger)
                await asyncio.sleep(1.0)
                continue
            await async_logger(f"❌ {symbol} 条件单 {order_type} 下单失败: {err}", "error")
            return False
    await async_logger(f"❌ {symbol} 条件单 {order_type} 重试后仍失败。", "error")
    return False


async def _resolve_atr(full_symbol: str, config: dict, async_logger) -> float | None:
    """取实盘 ATR（走共享行情服务，带缓存与限流）。失败返回 None，由调用方回退百分比口径。

    周期优先跟随**信号自身周期**（`_signal_timeframe`，由 auto_open_from_signal 透传），
    其次才是全局 `signal_live_exit_timeframe`。两者不一致会让 1h 信号用 4h 的 ATR，
    止损宽一倍、单笔风险翻倍。
    """
    signal_tf = str(config.get('_signal_timeframe') or '').lower()
    timeframe = signal_tf if exit_rules.timeframe_ms(signal_tf) else \
        str(config.get('signal_live_exit_timeframe') or '4h')
    try:
        from ..signals.market_data import shared_market_data
        return await shared_market_data().atr_at(full_symbol, timeframe)
    except Exception as e:  # noqa: BLE001 - 行情失败不能影响挂单主流程
        await async_logger(f"⚠️ {full_symbol} 获取 ATR({timeframe}) 失败: {e}", "warning")
        return None


async def set_tp_sl_for_position_async(exchange: ccxt.binanceusdm, position: Position, config: dict, async_logger,
                                       stop_event: asyncio.Event) -> bool:
    """为一个仓位设置止盈止损（统一走 `core.exit_rules`，与纸面跟踪同一份实现）。

    口径由 `signal_exit_mode` 决定：
    - `percent`：long 止损 entry*(1-sl%/100/lev)，止盈 entry*(1+tp%/100/lev)；short 反向；
    - `atr`：止损 = N×ATR，止盈 = R×止损距离（ATR 取 `signal_live_exit_timeframe` 周期）。
      **ATR 拿不到时自动回退 percent**——绝不因为行情缺失而裸奔不挂止损。
    移动止盈模式：只挂 TRAILING_STOP_MARKET（保持原行为）。
    """
    full_symbol = position.full_symbol

    is_long = str(position.side).lower() == constants.SIDE_LONG
    side_key = constants.SIDE_LONG if is_long else constants.SIDE_SHORT
    exit_side = constants.ORDER_SIDE_SELL if is_long else constants.ORDER_SIDE_BUY

    trailing_enabled = bool(config.get(f'enable_{side_key}_trailing_stop', False))
    fixed_enabled = bool(config.get(f'enable_{side_key}_sl_tp', False))

    # 1. 未启用任何保护：保持现状，不撤销已有挂单（P0：曾因先撤单后判断开关而清空保护）
    if not trailing_enabled and not fixed_enabled:
        await async_logger(
            f"ℹ️ {position.symbol} 未启用止盈止损，保持现有挂单不变。", "info")
        return True

    contracts = float(position.contracts or 0)
    if contracts <= 0:
        await async_logger(f"⚠️ {position.symbol} 仓位数量无效，跳过止盈止损。", "warning")
        return False

    entry_price = float(position.entry_price or 0)
    if not trailing_enabled and entry_price <= 0:
        await async_logger(f"⚠️ {position.symbol} 入场价无效，跳过止盈止损。", "warning")
        return False

    # 2. 确认要重挂后才清理历史挂单；撤单失败则中止，避免新旧条件单叠加
    if not await cancel_all_orders_async(exchange, full_symbol, async_logger):
        await async_logger(
            f"❌ {position.symbol} 撤销历史挂单失败，已中止本次止盈止损设置（避免条件单叠加）。", "error")
        return False

    if stop_event.is_set():
        return False

    # 3. 移动止盈分支保持原行为：优先且仅挂 TRAILING_STOP_MARKET
    if trailing_enabled:
        callback_rate = config.get(f'{side_key}_trailing_stop_callback_rate', 1.0)
        res = await _place_trailing_stop_order(
            exchange, full_symbol, exit_side, contracts, callback_rate, async_logger
        )
        if isinstance(res, dict) and res.get('id'):
            info = res.get('info') or {}
            final_rate = info.get('priceRate') or callback_rate
            await async_logger(f"✅ {position.symbol} 移动止盈成功 (Rate:{final_rate}%)", "success")
            return True
        return False

    # 4. 固定止盈止损：价格计算统一走 core.exit_rules（与纸面跟踪共用同一份实现）
    mode = exit_rules.exit_mode(config)
    atr = await _resolve_atr(full_symbol, config, async_logger) if mode == exit_rules.ATR_MODE else None
    prices = exit_rules.exit_prices(
        entry_price, constants.SIDE_LONG if is_long else constants.SIDE_SHORT, config, atr=atr)
    if prices is None and mode == exit_rules.ATR_MODE and atr is None:
        # ATR 口径但行情不可用：回退百分比，宁可按老设置挂上，也不裸奔
        await async_logger(
            f"⚠️ {position.symbol} ATR 不可用，已回退百分比口径挂止损（避免无保护）。", "warning")
        prices = exit_rules.exit_prices(
            entry_price, constants.SIDE_LONG if is_long else constants.SIDE_SHORT, config,
            mode=exit_rules.PERCENT_MODE)
    if prices is None:
        await async_logger(f"ℹ️ {position.symbol} 止盈止损参数无效或未启用，跳过固定挂单。", "info")
        return True

    success = True

    sl_trigger = prices.get('stop_loss')
    if sl_trigger is not None:
        res = await _place_conditional_order_async(
            exchange, full_symbol, exit_side, contracts, sl_trigger,
            constants.ORDER_TYPE_STOP_MARKET, async_logger
        )
        if isinstance(res, dict) and res.get('id'):
            await async_logger(f"✅ {position.symbol} 固定止损成功 (触发价: {sl_trigger:.8g})", "success")
        else:
            await async_logger(f"❌ {position.symbol} 固定止损下单失败", "error")
            success = False

    tp_trigger = prices.get('take_profit')
    if tp_trigger is not None:
        res = await _place_conditional_order_async(
            exchange, full_symbol, exit_side, contracts, tp_trigger,
            constants.ORDER_TYPE_TAKE_PROFIT_MARKET, async_logger
        )
        if isinstance(res, dict) and res.get('id'):
            await async_logger(f"✅ {position.symbol} 固定止盈成功 (触发价: {tp_trigger:.8g})", "success")
        else:
            await async_logger(f"❌ {position.symbol} 固定止盈下单失败", "error")
            success = False

    return success


# 能兜住反向风险的条件单类型（止盈单不算保护，不能替代止损）
PROTECTIVE_ORDER_TYPES = {'STOP_MARKET', 'STOP', 'TRAILING_STOP_MARKET', 'TRAILING_STOP'}


def has_protective_order(orders: list, full_symbol: str, is_long: bool) -> bool:
    """判断某交易对是否已有 reduce-only 的止损/移动止损挂单。

    只认止损类：止盈单（TAKE_PROFIT_MARKET）不提供下行保护，不能算已挂保护。
    字段兼容 ccxt 统一结构（order['type']/['side']/['reduceOnly']）与交易所原始
    `info`（`type`/`side`/`reduceOnly`），两者任一命中即可。
    """
    target = str(full_symbol or '').upper()
    want_side = constants.ORDER_SIDE_SELL if is_long else constants.ORDER_SIDE_BUY
    for order in orders or []:
        if not isinstance(order, dict):
            continue
        if str(order.get('symbol') or '').upper() != target:
            continue
        info = order.get('info') or {}
        order_type = str(order.get('type') or info.get('type') or '').upper()
        if order_type not in PROTECTIVE_ORDER_TYPES:
            continue
        side = str(order.get('side') or info.get('side') or '').lower()
        if side and side != want_side:
            continue
        reduce_only = order.get('reduceOnly')
        if reduce_only is None:
            reduce_only = info.get('reduceOnly')
        if str(reduce_only).lower() in ('false', '0', 'no'):
            continue
        return True
    return False


async def ensure_positions_sltp_async(exchange: ccxt.binanceusdm, positions: list, config: dict,
                                      async_logger, stop_event: asyncio.Event) -> dict:
    """巡检所有持仓的止盈止损，缺止损的自动补挂（手动/自动开仓一视同仁）。

    这是「挂单失败」与「人为撤单」的兜底：开仓时 `process_order_with_sl_tp_async`
    已经挂过一次，但网络抖动、交易所拒绝或撤单冲突都可能让仓位裸奔；本函数每轮
    拉一次全量挂单，只对**完全没有止损**的仓位重新执行 `set_tp_sl_for_position_async`
    （它内部会先撤后挂，已有止损的仓位被跳过，不会重复叠加）。

    返回 {'checked': n, 'guarded': n, 'skipped': n, 'failed': n}。
    """
    stats = {'checked': 0, 'guarded': 0, 'skipped': 0, 'failed': 0}
    live = [p for p in (positions or []) if float(getattr(p, 'contracts', 0) or 0) > 0]
    if not live:
        return stats
    try:
        orders = await exchange.fetch_open_orders()
    except Exception as e:  # noqa: BLE001 - 查询失败不能影响主流程
        await async_logger(f"⚠️ 止盈止损巡检获取挂单失败，本轮跳过: {e}", "warning")
        return stats

    for pos in live:
        stats['checked'] += 1
        is_long = str(getattr(pos, 'side', '')).lower() == constants.SIDE_LONG
        side_key = constants.SIDE_LONG if is_long else constants.SIDE_SHORT
        if not bool(config.get(f'enable_{side_key}_sl_tp', False)) and \
                not bool(config.get(f'enable_{side_key}_trailing_stop', False)):
            stats['skipped'] += 1
            continue
        if has_protective_order(orders, getattr(pos, 'full_symbol', ''), is_long):
            stats['skipped'] += 1
            continue
        await async_logger(
            f"🛡️ {getattr(pos, 'symbol', '')} 未检测到止损单，自动补挂止盈止损。", "warning")
        ok = await set_tp_sl_for_position_async(exchange, pos, config, async_logger, stop_event)
        stats['guarded' if ok else 'failed'] += 1
    return stats


async def cleanup_orphan_sltp_orders_async(exchange: ccxt.binanceusdm, active_symbols: Set[str], async_logger) -> int:
    """清理"已无持仓的交易对"上残留的条件单/挂单。

    实现 P0-6：拉取全部挂单，撤销 symbol 不在当前持仓集合中的挂单。
    任何查询/撤销失败都只记录日志，不影响同步 SL/TP 主流程。
    """
    active_upper = {str(symbol).upper() for symbol in (active_symbols or set())}
    try:
        open_orders = await exchange.fetch_open_orders()
    except Exception as e:
        await async_logger(f"⚠️ 获取全部挂单失败，跳过孤儿条件单清理: {e}", "warning")
        return 0

    orphan_orders = []
    for order in open_orders or []:
        symbol = str((order or {}).get('symbol') or '')
        if symbol and symbol.upper() not in active_upper:
            orphan_orders.append(order)

    cancelled_count = 0
    for order in orphan_orders:
        try:
            await exchange.cancel_order(order.get('id'), order.get('symbol'))
            cancelled_count += 1
        except Exception as e:
            await async_logger(f"⚠️ 撤销孤儿挂单失败 {order.get('symbol')} {order.get('id')}: {e}", "warning")

    if cancelled_count:
        await async_logger(f"🧹 已清理 {cancelled_count} 个无持仓交易对的孤儿条件单。", "info")
    return cancelled_count
