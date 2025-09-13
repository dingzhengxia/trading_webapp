import asyncio
import datetime
import ccxt.async_support as ccxt
from typing import List, Optional, Dict

from ..models.schemas import Position
from ..config.config import load_settings, STABLECOIN_PREFERENCE
from ..config import i18n


class RetriableOrderError(Exception): pass


class InterruptedError(Exception): pass


async def initialize_exchange_async(api_key: str, api_secret: str, use_testnet: bool) -> ccxt.binanceusdm:
    if not api_key or not api_secret:
        raise ConnectionError("API Key/Secret cannot be empty.")

    config = {
        'apiKey': api_key,
        'secret': api_secret,
        'options': {
            'adjustForTimeDifference': True,
            "warnOnFetchOpenOrdersWithoutSymbol": False
        },
    }

    exchange = ccxt.binanceusdm(config)
    exchange.enableRateLimit = True

    if use_testnet:
        exchange.set_sandbox_mode(True)

    await exchange.load_markets()
    return exchange


def resolve_full_symbol(exchange: ccxt.binanceusdm, base_coin: str) -> Optional[str]:
    base_upper = base_coin.upper()
    quote_preferences = STABLECOIN_PREFERENCE

    for quote in quote_preferences:
        simple_symbol = f"{base_upper}/{quote}"
        if simple_symbol in exchange.markets:
            return exchange.markets[simple_symbol]['symbol']

        suffixed_symbol = f"{simple_symbol}:{quote}"
        if suffixed_symbol in exchange.markets:
            return exchange.markets[suffixed_symbol]['symbol']

    return None


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

                margin_for_calc = initial_margin
                if margin_for_calc == 0 and leverage > 0:
                    margin_for_calc = notional / leverage

                pnl_percentage = (pnl / margin_for_calc) * 100 if margin_for_calc > 0 else 0.0

                base_coin_symbol = full_symbol.split('/')[0].split(':')[0]

                pos_obj = Position(
                    symbol=base_coin_symbol,
                    full_symbol=full_symbol,
                    side=raw_pos.get('side'),
                    contracts=abs(signed_contracts),
                    entry_price=float(raw_pos.get('entryPrice', 0.0)),
                    notional=notional,
                    mark_price=current_price,
                    pnl=pnl,
                    pnl_percentage=pnl_percentage,
                )
                final_positions.append(pos_obj)
            except (TypeError, ValueError, KeyError) as e:
                print(f"Error processing position {raw_pos.get('symbol', 'N/A')}: {e}")
                continue
        return final_positions
    except Exception as e:
        print(f"Error fetching positions or PNL: {e}")
        return []


# --- 核心修复：更健壮的价格获取和平仓逻辑 ---
async def close_position_async(exchange: ccxt.binanceusdm, full_symbol_to_close: str, ratio: float, async_logger):
    base_coin = full_symbol_to_close.split('/')[0]
    await async_logger(f"开始为 {full_symbol_to_close} 执行平仓，比例 {ratio * 100:.1f}%...")

    try:
        # 1. 获取持仓信息
        # fetch_positions 返回的是一个列表，即使我们只请求一个 symbol
        all_positions = await exchange.fetch_positions([full_symbol_to_close])
        target_position_raw = next((p for p in all_positions if p['symbol'] == full_symbol_to_close), None)

        if not target_position_raw or float(target_position_raw.get('contracts', 0)) == 0:
            await async_logger(f"最终确认失败：未找到 {full_symbol_to_close} 的有效持仓。", "info")
            return True

        # 2. 获取行情价格 (Ticker)
        ticker = await exchange.fetch_ticker(full_symbol_to_close)

        # 3. 安全地获取价格，优先使用标记价，否则使用最后成交价
        price_for_calc = ticker.get('mark') or ticker.get('last')
        if not price_for_calc:
            raise ValueError(f"无法获取 {full_symbol_to_close} 的标记价格或最后成交价。")
        mark_price = float(price_for_calc)

        # 4. 提取持仓数据并计算
        position_info = target_position_raw['info']
        position_amount_contracts = float(position_info['positionAmt'])
        side = 'long' if position_amount_contracts > 0 else 'short'

        # 使用我们安全获取的价格来计算名义价值
        notional_value = abs(position_amount_contracts * mark_price)

        value_to_close_usd = notional_value * ratio
        amount_to_close_contracts = float(
            exchange.amount_to_precision(full_symbol_to_close, value_to_close_usd / mark_price))

        # 健全性检查
        if amount_to_close_contracts > abs(position_amount_contracts):
            amount_to_close_contracts = abs(position_amount_contracts)

        if amount_to_close_contracts <= 0:
            await async_logger(f"计算出的平仓数量为 {amount_to_close_contracts}，小于等于0。跳过下单。", "warning")
            return False

        close_side = 'SELL' if side == 'long' else 'BUY'
        await async_logger(
            f"最终确认：计划市价平仓 {value_to_close_usd:,.2f} U (合约数量: {amount_to_close_contracts}) on {full_symbol_to_close} at {close_side} side.")

        # 5. 下单
        order = await exchange.private_post_order({
            'symbol': full_symbol_to_close,
            'side': close_side,
            'type': 'MARKET',
            'quantity': str(amount_to_close_contracts),
            'reduceOnly': 'true'
        })

        await async_logger(f"✅ {base_coin} ({full_symbol_to_close}) 平仓订单已成功提交: ID {order['orderId']}",
                           "success")
        return True

    except Exception as e:
        if 'ReduceOnly' in str(e):
            await async_logger(
                f"❌ {base_coin} ({full_symbol_to_close}) 平仓失败：交易所拒绝了'只减仓'订单。请确认账户/网络是否正确，以及该仓位是否真实存在。",
                "error")
        else:
            await async_logger(f"❌ {base_coin} ({full_symbol_to_close}) 平仓失败，发生意外错误: {e}", "error")
        return False


