# backend/app/logic/exchange_logic_async.py
import asyncio
import datetime
import ccxt.async_support as ccxt
from typing import List, Optional, Dict

from ..config import i18n
from ..config.config import load_settings
from ..models.schemas import Position


class RetriableOrderError(Exception): pass


class InterruptedError(Exception): pass


# --- 初始化 ---
async def initialize_exchange_async(api_key: str, api_secret: str, use_testnet: bool) -> ccxt.binanceusdm:
    if not api_key or not api_secret:
        raise ConnectionError("API Key/Secret cannot be empty.")
    exchange = ccxt.binanceusdm({
        'apiKey': api_key, 'secret': api_secret,
        'options': {'adjustForTimeDifference': True, "warnOnFetchOpenOrdersWithoutSymbol": False},
    })
    exchange.enableRateLimit = True
    if use_testnet:
        exchange.set_sandbox_mode(True)
    await exchange.load_markets()
    return exchange


def resolve_full_symbol(exchange: ccxt.binanceusdm, base_coin: str) -> Optional[str]:
    """从基础币种解析出交易所支持的完整交易对符号"""
    base_upper = base_coin.upper()
    preferences = ['USDT', 'USDC']  # 优先使用USDT
    for quote in preferences:
        simple_symbol = f"{base_upper}/{quote}"
        if simple_symbol in exchange.markets:
            return exchange.markets[simple_symbol]['symbol']
        suffixed_symbol = f"{simple_symbol}:{quote}"
        if suffixed_symbol in exchange.markets:
            return exchange.markets[suffixed_symbol]['symbol']
    return None


# --- 数据获取 ---
async def fetch_positions_with_pnl_async(exchange: ccxt.binanceusdm) -> List[Position]:
    try:
        config = load_settings()  # <-- 加载配置以获取杠杆
        leverage = config.get('leverage', 1)  # 默认为1倍杠杆

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

                # --- 核心修复：PNL 百分比计算 ---
                initial_margin = float(info.get('initialMargin', 0.0))
                pnl = (current_price - break_even_price) * signed_contracts if break_even_price > 0 else float(
                    info.get('unRealizedProfit', 0.0))

                margin_for_calc = initial_margin
                # 如果初始保证金为0，使用估算值
                if margin_for_calc == 0 and leverage > 0:
                    margin_for_calc = notional / leverage

                pnl_percentage = (pnl / margin_for_calc) * 100 if margin_for_calc > 0 else 0.0
                # --- 修复结束 ---

                base_coin_symbol = full_symbol.split('/')[0].split(':')[0]

                pos_obj = Position(
                    symbol=base_coin_symbol,
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


async def close_position_async(exchange: ccxt.binanceusdm, symbol: str, ratio: float, async_logger):
    """异步平仓指定币种"""
    await async_logger(f"开始为 {symbol} 执行平仓，比例 {ratio * 100:.1f}%...")

    # 1. 获取所有持仓，找到目标
    all_positions = await fetch_positions_with_pnl_async(exchange)
    target_position = next((p for p in all_positions if p.symbol.upper() == symbol.upper()), None)

    if not target_position:
        await async_logger(f"未找到 {symbol} 的持仓，跳过。", "warning")
        return False

    # 2. 计算平仓参数
    full_symbol = resolve_full_symbol(exchange, target_position.symbol)
    if not full_symbol:
        await async_logger(f"无法为 {target_position.symbol} 找到可交易的交易对。", "error")
        return False

    close_side = 'sell' if target_position.side == 'long' else 'buy'
    amount_to_close = float(exchange.amount_to_precision(full_symbol, target_position.contracts * ratio))

    await async_logger(f"计划平仓 {amount_to_close} {target_position.symbol} on {full_symbol} at {close_side} side.")

    # 3. 创建平仓订单 (市价单简化处理)
    params = {'reduceOnly': True}
    try:
        order = await exchange.create_order(full_symbol, 'market', close_side, amount_to_close, params=params)
        await async_logger(f"✅ {symbol} 平仓订单已提交: ID {order['id']}", "success")
        return True
    except Exception as e:
        await async_logger(f"❌ {symbol} 平仓失败: {e}", "error")
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


# --- 新增：完整的真实下单函数 ---
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

            # 获取盘口价格
            order_book = await exchange.fetch_order_book(symbol, limit=5)
            price = float(order_book['bids'][0][0]) if side == i18n.ORDER_SIDE_BUY else float(order_book['asks'][0][0])

            # 计算数量
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
            await async_logger(f"✅ '{order_type_log}'限价单已提交！ID: {order_id}, 价格: {price}, 数量: {amount}")

            # 等待订单成交
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

            # 超时处理
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
    """完整的、包含真实下单和SL/TP设置的异步任务"""
    base_coin = plan['coin']
    await async_logger(f"--- 开始为 {base_coin} 处理完整订单流程 ---")

    full_symbol = resolve_full_symbol(exchange, base_coin)
    if not full_symbol:
        raise Exception(f"在期货市场中找不到 {base_coin} 的任何可用交易对。")

    # 1. 设置杠杆
    await exchange.set_leverage(config['leverage'], full_symbol)
    await async_logger(f"✅ 杠杆已设置为 {config['leverage']}x。")

    # 2. 执行下单
    filled_order = await _execute_maker_order_with_retry_async(
        exchange, full_symbol, plan['side'], {'postOnly': True},
        config['open_order_fill_timeout_seconds'], config['open_maker_retries'],
        async_logger, stop_event, value_to_trade=plan['value']
    )
    if not filled_order:
        raise Exception("开仓订单在所有重试后最终失败。")

    # 3. 获取最终仓位信息
    await async_logger("正在获取最终仓位信息...")
    final_pos = None
    for _ in range(5):  # 重试5次获取仓位
        if stop_event.is_set(): raise InterruptedError("Operation cancelled.")
        positions = await fetch_positions_with_pnl_async(exchange)
        final_pos = next((p for p in positions if p.symbol == base_coin), None)
        if final_pos: break
        await asyncio.sleep(2)

    if not final_pos:
        raise Exception("下单成功后，仍无法获取最终仓位信息。")

    # 4. 设置 SL/TP
    from ..logic.sl_tp_logic_async import set_tp_sl_for_position_async
    await set_tp_sl_for_position_async(exchange, final_pos, config, async_logger)

    await async_logger(f"✅ {base_coin} 订单流程完全成功！", "success")
    return True