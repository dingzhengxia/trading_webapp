# backend/app/logic/exchange_logic_async.py (完整代码)
import asyncio
import datetime
import ccxt.async_support as ccxt
from typing import List, Optional, Dict

from .utils import resolve_full_symbol
from ..models.schemas import Position
from ..config.config import load_settings
from ..config import i18n
from .sl_tp_logic_async import _cancel_sl_tp_orders_async


class RetriableOrderError(Exception): pass


class InterruptedError(Exception): pass


async def initialize_exchange_async(api_key: str, api_secret: str, use_testnet: bool, enable_proxy: bool,
                                    proxy_url: str) -> ccxt.binanceusdm:
    if not api_key or not api_secret:
        raise ConnectionError("API Key/Secret cannot be empty.")

    config = {
        'apiKey': api_key,
        'secret': api_secret,
        'options': {'adjustForTimeDifference': True, "warnOnFetchOpenOrdersWithoutSymbol": False},
    }

    exchange = ccxt.binanceusdm(config)
    exchange.enableRateLimit = True

    if enable_proxy and proxy_url:
        print(f"Enabling proxy: {proxy_url}")
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

                current_price = float(ticker.get('mark', ticker.get('last', 0.0)))
                notional = current_price * abs(signed_contracts)
                break_even_price = float(info.get('breakEvenPrice', 0.0))
                initial_margin = float(info.get('initialMargin', 0.0))
                pnl = (current_price - break_even_price) * signed_contracts if break_even_price > 0 else float(
                    info.get('unRealizedProfit', 0.0))
                margin_for_calc = initial_margin or (notional / leverage if leverage > 0 else 0)
                pnl_percentage = (pnl / margin_for_calc) * 100 if margin_for_calc > 0 else 0.0
                base_coin_symbol = full_symbol.split('/')[0].split(':')[0]

                pos_obj = Position(
                    symbol=base_coin_symbol, full_symbol=full_symbol, side=raw_pos.get('side'),
                    contracts=abs(signed_contracts), entry_price=float(raw_pos.get('entryPrice', 0.0)),
                    notional=notional, mark_price=current_price, pnl=pnl, pnl_percentage=pnl_percentage,
                )
                final_positions.append(pos_obj)
            except (TypeError, ValueError, KeyError) as e:
                print(f"Error processing position {raw_pos.get('symbol', 'N/A')}: {e}")
                continue
        return final_positions
    except Exception as e:
        print(f"Error during fetch_positions_with_pnl_async: {e}")
        return []


async def close_position_async(exchange: ccxt.binanceusdm, full_symbol_to_close: str, ratio: float, async_logger):
    base_coin = full_symbol_to_close.split('/')[0]
    await async_logger(f"准备为 {full_symbol_to_close} 执行平仓，比例 {ratio * 100:.1f}%...")

    try:
        all_positions = await exchange.fetch_positions([full_symbol_to_close])
        target_pos = next(
            (p for p in all_positions if p['symbol'] == full_symbol_to_close and float(p.get('contracts', 0)) != 0),
            None)

        if not target_pos:
            await async_logger(f"最终确认失败：未找到 {full_symbol_to_close} 的有效持仓。", "info")
            return True  # No position is a form of success for closing

        pos_amt = float(target_pos['info']['positionAmt'])
        close_side = 'sell' if pos_amt > 0 else 'buy'
        amount_to_close = float(exchange.amount_to_precision(full_symbol_to_close, abs(pos_amt) * ratio))

        if amount_to_close <= 0:
            await async_logger("计算出的平仓数量为0，跳过。", "warning")
            return True

        config = load_settings()
        order_result = await _execute_maker_order_with_retry_async(
            exchange, full_symbol_to_close, close_side, {'reduceOnly': True},
            config.get('close_order_fill_timeout_seconds', 12),
            config.get('close_maker_retries', 3), async_logger, asyncio.Event(),
            # Stop event is handled by cancellation
            contracts_to_trade=amount_to_close
        )

        if order_result and abs(ratio - 1.0) < 1e-9:
            await _cancel_sl_tp_orders_async(exchange, full_symbol_to_close, async_logger)

        return order_result is not None
    except Exception as e:
        await async_logger(f"❌ {base_coin} ({full_symbol_to_close}) 平仓失败: {e}", "error")
        return False


async def fetch_klines_async(exchange: ccxt.binanceusdm, symbol: str, timeframe: str = '1d', days_ago: int = 61) -> \
Optional[List]:
    if not symbol: return None
    try:
        since = exchange.parse8601((datetime.datetime.utcnow() - datetime.timedelta(days=days_ago)).isoformat() + 'Z')
        return await exchange.fetch_ohlcv(symbol, timeframe, since, limit=days_ago + 1)
    except ccxt.BadSymbol:
        return None
    except Exception:
        return None


