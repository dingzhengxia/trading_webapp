# backend/app/logic/exchange_logic_async.py
import asyncio
import datetime
from typing import Any, List, Optional

import ccxt.async_support as ccxt

from .exceptions import RetriableOrderError, InterruptedError
from .sl_tp_logic_async import cancel_all_orders_async, set_tp_sl_for_position_async
from .utils import resolve_symbol_details
from ..config import constants
from ..config.config import load_settings
from ..models.schemas import Position


def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """安全转换 float；NaN/inf 视为无效并返回 default。"""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if result != result or result in (float('inf'), float('-inf')):
        return default
    return result


def _amount_to_precision(exchange: ccxt.binanceusdm, symbol: str, amount: float) -> float:
    try:
        return float(exchange.amount_to_precision(symbol, amount))
    except Exception:
        return float(amount)


def _min_order_amount(exchange: ccxt.binanceusdm, symbol: str) -> Optional[float]:
    market = None
    try:
        market = exchange.market(symbol)
    except Exception:
        markets = getattr(exchange, 'markets', None) or {}
        market = markets.get(symbol)
    if not isinstance(market, dict):
        return None
    amount_limits = (market.get('limits') or {}).get('amount') or {}
    return _to_float(amount_limits.get('min'))


async def initialize_exchange_async(api_key: str, api_secret: str, use_testnet: bool, enable_proxy: bool,
                                    proxy_url: str) -> ccxt.binanceusdm:
    if not api_key or not api_secret:
        raise ConnectionError("API Key/Secret cannot be empty.")
    config = {'apiKey': api_key, 'secret': api_secret,
              'options': {'adjustForTimeDifference': True, "warnOnFetchOpenOrdersWithoutSymbol": False}}
    exchange = ccxt.binanceusdm(config)
    exchange.enableRateLimit = True
    if enable_proxy and proxy_url:
        exchange.https_proxy = proxy_url
        exchange.aiohttp_proxy = proxy_url
    if use_testnet:
        exchange.set_sandbox_mode(True)
    await exchange.load_markets()
    return exchange


def _position_side(raw_pos: dict) -> str:
    side = str((raw_pos or {}).get('side') or '').lower()
    if side in (constants.SIDE_LONG, constants.SIDE_SHORT):
        return side
    info = (raw_pos or {}).get('info') or {}
    amount = _to_float(info.get('positionAmt'))
    if amount is None:
        amount = _to_float(raw_pos.get('contracts'), 0.0) or 0.0
    return constants.SIDE_LONG if amount >= 0 else constants.SIDE_SHORT


async def fetch_positions_with_pnl_async(exchange: ccxt.binanceusdm, leverage: int) -> List[Position]:
    """获取带 PnL 的非零持仓。

    P0-5：不再吞掉交易所异常（由任务日志/全局异常处理呈现），
    并优先使用 position.info 的 markPrice/unRealizedProfit/notional/initialMargin
    计算，避免额外的全量 fetch_tickers 请求。
    """
    raw_positions = await exchange.fetch_positions(None)
    final_positions: List[Position] = []

    for raw_pos in raw_positions or []:
        info = (raw_pos or {}).get('info') or {}
        full_symbol = str(raw_pos.get('symbol') or info.get('symbol') or '')
        if not full_symbol:
            continue

        signed_contracts = _to_float(info.get('positionAmt'))
        if signed_contracts is None:
            contracts = _to_float(raw_pos.get('contracts'), 0.0) or 0.0
            side = _position_side(raw_pos)
            signed_contracts = -abs(contracts) if side == constants.SIDE_SHORT else abs(contracts)
        if signed_contracts == 0:
            continue

        entry_price = _to_float(info.get('breakEvenPrice'))
        if entry_price is None:
            entry_price = _to_float(raw_pos.get('entryPrice'), 0.0) or 0.0

        mark_price = _to_float(info.get('markPrice'))
        if mark_price is None:
            mark_price = _to_float(raw_pos.get('markPrice'))
        if mark_price is None or mark_price <= 0:
            mark_price = entry_price

        notional = _to_float(info.get('notional'))
        if notional is None:
            notional = _to_float(raw_pos.get('notional'))
        if notional is None or notional == 0:
            notional = mark_price * abs(signed_contracts)
        notional = abs(notional)

        pnl = _to_float(info.get('unRealizedProfit'))
        if pnl is None:
            pnl = _to_float(raw_pos.get('unrealizedPnl'))
        if pnl is None:
            pnl = 0.0

        margin = _to_float(info.get('initialMargin'))
        if margin is None:
            margin = _to_float(raw_pos.get('initialMargin'))
        if margin is None or margin <= 0:
            effective_leverage = leverage if leverage and leverage > 0 else 1
            margin = notional / effective_leverage if notional > 0 else 0.0

        pnl_percentage = (pnl / margin) * 100 if margin > 0 else 0.0

        final_positions.append(Position(
            symbol=full_symbol.split('/')[0],
            full_symbol=full_symbol,
            side=_position_side(raw_pos),
            contracts=abs(signed_contracts),
            entry_price=entry_price,
            notional=notional,
            mark_price=mark_price,
            pnl=pnl,
            pnl_percentage=pnl_percentage,
        ))

    return final_positions