# --- 修复结束 ---

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
        exchange: ccxt.binanceusdm,
        symbol: str,
        side: str,
        params: dict,
        timeout: int,
        retries: int,
        async_logger,
        stop_event: asyncio.Event,
        value_to_trade: float = None,
        contracts_to_trade: float = None
):
    order_id = None
    order_type_log = "开仓" if not params.get('reduceOnly') else "平仓"

    for attempt in range(retries + 1):
        if stop_event.is_set():
            raise InterruptedError(f"{order_type_log} operation cancelled by user.")

        try:
            if attempt > 0:
                await async_logger(f"正在进行第 {attempt} 次重试...")

            order_book = await exchange.fetch_order_book(symbol, limit=5)
            price = float(order_book['bids'][0][0]) if side == i18n.ORDER_SIDE_BUY else float(order_book['asks'][0][0])

            if contracts_to_trade is not None:
                amount = contracts_to_trade
            elif value_to_trade is not None:
                amount = float(exchange.amount_to_precision(symbol, float(value_to_trade) / price))
                market = exchange.market(symbol)
                min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)
                if min_amount is not None and amount < min_amount:
                    raise ValueError(f"计算数量 {amount} 小于最小下单量 {min_amount}。")
            else:
                raise ValueError("必须提供开仓价值或平仓数量。")

            await async_logger(f"正在提交'{order_type_log}'限价单 (尝试 {attempt + 1}/{retries + 1})...")
            order = await exchange.create_order(symbol, 'limit', side, amount, price, params)
            order_id = order['id']
            await async_logger(f"✅ '{order_type_log}'限价单已提交！ID: {order['id']}, 价格: {price}, 数量: {amount}")

            start_time = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start_time < timeout:
                if stop_event.is_set():
                    await exchange.cancel_order(order_id, symbol)
                    raise InterruptedError("Operation cancelled.")

                try:
                    order_status = await exchange.fetch_order(order_id, symbol)
                    if order_status['status'] == 'closed':
                        await async_logger(f"✅ 订单 {order_id} 已成交！", "success")
                        return order_status
                    if order_status['status'] == 'canceled':
                        raise RetriableOrderError(f"订单 {order_id} 被交易所取消。")
                except ccxt.OrderNotFound:
                    await async_logger(f"  > 订单 {order_id} 暂时未找到，可能是交易所延迟...")

                await asyncio.sleep(3)

            await async_logger(f"⚠️ 订单 {order_id} 超时未成交，正在取消...", "warning")
            await exchange.cancel_order(order_id, symbol)
            raise RetriableOrderError(f"订单 {order_id} 在 {timeout}s 内未成交。")

        except (ccxt.RequestTimeout, ccxt.DDoSProtection, ccxt.ExchangeNotAvailable, ccxt.OrderNotFillable,
                RetriableOrderError) as e:
            await async_logger(f"尝试失败: 可重试错误 ({type(e).__name__}): {e}", "warning")
            if attempt < retries:
                await asyncio.sleep(3)
                continue
            else:
                await async_logger(f"❌ 在 {retries} 次重试后，'{order_type_log}'订单仍然失败。", "error")
                return None
        except Exception as e:
            await async_logger(f"🚨 发生严重错误: {e}", "error")
            if order_id:
                try:
                    await exchange.cancel_order(order_id, symbol)
                except:
                    pass
            raise


async def process_order_with_sl_tp_async(exchange: ccxt.binanceusdm, plan: dict, config: dict, async_logger,
                                         stop_event: asyncio.Event):
    base_coin = plan['coin']
    await async_logger(f"--- 开始为 {base_coin} 处理完整订单流程 ---")

    full_symbol = resolve_full_symbol(exchange, base_coin)
    if not full_symbol:
        raise Exception(f"在期货市场中找不到 {base_coin} 的任何可用交易对。")

    await exchange.set_leverage(config['leverage'], full_symbol)
    await async_logger(f"✅ 杠杆已设置为 {config['leverage']}x。")

    filled_order = await _execute_maker_order_with_retry_async(
        exchange, full_symbol, plan['side'], {'postOnly': True},
        config['open_order_fill_timeout_seconds'], config['open_maker_retries'],
        async_logger, stop_event, value_to_trade=plan['value']
    )
    if not filled_order:
        raise Exception("开仓订单在所有重试后最终失败。")

    await async_logger("正在获取最终仓位信息...")
    final_pos = None
    for _ in range(5):
        if stop_event.is_set(): raise InterruptedError("Operation cancelled.")
        positions = await fetch_positions_with_pnl_async(exchange, config.get('leverage', 1))
        final_pos = next((p for p in positions if p.symbol == base_coin and p.full_symbol == full_symbol), None)
        if final_pos: break
        await asyncio.sleep(2)

    if not final_pos:
        raise Exception("下单成功后，仍无法获取最终仓位信息。")

    from ..logic.sl_tp_logic_async import set_tp_sl_for_position_async
    await set_tp_sl_for_position_async(exchange, final_pos, config, async_logger)

    await async_logger(f"✅ {base_coin} 订单流程完全成功！", "success")
    return True