async def _execute_maker_order_with_retry_async(
        exchange: ccxt.binanceusdm, symbol: str, side: str, params: dict, timeout: int, retries: int,
        async_logger, stop_event: asyncio.Event,
        value_to_trade: float = None, contracts_to_trade: float = None):
    order_id = None
    order_type_log = "开仓" if not params.get('reduceOnly') else "平仓"

    for attempt in range(retries + 1):
        if stop_event.is_set(): raise InterruptedError(f"{order_type_log} a priori cancelled.")

        try:
            if attempt > 0: await async_logger(f"正在进行第 {attempt + 1}/{retries + 1} 次重试...")

            order_book = await exchange.fetch_order_book(symbol, limit=5)
            price = order_book['bids'][0][0] if side == i18n.ORDER_SIDE_BUY else order_book['asks'][0][0]

            if contracts_to_trade is not None:
                amount = contracts_to_trade
            elif value_to_trade:
                amount = float(exchange.amount_to_precision(symbol, float(value_to_trade) / price))
                min_amount = exchange.market(symbol).get('limits', {}).get('amount', {}).get('min', 0)
                if min_amount and amount < min_amount:
                    raise ValueError(f"计算数量 {amount} 小于最小下单量 {min_amount}。")
            else:
                raise ValueError("必须提供价值或数量。")

            if stop_event.is_set(): raise InterruptedError("Cancelled before placing order.")

            final_params = {**params, 'postOnly': True}
            order = await exchange.create_order(symbol, 'limit', side, amount, price, final_params)
            order_id = order['id']
            await async_logger(f"✅ '{order_type_log}' 限价单已提交！ID: {order['id']}")

            start_time = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start_time < timeout:
                if stop_event.is_set(): raise InterruptedError("Cancelled while waiting for fill.")

                try:
                    order_status = await exchange.fetch_order(order_id, symbol)
                    if order_status['status'] == 'closed':
                        await async_logger(f"✅ 订单 {order_id} 已成交！", "success")
                        return order_status
                except ccxt.OrderNotFound:
                    pass
                await asyncio.sleep(2)

            await exchange.cancel_order(order_id, symbol)
            raise RetriableOrderError(f"订单 {order_id} 在 {timeout}s 内未成交。")

        except (InterruptedError, asyncio.CancelledError) as e:
            if order_id:
                await async_logger(f"收到停止信号，正在尝试取消订单 {order_id}...", "warning")
                try:
                    await exchange.cancel_order(order_id, symbol)
                    await async_logger(f"✅ 订单 {order_id} 已成功取消。", "success")
                except Exception as cancel_exc:
                    await async_logger(f"⚠️ 尝试取消订单 {order_id} 时出错: {cancel_exc}", "warning")
            raise InterruptedError("操作被用户取消。") from e

        except (ccxt.RequestTimeout, ccxt.DDoSProtection, ccxt.ExchangeNotAvailable, ccxt.OrderImmediatelyFillable,
                ccxt.OrderNotFillable, RetriableOrderError) as e:
            await async_logger(f"尝试失败: 可重试错误: {e}", "warning")
            if attempt >= retries:
                await async_logger(f"❌ '{order_type_log}' 订单在 {retries + 1} 次尝试后仍然失败。", "error")
                raise
        except Exception as e:
            if order_id: await exchange.cancel_order(order_id, symbol, {'clientOrderId': f'error-cancel-{order_id}'})
            raise


async def process_order_with_sl_tp_async(exchange: ccxt.binanceusdm, plan: dict, config: dict, async_logger,
                                         stop_event: asyncio.Event):
    base_coin = plan['coin']
    await async_logger(f"--- 开始为 {base_coin} 处理完整开仓流程 ---")

    full_symbol = resolve_full_symbol(exchange, base_coin)
    if not full_symbol: raise Exception(f"找不到 {base_coin} 的可用交易对。")
    if stop_event.is_set(): raise InterruptedError("Cancelled before setting leverage.")

    await exchange.set_leverage(config['leverage'], full_symbol)
    await async_logger(f"✅ 杠杆已设置为 {config['leverage']}x。")

    filled_order = await _execute_maker_order_with_retry_async(
        exchange, full_symbol, plan['side'], {}, config['open_order_fill_timeout_seconds'],
        config['open_maker_retries'], async_logger, stop_event, value_to_trade=plan['value']
    )

    if stop_event.is_set(): raise InterruptedError("Cancelled after order fill.")

    final_pos = None
    for _ in range(5):
        positions = await fetch_positions_with_pnl_async(exchange, config.get('leverage', 1))
        final_pos = next((p for p in positions if p.symbol == base_coin and p.full_symbol == full_symbol), None)
        if final_pos: break
        await asyncio.sleep(2)

    if not final_pos: raise Exception("下单成功后，无法获取最终仓位信息。")

    await set_tp_sl_for_position_async(exchange, final_pos, config, async_logger)
    await async_logger(f"✅ {base_coin} 订单流程完全成功！", "success")
    return True