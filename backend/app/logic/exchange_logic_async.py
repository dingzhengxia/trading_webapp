# backend/app/logic/exchange_logic_async.py (最终完整版)
import asyncio
import datetime
import ccxt.async_support as ccxt
from typing import List, Optional, Dict

from .utils import resolve_full_symbol
from ..models.schemas import Position
from ..config.config import load_settings
from ..config import i18n
from .sl_tp_logic_async import _cancel_sl_tp_orders_async
from .exceptions import RetriableOrderError, InterruptedError


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
                info, signed_contracts = raw_pos.get('info', {}), float(raw_pos['info'].get('positionAmt', 0.0))
                full_symbol, ticker = raw_pos['symbol'], tickers.get(raw_pos['symbol'])
                if not ticker: continue
                current_price = float(ticker.get('mark', ticker.get('last', 0.0)))
                notional = current_price * abs(signed_contracts)
                entry_price = float(raw_pos.get('entryPrice', 0.0))
                pnl = float(raw_pos.get('unrealizedPnl', 0.0))
                margin = float(raw_pos.get('initialMargin', 0.0)) or (notional / leverage if leverage > 0 else 0)
                pnl_percentage = (pnl / margin) * 100 if margin > 0 else 0.0
                final_positions.append(Position(
                    symbol=full_symbol.split('/')[0], full_symbol=full_symbol, side=raw_pos.get('side'),
                    contracts=abs(signed_contracts), entry_price=entry_price, notional=notional,
                    mark_price=current_price, pnl=pnl, pnl_percentage=pnl_percentage,
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
        if not target_pos: return True

        pos_amt = float(target_pos['info']['positionAmt'])
        amount_to_close = float(exchange.amount_to_precision(full_symbol_to_close, abs(pos_amt) * ratio))
        if amount_to_close <= 0: return True

        config = load_settings()
        order_result = await _execute_maker_order_with_retry_async(
            exchange, full_symbol_to_close, 'sell' if pos_amt > 0 else 'buy', {'reduceOnly': True},
            config.get('close_order_fill_timeout_seconds', 12), config.get('close_maker_retries', 3),
            async_logger, stop_event, contracts_to_trade=amount_to_close
        )
        if order_result and abs(ratio - 1.0) < 1e-9:
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
            if exchange.market(symbol).get('limits', {}).get('amount', {}).get('min', 0) > amount:
                raise ValueError(f"计算数量 {amount} 小于最小下单量。")

            if stop_event.is_set(): raise InterruptedError()
            order = await exchange.create_order(symbol, 'limit', side, amount, price, {**params, 'postOnly': True})
            order_id = order['id']
            await async_logger(f"✅ 限价单已提交！ID: {order['id']}")

            start_time = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start_time < timeout:
                if stop_event.is_set(): raise InterruptedError()
                if (await exchange.fetch_order(order_id, symbol))['status'] == 'closed':
                    await async_logger(f"✅ 订单 {order_id} 已成交！", "success")
                    return True
                await asyncio.sleep(2)

            raise RetriableOrderError(f"订单 {order_id} 超时未成交。")
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

            await async_logger(f"⚠️ 尝试失败 (第 {attempt + 1}/{retries + 1} 次)，可重试错误: {type(e).__name__}",
                               "warning")

            if attempt < retries:
                if stop_event.is_set(): raise InterruptedError()
                await asyncio.sleep(3)
            else:
                await async_logger(f"❌ 订单在 {retries + 1} 次尝试后仍然失败。", "error")
                return False
        except Exception as e:
            if order_id:
                try:
                    await exchange.cancel_order(order_id, symbol)
                except Exception:
                    pass
            await async_logger(f"🚨 发生严重错误: {e}", "error")
            raise

    return False


async def process_order_with_sl_tp_async(exchange: ccxt.binanceusdm, plan: dict, config: dict, async_logger,
                                         stop_event: asyncio.Event) -> bool:
    base_coin = plan['coin']
    full_symbol = resolve_full_symbol(exchange, base_coin)
    if not full_symbol: raise Exception(f"找不到 {base_coin} 的可用交易对。")
    if stop_event.is_set(): raise InterruptedError()
    await exchange.set_leverage(config['leverage'], full_symbol)

    filled = await _execute_maker_order_with_retry_async(
        exchange, full_symbol, plan['side'], {}, config['open_order_fill_timeout_seconds'],
        config['open_maker_retries'], async_logger, stop_event, value_to_trade=plan['value']
    )
    if not filled:
        return False

    if stop_event.is_set(): return False

    final_pos = None
    for _ in range(5):
        if stop_event.is_set(): raise InterruptedError()
        positions = await fetch_positions_with_pnl_async(exchange, config.get('leverage', 1))
        final_pos = next((p for p in positions if p.symbol == base_coin), None)
        if final_pos: break
        await asyncio.sleep(2)

    if not final_pos: raise Exception("下单成功后，无法获取最终仓位信息。")

    await set_tp_sl_for_position_async(exchange, final_pos, config, async_logger, stop_event)
    await async_logger(f"✅ {base_coin} 订单流程完全成功！", "success")
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