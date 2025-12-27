# backend/app/logic/exchange_logic_async.py (完整修复版)
import asyncio
import datetime
from typing import List, Optional

import ccxt.async_support as ccxt

from .exceptions import RetriableOrderError, InterruptedError
from .sl_tp_logic_async import _cancel_sl_tp_orders_async, set_tp_sl_for_position_async
from .utils import resolve_full_symbol
from ..config import i18n
from ..config.config import load_settings
from ..models.schemas import Position


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


async def fetch_positions_with_pnl_async(exchange: ccxt.binanceusdm, leverage: int) -> List[Position]:
    try:
        raw_positions = await exchange.fetch_positions(None)
        non_zero_positions = [p for p in raw_positions if float(p.get('contracts', 0) or 0) != 0]
        if not non_zero_positions: return []
        symbols = [p['symbol'] for p in non_zero_positions]
        tickers = await exchange.fetch_tickers(symbols)
        final_positions = []
        for raw_pos in non_zero_positions:
            try:
                info = raw_pos.get('info', {})
                signed_contracts = float(info.get('positionAmt', 0.0))
                full_symbol = raw_pos['symbol']
                ticker = tickers.get(full_symbol)

                if not ticker: continue

                # 1. 获取关键价格
                mark_price = float(ticker.get('mark', ticker.get('last', 0.0)))
                break_even_price = float(info.get('breakEvenPrice', raw_pos.get('entryPrice', 0.0)))

                # 2. 重新计算 PNL
                pnl = (mark_price - break_even_price) * signed_contracts

                # 3. 获取其他必要数据
                notional = mark_price * abs(signed_contracts)
                # 使用传入的 leverage 计算保证金，或者使用 API 返回的
                margin = float(raw_pos.get('initialMargin', 0.0)) or (notional / leverage if leverage > 0 else 0)

                # 4. 重新计算 PNL 百分比
                pnl_percentage = (pnl / margin) * 100 if margin > 0 else 0.0

                final_positions.append(Position(
                    symbol=full_symbol.split('/')[0],
                    full_symbol=full_symbol,
                    side=raw_pos.get('side'),
                    contracts=abs(signed_contracts),
                    entry_price=break_even_price,
                    notional=notional,
                    mark_price=mark_price,
                    pnl=pnl,
                    pnl_percentage=pnl_percentage,
                ))
            except (TypeError, ValueError, KeyError) as e:
                print(f"Error processing position {raw_pos.get('symbol', 'N/A')}: {e}")
        return final_positions
    except Exception as e:
        print(f"Error during fetch_positions_with_pnl_async: {e}")
        return []


async def close_position_async(exchange: ccxt.binanceusdm, full_symbol_to_close: str, ratio: float, async_logger,
                               stop_event: asyncio.Event):
    try:
        if stop_event.is_set(): raise InterruptedError()
        all_positions = await exchange.fetch_positions([full_symbol_to_close])
        target_pos = next(
            (p for p in all_positions if p['symbol'] == full_symbol_to_close and float(p.get('contracts', 0)) != 0),
            None)
        if not target_pos:
            await async_logger(f"平仓 {full_symbol_to_close} 时未找到持仓，可能已被手动关闭。", "info")
            return True

        pos_amt = float(target_pos['info']['positionAmt'])
        amount_to_close = float(exchange.amount_to_precision(full_symbol_to_close, abs(pos_amt) * ratio))
        if amount_to_close <= 0:
            await async_logger(f"计算出的平仓数量为0，跳过 {full_symbol_to_close}。", "info")
            return True

        config = load_settings()
        order_result = await _execute_maker_order_with_retry_async(
            exchange, full_symbol_to_close, 'sell' if pos_amt > 0 else 'buy', {'reduceOnly': True},
            config.get('close_order_fill_timeout_seconds', 12), config.get('close_maker_retries', 3),
            async_logger, stop_event, contracts_to_trade=amount_to_close
        )

        if order_result and abs(ratio - 1.0) < 1e-9:
            await async_logger(f"✅ {full_symbol_to_close} 已完全平仓，准备清理其SL/TP挂单...", "info")
            await _cancel_sl_tp_orders_async(exchange, full_symbol_to_close, async_logger)

        return order_result
    except InterruptedError:
        await async_logger(f"平仓操作 {full_symbol_to_close} 被中断。", "warning")
        return False
    except Exception as e:
        await async_logger(f"❌ {full_symbol_to_close} 平仓失败: {e}", "error")
        return False