async def _fetch_symbol_contracts_async(exchange: ccxt.binanceusdm, full_symbol: str) -> float:
    """查询指定交易对的剩余持仓数量（绝对值，0 表示已无持仓）。"""
    positions = await exchange.fetch_positions([full_symbol])
    remaining = 0.0
    for raw_pos in positions or []:
        if str((raw_pos or {}).get('symbol') or '') != full_symbol:
            continue
        contracts = abs(_to_float(raw_pos.get('contracts'), 0.0) or 0.0)
        if contracts == 0:
            info = (raw_pos or {}).get('info') or {}
            contracts = abs(_to_float(info.get('positionAmt'), 0.0) or 0.0)
        remaining = max(remaining, contracts)
    return remaining


async def close_position_async(exchange: ccxt.binanceusdm, full_symbol_to_close: str, ratio: float, async_logger,
                               stop_event: asyncio.Event) -> bool:
    """按比例平仓。

    P0-4：ratio==1 时成交后重新拉取持仓复核 contracts==0，必要时补平（最多 2 轮），
    仍有残留则返回 False，禁止后续反手裸开反向仓。
    P1-6：部分平仓成功后按剩余仓位重挂该仓位的 SL/TP。
    """
    try:
        if stop_event.is_set():
            raise InterruptedError()

        all_positions = await exchange.fetch_positions([full_symbol_to_close])
        target_pos = next(
            (p for p in (all_positions or [])
             if str((p or {}).get('symbol') or '') == full_symbol_to_close
             and abs(_to_float(p.get('contracts'), 0.0) or 0.0) != 0),
            None,
        )
        if not target_pos:
            await async_logger(f"平仓 {full_symbol_to_close} 时未找到持仓，可能已被手动关闭。", "info")
            return True

        info = target_pos.get('info') or {}
        pos_amt = _to_float(info.get('positionAmt'))
        if pos_amt is None:
            contracts = abs(_to_float(target_pos.get('contracts'), 0.0) or 0.0)
            pos_amt = contracts if str(target_pos.get('side') or '').lower() == constants.SIDE_LONG else -contracts
        if pos_amt == 0:
            await async_logger(f"平仓 {full_symbol_to_close} 时持仓数量为 0，跳过。", "info")
            return True

        config = load_settings()
        close_side = constants.ORDER_SIDE_SELL if pos_amt > 0 else constants.ORDER_SIDE_BUY
        amount_to_close = _amount_to_precision(exchange, full_symbol_to_close, abs(pos_amt) * ratio)
        if amount_to_close <= 0:
            await async_logger(f"计算出的平仓数量为0，跳过 {full_symbol_to_close}。", "info")
            return True

        close_timeout = int(config.get('close_order_fill_timeout_seconds', 12) or 12)
        close_retries = int(config.get('close_maker_retries', 3) or 3)
        order_result = await _execute_maker_order_with_retry_async(
            exchange, full_symbol_to_close, close_side, {'reduceOnly': True},
            close_timeout, close_retries, async_logger, stop_event,
            contracts_to_trade=amount_to_close
        )
        if not order_result:
            await async_logger(f"❌ {full_symbol_to_close} 平仓订单未能成交。", "error")
            return False

        if abs(ratio - 1.0) < 1e-9:
            # 全平复核：等待交易所状态刷新后重新拉取持仓
            await asyncio.sleep(0.5)
            remaining_contracts = None
            for retry_round in range(3):
                remaining_contracts = await _fetch_symbol_contracts_async(exchange, full_symbol_to_close)
                if remaining_contracts <= 1e-9:
                    break
                if retry_round >= 2:
                    break
                await async_logger(
                    f"⚠️ {full_symbol_to_close} 全平后仍残留 {remaining_contracts} 仓位，"
                    f"尝试第 {retry_round + 1} 次补平...", "warning"
                )
                retry_amount = _amount_to_precision(exchange, full_symbol_to_close, remaining_contracts)
                if retry_amount <= 0:
                    await async_logger(
                        f"❌ {full_symbol_to_close} 残留数量 {remaining_contracts} 低于最小下单精度，无法补平。",
                        "error")
                    return False
                order_result = await _execute_maker_order_with_retry_async(
                    exchange, full_symbol_to_close, close_side, {'reduceOnly': True},
                    close_timeout, close_retries, async_logger, stop_event,
                    contracts_to_trade=retry_amount
                )
                if not order_result:
                    await async_logger(f"❌ {full_symbol_to_close} 补平订单未能成交。", "error")
                    return False
                if stop_event.is_set():
                    raise InterruptedError()

            if remaining_contracts is None or remaining_contracts > 1e-9:
                await async_logger(
                    f"❌ {full_symbol_to_close} 全平后仍有残留仓位 ({remaining_contracts})，"
                    f"已阻止后续操作。", "error")
                return False

            await async_logger(f"✅ {full_symbol_to_close} 已完全平仓且复核无残留，清理其SL/TP挂单...", "info")
            await cancel_all_orders_async(exchange, full_symbol_to_close, async_logger)
        else:
            # 部分平仓：按剩余仓位重挂该仓位的 SL/TP（P1-6）
            remaining_positions = await fetch_positions_with_pnl_async(exchange, config.get('leverage', 1))
            current_pos = next(
                (p for p in remaining_positions if p.full_symbol == full_symbol_to_close), None)
            if current_pos:
                await set_tp_sl_for_position_async(exchange, current_pos, config, async_logger, stop_event)
            else:
                await async_logger(
                    f"⚠️ {full_symbol_to_close} 部分平仓后未查询到剩余仓位，跳过 SL/TP 重挂。", "warning")

        return True
    except InterruptedError:
        await async_logger(f"平仓操作 {full_symbol_to_close} 被中断。", "warning")
        return False
    except Exception as e:
        await async_logger(f"❌ {full_symbol_to_close} 平仓失败: {e}", "error")
        return False


async def _execute_maker_order_with_retry_async(exchange: ccxt.binanceusdm, symbol: str, side: str, params: dict,
                                                timeout: int, retries: int, async_logger, stop_event: asyncio.Event,
                                                value_to_trade: float = None, contracts_to_trade: float = None) -> bool:
    """限价 post-only 单执行器（开仓/平仓均走这里，禁止市价单）。

    P0-3：记录累计成交量，超时撤单后重试只下"目标数量 - 已成交量"的剩余量，
    剩余量低于最小下单量时停止，确保不会产生超额敞口。
    """
    if contracts_to_trade is None and not value_to_trade:
        raise ValueError("下单数量或下单价值必须提供其一。")

    params = dict(params or {})
    side = str(side).lower()
    target_amount: Optional[float] = float(contracts_to_trade) if contracts_to_trade else None
    total_filled = 0.0
    max_attempts = max(int(retries), 0) + 1
    order_fill_timeout = float(timeout)

    for attempt in range(max_attempts):
        if stop_event.is_set():
            raise InterruptedError()
        order_id = None
        try:
            order_book = await exchange.fetch_order_book(symbol, limit=5)
            bids = order_book.get('bids') or []
            asks = order_book.get('asks') or []
            if not bids or not asks:
                raise RetriableOrderError(f"{symbol} 盘口数据为空，无法确定限价。")
            price = float(bids[0][0]) if side == constants.ORDER_SIDE_BUY else float(asks[0][0])
            if price <= 0:
                raise RetriableOrderError(f"{symbol} 盘口价格无效: {price}")

            if target_amount is None:
                target_amount = _amount_to_precision(exchange, symbol, float(value_to_trade) / price)
                if target_amount <= 0:
                    raise ValueError(f"根据价值 {value_to_trade} 计算出的下单数量为 0。")

            remaining = _amount_to_precision(exchange, symbol, target_amount - total_filled)
            if remaining <= 0:
                await async_logger(
                    f"✅ {symbol} 已按目标数量全部成交（{total_filled}/{target_amount}），无需继续下单。", "success")
                return True

            min_amount = _min_order_amount(exchange, symbol)
            if min_amount and remaining < min_amount:
                if total_filled > 1e-12:
                    await async_logger(
                        f"⚠️ {symbol} 剩余数量 {remaining} 低于最小下单量 {min_amount}，停止重试"
                        f"（已成交 {total_filled}/{target_amount}，避免超额敞口）。", "warning")
                    return True
                raise ValueError(f"计算数量 {remaining} 小于最小下单量 {min_amount}。")

            if stop_event.is_set():
                raise InterruptedError()

            # 仅允许限价 post-only 单，禁止市价开仓
            order = await exchange.create_order(symbol, constants.ORDER_TYPE_LIMIT, side, remaining, price,
                                                {**params, 'postOnly': True})
            order_id = (order or {}).get('id')
            order_filled = _to_float((order or {}).get('filled'), 0.0) or 0.0
            await async_logger(
                f"✅ {symbol} 限价单已提交 (ID: {order_id})，价格: {price}，数量: {remaining}，等待成交...")

            timed_out = True
            loop = asyncio.get_running_loop()
            start_time = loop.time()
            while loop.time() - start_time < order_fill_timeout:
                if stop_event.is_set():
                    raise InterruptedError()
                fetched_order = await exchange.fetch_order(order_id, symbol)
                order_filled = max(order_filled, _to_float((fetched_order or {}).get('filled'), 0.0) or 0.0)
                if (fetched_order or {}).get('status') == 'closed':
                    timed_out = False
                    break
                await asyncio.sleep(2)

            if timed_out:
                try:
                    await exchange.cancel_order(order_id, symbol)
                except Exception:
                    pass
                # 撤单后重新读取最终成交量，避免漏算撤单前成交的部分
                try:
                    fetched_order = await exchange.fetch_order(order_id, symbol)
                    order_filled = max(order_filled, _to_float((fetched_order or {}).get('filled'), 0.0) or 0.0)
                except Exception:
                    pass

            total_filled += order_filled

            if not timed_out:
                await async_logger(f"✅ {symbol} 订单 {order_id} 已成交！", "success")
                return True

            raise RetriableOrderError(
                f"订单 {order_id} 在 {order_fill_timeout} 秒内超时未成交（本单成交 {order_filled}）。")

        except InterruptedError:
            if order_id:
                try:
                    await exchange.cancel_order(order_id, symbol)
                except Exception:
                    pass
            raise

        except (ccxt.RequestTimeout, ccxt.DDoSProtection, ccxt.ExchangeNotAvailable, ccxt.OrderImmediatelyFillable,
                ccxt.OrderNotFillable, RetriableOrderError) as e:
            if order_id:
                try:
                    await exchange.cancel_order(order_id, symbol)
                except Exception:
                    pass

            await async_logger(
                f"⚠️ {symbol} 订单尝试失败 (第 {attempt + 1}/{max_attempts} 次)，可重试错误: {type(e).__name__}",
                "warning")

            if attempt < max_attempts - 1:
                if stop_event.is_set():
                    raise InterruptedError()
                await asyncio.sleep(3)
            else:
                await async_logger(f"❌ {symbol} 订单在 {max_attempts} 次尝试后仍然失败。", "error")
                return False

        except Exception as e:
            if order_id:
                try:
                    await exchange.cancel_order(order_id, symbol)
                except Exception:
                    pass
            await async_logger(f"🚨 {symbol} 订单发生严重错误: {e}", "error")
            raise

    return False