async def _execute_maker_order_with_retry_async(exchange: ccxt.binanceusdm, symbol: str, side: str, params: dict,
                                                timeout: int, retries: int, async_logger, stop_event: asyncio.Event,
                                                value_to_trade: float = None, contracts_to_trade: float = None) -> bool:
    order_id = None
    for attempt in range(retries + 1):
        if stop_event.is_set(): raise InterruptedError()
        try:
            order_book = await exchange.fetch_order_book(symbol, limit=5)
            price = order_book['bids'][0][0] if side == i18n.ORDER_SIDE_BUY else order_book['asks'][0][0]
            amount = contracts_to_trade or float(exchange.amount_to_precision(symbol, (value_to_trade or 0) / price))

            min_amount = exchange.market(symbol).get('limits', {}).get('amount', {}).get('min')
            if min_amount and amount < min_amount:
                raise ValueError(f"计算数量 {amount} 小于最小下单量 {min_amount}。")

            if stop_event.is_set(): raise InterruptedError()
            order = await exchange.create_order(symbol, 'limit', side, amount, price, {**params, 'postOnly': True})
            order_id = order['id']
            await async_logger(f"✅ {symbol} 限价单已提交 (ID: {order['id']})，等待成交...")

            start_time = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start_time < timeout:
                if stop_event.is_set(): raise InterruptedError()
                fetched_order = await exchange.fetch_order(order_id, symbol)
                if fetched_order['status'] == 'closed':
                    await async_logger(f"✅ {symbol} 订单 {order_id} 已成交！", "success")
                    return True
                await asyncio.sleep(2)

            raise RetriableOrderError(f"订单 {order_id} 在 {timeout} 秒内超时未成交。")
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

            error_msg = f"⚠️ {symbol} 订单尝试失败 (第 {attempt + 1}/{retries + 1} 次)，可重试错误: {type(e).__name__}"
            await async_logger(error_msg, "warning")

            if attempt < retries:
                if stop_event.is_set(): raise InterruptedError()
                await asyncio.sleep(3)
            else:
                await async_logger(f"❌ {symbol} 订单在 {retries + 1} 次尝试后仍然失败。", "error")
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
    """
    尝试设置杠杆，如果失败则自动降级 (20 -> 10 -> 5 -> 2 -> 1)。
    返回最终成功设置的杠杆值。
    """
    # 定义降级阶梯，确保包含目标杠杆
    ladder = sorted(list(set([target_leverage, 10, 5, 2, 1])), reverse=True)
    # 过滤掉比目标杠杆还大的（如果用户设置了15，列表变成 [15, 10, 5...]）
    ladder = [l for l in ladder if l <= target_leverage]

    for lev in ladder:
        try:
            await exchange.set_leverage(lev, symbol)
            if lev != target_leverage:
                await async_logger(f"⚠️ {symbol} 杠杆 {target_leverage}x 不支持，已自动降级为 {lev}x", "warning")
            return lev
        except Exception as e:
            error_msg = str(e)
            # 捕获 -4028 (Leverage not valid) 或其他相关错误
            if 'Leverage' in error_msg or '-4028' in error_msg:
                continue  # 尝试下一个等级
            else:
                # 如果是网络错误等其他问题，直接抛出
                raise e

    # 如果所有都失败（极不可能），抛出异常
    raise ValueError(f"无法为 {symbol} 设置任何有效杠杆。")


async def process_order_with_sl_tp_async(exchange: ccxt.binanceusdm, plan: dict, config: dict, async_logger,
                                         stop_event: asyncio.Event) -> bool:
    base_coin = plan['coin']
    full_symbol = resolve_full_symbol(exchange, base_coin)
    if not full_symbol: raise Exception(f"找不到 {base_coin} 的可用交易对。")
    if stop_event.is_set(): raise InterruptedError()

    # 1. 设置杠杆 (使用带重试降级的新逻辑)
    desired_leverage = config.get('leverage', 1)
    actual_leverage = await _set_leverage_safe_async(exchange, full_symbol, desired_leverage, async_logger)

    # 2. 执行开仓
    filled = await _execute_maker_order_with_retry_async(
        exchange, full_symbol, plan['side'], {}, config['open_order_fill_timeout_seconds'],
        config['open_maker_retries'], async_logger, stop_event, value_to_trade=plan['value']
    )
    if not filled:
        return False

    if stop_event.is_set(): return False

    # 3. 获取持仓并设置止盈止损
    final_pos = None
    for _ in range(5):
        if stop_event.is_set(): raise InterruptedError()
        positions = await fetch_positions_with_pnl_async(exchange, actual_leverage)  # 使用实际杠杆
        final_pos = next((p for p in positions if p.symbol == base_coin), None)
        if final_pos: break
        await asyncio.sleep(2)

    if not final_pos: raise Exception("下单成功后，无法获取最终仓位信息。")

    # 4. 创建一个临时的 config 副本，将 leverage 替换为实际成功的 leverage
    # 这一点非常重要，因为 SL/TP 的百分比计算依赖于杠杆
    effective_config = config.copy()
    effective_config['leverage'] = actual_leverage

    await set_tp_sl_for_position_async(exchange, final_pos, effective_config, async_logger, stop_event)

    await async_logger(f"✅ {base_coin} 订单流程完全成功！(杠杆: {actual_leverage}x)", "success")
    return True


async def fetch_klines_async(exchange: ccxt.binanceusdm, symbol: str, timeframe: str = '1d', days_ago: int = 61) -> \
        Optional[List]:
    if not symbol: return None
    try:
        since = exchange.parse8601(
            (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)).isoformat())
        return await exchange.fetch_ohlcv(symbol, timeframe, since, limit=days_ago + 2)
    except ccxt.BadSymbol:
        return None
    except Exception as e:
        print(f"Error fetching klines for '{symbol}': {e}")
        return None