async def _set_leverage_safe_async(exchange: ccxt.binanceusdm, symbol: str, target_leverage: int, async_logger) -> int:
    """尝试设置杠杆，失败时按阶梯自动降级（target -> 10 -> 5 -> 2 -> 1）。"""
    ladder = sorted(list(set([target_leverage, 10, 5, 2, 1])), reverse=True)
    ladder = [lev for lev in ladder if lev <= target_leverage]

    for lev in ladder:
        try:
            await exchange.set_leverage(lev, symbol)
            if lev != target_leverage:
                await async_logger(f"⚠️ {symbol} 杠杆 {target_leverage}x 不支持，已自动降级为 {lev}x", "warning")
            return lev
        except Exception as e:
            error_msg = str(e)
            if 'Leverage' in error_msg or '-4028' in error_msg:
                continue
            raise e

    raise ValueError(f"无法为 {symbol} 设置任何有效杠杆。")


async def process_order_with_sl_tp_async(exchange: ccxt.binanceusdm, plan: dict, config: dict, async_logger,
                                         stop_event: asyncio.Event) -> bool:
    """限价 post-only 开仓 -> 拉取实际仓位 -> 挂 SL/TP。"""
    base_coin = str(plan.get('coin') or '').strip().upper()
    full_symbol, quote = resolve_symbol_details(exchange, base_coin)
    if not full_symbol:
        raise Exception(f"找不到 {base_coin} 的可用交易对。")
    await async_logger(f"✅ {base_coin} 交易对: {full_symbol} ({quote} 优先)", "info")
    if stop_event.is_set():
        raise InterruptedError()

    desired_leverage = int(config.get('leverage', 1) or 1)
    actual_leverage = await _set_leverage_safe_async(exchange, full_symbol, desired_leverage, async_logger)

    side = str(plan.get('side') or '').lower()
    filled = await _execute_maker_order_with_retry_async(
        exchange, full_symbol, side, {},
        int(config.get('open_order_fill_timeout_seconds', 60) or 60),
        int(config.get('open_maker_retries', 5) or 5),
        async_logger, stop_event, value_to_trade=plan.get('value')
    )
    if not filled:
        return False
    if stop_event.is_set():
        return False

    # P0-2：优先按 full_symbol（必要时加上方向）精确匹配刚成交的仓位，
    # 避免同币种 USDC/USDT 合约或历史残留仓位导致止盈止损挂错。
    expected_side = constants.SIDE_LONG if side == constants.ORDER_SIDE_BUY else constants.SIDE_SHORT
    final_pos = None
    for _ in range(5):
        if stop_event.is_set():
            raise InterruptedError()
        positions = await fetch_positions_with_pnl_async(exchange, actual_leverage)
        final_pos = next(
            (p for p in positions
             if p.full_symbol == full_symbol and str(p.side).lower() == expected_side),
            None,
        )
        if not final_pos:
            final_pos = next((p for p in positions if p.full_symbol == full_symbol), None)
        if not final_pos:
            final_pos = next((p for p in positions if str(p.symbol).upper() == base_coin), None)
        if final_pos:
            break
        await asyncio.sleep(2)

    if not final_pos:
        raise Exception("下单成功后，无法获取最终仓位信息。")

    # 将 leverage 替换为实际成功的杠杆，保证金百分比计算依赖它
    effective_config = dict(config)
    effective_config['leverage'] = actual_leverage
    await set_tp_sl_for_position_async(exchange, final_pos, effective_config, async_logger, stop_event)

    await async_logger(
        f"✅ {base_coin} 订单流程完全成功！(交易对: {full_symbol}, 杠杆: {actual_leverage}x)", "success")
    return True


async def fetch_klines_async(exchange: ccxt.binanceusdm, symbol: str, timeframe: str = '1d', days_ago: int = 61) -> \
        Optional[List]:
    if not symbol:
        return None
    try:
        since = exchange.parse8601(
            (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)).isoformat())
        return await exchange.fetch_ohlcv(symbol, timeframe, since, limit=days_ago + 2)
    except ccxt.BadSymbol:
        return None
    except Exception:
        return None
