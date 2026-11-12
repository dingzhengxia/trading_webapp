# backend/app/logic/exchange_logic_async.py
import asyncio
from typing import Any, List, Optional

import ccxt.async_support as ccxt
from loguru import logger

from .exceptions import RetriableOrderError, TaskInterruptedError
from .order_id import make_client_order_id, recover_order_by_client_id_async
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


def _min_notional(exchange: ccxt.binanceusdm, symbol: str) -> float:
    """最小名义价值（R-P0-4）：market.limits.cost.min，缺省 5.0 USDT。"""
    market = None
    try:
        market = exchange.market(symbol)
    except Exception:
        markets = getattr(exchange, 'markets', None) or {}
        market = markets.get(symbol)
    if not isinstance(market, dict):
        return 5.0
    cost_limits = (market.get('limits') or {}).get('cost') or {}
    return _to_float(cost_limits.get('min'), 5.0) or 5.0


async def _loguru_async_logger(message: str, level: str = 'normal') -> None:
    """把 async_logger 风格的日志桥接到 loguru（initialize 阶段没有任务级 logger）。"""
    mapped = {'normal': 'INFO', 'info': 'INFO', 'success': 'SUCCESS',
              'warning': 'WARNING', 'error': 'ERROR'}.get(str(level or 'info').lower(), 'INFO')
    logger.log(mapped, message)


async def detect_position_mode_async(exchange: ccxt.binanceusdm, async_logger) -> bool:
    """探测账户是否为双向持仓（Hedge Mode，R-P0-3）。

    结果缓存到 ``exchange._twa_hedge_mode``（经代理 __setattr__ 落到 underlying，
    实例生命周期内只探测一次）；探测失败记 warning 并按单向模式继续（不静默吞）。
    """
    try:
        mode = await exchange.fetch_position_mode()
        hedged = bool((mode or {}).get('hedged', False))
    except Exception as e:  # noqa: BLE001 - 探测失败不阻塞启动，按单向继续
        exchange._twa_hedge_mode = False
        await async_logger(
            f"⚠️ 持仓模式探测失败（按单向模式继续）: {type(e).__name__}: {e}", "warning")
        return False
    exchange._twa_hedge_mode = hedged
    await async_logger(
        f"ℹ️ 持仓模式探测完成: {'双向持仓 (Hedge Mode)' if hedged else '单向持仓'}。", "info")
    return hedged


def position_side_for(exchange: ccxt.binanceusdm, order_side: str) -> Optional[str]:
    """hedge 模式下 order_side→LONG/SHORT；单向返回 None（不携带 positionSide）。

    单向模式传 'BOTH' 会有 -4061 风险，宁缺勿错：返回 None 时调用方不合并该字段。
    """
    if not getattr(exchange, '_twa_hedge_mode', False):
        return None
    side = str(order_side or '').lower()
    if side == constants.ORDER_SIDE_BUY:
        return 'LONG'
    if side == constants.ORDER_SIDE_SELL:
        return 'SHORT'
    return None


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
    # R-P0-3：持仓模式探测一次并缓存到 exchange._twa_hedge_mode；失败按单向继续
    await detect_position_mode_async(exchange, _loguru_async_logger)
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

        # breakEvenPrice 在部分场景返回 "0"，不能仅用 None 判断，否则入场价恒为 0 导致 SL/TP 被跳过
        entry_price = _to_float(info.get('breakEvenPrice'))
        if entry_price is None or entry_price <= 0:
            entry_price = _to_float(raw_pos.get('entryPrice'), 0.0) or 0.0
        if entry_price <= 0:
            entry_price = _to_float(info.get('entryPrice'), 0.0) or 0.0

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
            raise TaskInterruptedError()

        all_positions = await exchange.fetch_positions([full_symbol_to_close])
        target_pos = next(
            (p for p in (all_positions or [])
             if str((p or {}).get('symbol') or '') == full_symbol_to_close
             and abs(_to_float(p.get('contracts'), 0.0) or 0.0) != 0),
            None,
        )
        if not target_pos:
            # 返回 False（而非 True）：调用方会广播 position_closed 并让前端乐观删除仓位，
            # 未实际平仓时不能报告成功；是否存在仓位以上一次持仓查询为准。
            await async_logger(f"平仓 {full_symbol_to_close} 时未找到持仓，可能已被手动关闭。", "warning")
            return False

        info = target_pos.get('info') or {}
        pos_amt = _to_float(info.get('positionAmt'))
        if pos_amt is None:
            contracts = abs(_to_float(target_pos.get('contracts'), 0.0) or 0.0)
            pos_amt = contracts if str(target_pos.get('side') or '').lower() == constants.SIDE_LONG else -contracts
        if pos_amt == 0:
            await async_logger(f"平仓 {full_symbol_to_close} 时持仓数量为 0，跳过。", "warning")
            return False

        config = load_settings()
        close_side = constants.ORDER_SIDE_SELL if pos_amt > 0 else constants.ORDER_SIDE_BUY
        raw_close_amount = abs(pos_amt) * ratio
        amount_to_close = _amount_to_precision(exchange, full_symbol_to_close, raw_close_amount)
        if amount_to_close <= 0:
            await async_logger(
                f"❌ 计算出的平仓数量为 0（目标 {raw_close_amount}），无法平仓 {full_symbol_to_close}；"
                f"请检查比例/最小下单量。", "error")
            return False

        close_timeout = int(config.get('close_order_fill_timeout_seconds', 12) or 12)
        close_retries = int(config.get('close_maker_retries', 3) or 3)
        # R-P0-3：hedge 模式下平仓单 positionSide 跟随持仓方向（LONG 仓平仓单=LONG）
        close_position_side = position_side_for(
            exchange, constants.ORDER_SIDE_BUY if pos_amt > 0 else constants.ORDER_SIDE_SELL)
        # R-P1-5：让价兜底 tick 数（0=关闭，行为与现状一致）
        close_chase_ticks = int(config.get('close_price_chase_ticks', 1) or 0)
        order_result = await _execute_maker_order_with_retry_async(
            exchange, full_symbol_to_close, close_side, {'reduceOnly': True},
            close_timeout, close_retries, async_logger, stop_event,
            contracts_to_trade=amount_to_close,
            position_side=close_position_side,
            price_chase_ticks=close_chase_ticks
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
                    contracts_to_trade=retry_amount,
                    position_side=close_position_side,
                    price_chase_ticks=close_chase_ticks
                )
                if not order_result:
                    await async_logger(f"❌ {full_symbol_to_close} 补平订单未能成交。", "error")
                    return False
                if stop_event.is_set():
                    raise TaskInterruptedError()

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
    except TaskInterruptedError:
        await async_logger(f"平仓操作 {full_symbol_to_close} 被中断。", "warning")
        return False
    except Exception as e:
        await async_logger(f"❌ {full_symbol_to_close} 平仓失败: {e}", "error")
        return False


async def _await_order_fill_async(exchange: ccxt.binanceusdm, symbol: str, order_id: str,
                                  known_filled: float, timeout: float, async_logger,
                                  stop_event: asyncio.Event) -> tuple[bool, float]:
    """轮询订单直到 closed 或超时；返回 (timed_out, 累计成交量)。

    供主下单路径与"网络异常后接管原单"路径共用，避免两份等待/轮询逻辑漂移。
    """
    order_filled = _to_float(known_filled, 0.0) or 0.0
    timed_out = True
    loop = asyncio.get_running_loop()
    start_time = loop.time()
    while loop.time() - start_time < timeout:
        if stop_event.is_set():
            raise TaskInterruptedError()
        fetched_order = await exchange.fetch_order(order_id, symbol)
        order_filled = max(order_filled, _to_float((fetched_order or {}).get('filled'), 0.0) or 0.0)
        if (fetched_order or {}).get('status') == 'closed':
            timed_out = False
            break
        await asyncio.sleep(2)
    return timed_out, order_filled


async def _cancel_and_confirm_filled_async(exchange: ccxt.binanceusdm, symbol: str, order_id: str,
                                           known_filled: float, async_logger) -> Optional[float]:
    """撤单并读取最终成交量；撤单/确认失败时返回 None（调用方必须中止，避免重复下单）。"""
    try:
        await exchange.cancel_order(order_id, symbol)
    except Exception as cancel_error:
        await async_logger(
            f"❌ {symbol} 订单 {order_id} 撤单失败（{cancel_error}），"
            f"已中止本次执行以避免重复下单，请人工核对挂单。", "error")
        return None
    try:
        fetched_order = await exchange.fetch_order(order_id, symbol)
        return max(_to_float(known_filled, 0.0) or 0.0,
                   _to_float((fetched_order or {}).get('filled'), 0.0) or 0.0)
    except Exception as fetch_error:
        await async_logger(
            f"❌ {symbol} 撤单后无法确认订单 {order_id} 的成交状态（{fetch_error}），"
            f"已中止本次执行，请人工核对仓位。", "error")
        return None


def _client_order_prefix(params: dict) -> str:
    """按单据用途确定 clientOrderId 前缀：reduceOnly 平仓单用 C，其余（开仓）用 O。"""
    return 'C' if (params or {}).get('reduceOnly') else 'O'


def _tick_size(exchange: ccxt.binanceusdm, symbol: str) -> float:
    """读取价格最小变动单位（market.precision.price）；拿不到返回 0（禁用让价）。"""
    market = None
    try:
        market = exchange.market(symbol)
    except Exception:
        markets = getattr(exchange, 'markets', None) or {}
        market = markets.get(symbol)
    precision = (market or {}).get('precision') or {}
    tick = _to_float(precision.get('price'))
    return tick if tick and tick > 0 else 0.0


async def _wait_fill_or_chase_async(exchange: ccxt.binanceusdm, symbol: str, side: str,
                                    base_params: dict, position_side: Optional[str],
                                    price: float, amount: float, timeout: float,
                                    chase_ticks: int, coid_prefix: str, async_logger,
                                    stop_event: asyncio.Event) -> dict:
    """reduceOnly 平仓的等待 + 让价 chase 循环（R-P1-5 平仓可成交性兜底）。

    连续 2 轮（每轮 2 秒轮询）0 新成交 → 撤单并按 tick 向可成交方向让价重挂
    （仍为 limit；仅 chase 重挂单不带 postOnly）。整个等待共享同一个超时预算。

    返回 {'complete': bool,        # True=订单完全成交
          'prior_filled': float,   # 已成交（含被撤/已完成的批次）累计量
          'last_order_filled': float,  # 最后一张挂单的成交量（由调用方撤单复核/累计）
          'order_id': Optional[str]}   # 最后一张挂单 id（None=已不可控）
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + float(timeout)
    tick = _tick_size(exchange, symbol)
    if tick <= 0 and chase_ticks > 0:
        await async_logger(f"⚠️ {symbol} 无价格精度信息，平仓让价 chase 关闭。", "warning")
        chase_ticks = 0
    total_filled = 0.0
    order_id: Optional[str] = None
    current_price = float(price)
    is_chase = False

    async def _cancel_quiet() -> None:
        if order_id:
            try:
                await exchange.cancel_order(order_id, symbol)
            except Exception:
                pass

    while True:
        if stop_event.is_set():
            await _cancel_quiet()
            raise TaskInterruptedError()
        remaining = _amount_to_precision(exchange, symbol, amount - total_filled)
        if remaining <= 0:
            return {'complete': True, 'prior_filled': total_filled,
                    'last_order_filled': 0.0, 'order_id': order_id}
        attempt_params = dict(base_params or {})
        attempt_params['newClientOrderId'] = make_client_order_id(coid_prefix, symbol)
        if not is_chase:
            attempt_params['postOnly'] = True  # 首挂保持 post-only 语义
        if position_side:
            attempt_params['positionSide'] = position_side
        order = await exchange.create_order(
            symbol, constants.ORDER_TYPE_LIMIT, side, remaining, current_price, attempt_params)
        order_id = str((order or {}).get('id'))
        known_filled = _to_float((order or {}).get('filled'), 0.0) or 0.0
        zero_rounds = 0
        while True:
            if stop_event.is_set():
                await _cancel_quiet()
                raise TaskInterruptedError()
            fetched_order = await exchange.fetch_order(order_id, symbol)
            filled = max(known_filled, _to_float((fetched_order or {}).get('filled'), 0.0) or 0.0)
            if (fetched_order or {}).get('status') == 'closed':
                total_filled += filled
                return {'complete': True, 'prior_filled': total_filled,
                        'last_order_filled': filled, 'order_id': order_id}
            if filled > known_filled + 1e-12:
                known_filled = filled
                zero_rounds = 0
            else:
                zero_rounds += 1
            if loop.time() >= deadline:
                # 整体超时：最后一张挂单留给调用方撤单复核（避免双算）
                return {'complete': False, 'prior_filled': total_filled,
                        'last_order_filled': known_filled, 'order_id': order_id}
            if zero_rounds >= 2 and chase_ticks > 0:
                # 撤单 → 按 tick 让价重挂（chase 单仍为 limit，不带 postOnly）
                try:
                    await exchange.cancel_order(order_id, symbol)
                except Exception as cancel_error:
                    await async_logger(
                        f"❌ {symbol} chase 撤单失败（{cancel_error}），已中止避免重复下单，"
                        f"请人工核对挂单。", "error")
                    return {'complete': False, 'prior_filled': total_filled,
                            'last_order_filled': 0.0, 'order_id': None}
                try:
                    fetched_order = await exchange.fetch_order(order_id, symbol)
                    known_filled = max(
                        known_filled, _to_float((fetched_order or {}).get('filled'), 0.0) or 0.0)
                except Exception:
                    pass
                total_filled += known_filled
                current_price = (current_price - chase_ticks * tick if side == constants.ORDER_SIDE_SELL
                                 else current_price + chase_ticks * tick)
                await async_logger(
                    f"⏳ {symbol} 平仓单连续 2 轮 0 成交，按 tick 让价 {chase_ticks} 重挂"
                    f" @ {current_price}（已成交 {total_filled}）。", "warning")
                is_chase = True
                break  # 回到外层按剩余量重挂
            await asyncio.sleep(2)


async def _execute_maker_order_with_retry_async(exchange: ccxt.binanceusdm, symbol: str, side: str, params: dict,
                                                timeout: int, retries: int, async_logger, stop_event: asyncio.Event,
                                                value_to_trade: float = None, contracts_to_trade: float = None,
                                                position_side: Optional[str] = None,
                                                price_chase_ticks: int = 0) -> bool:
    """限价 post-only 单执行器（开仓/平仓均走这里，禁止市价单）。

    P0-3：记录累计成交量，超时撤单后重试只下"目标数量 - 已成交量"的剩余量，
    剩余量低于最小下单量时停止，确保不会产生超额敞口。

    比率修复：按价值（value_to_trade）开仓时，数量不再按第一次的盘口价一次性
    固定——那会导致重试时若价格已变动，实际成交名义价值偏离设定值（价格涨了
    开多、价格跌了开空）。现在每轮尝试都按「剩余价值 / 当前盘口价」重算数量，
    并用各轮的限价精确累计已成交名义价值（post-only 单作为 maker 恰好按限价
    成交），保证最终名义价值始终贴合设定值。

    R-P0-1 下单幂等：每轮尝试生成确定性 newClientOrderId；create_order 抛
    网络类异常（RequestTimeout/NetworkError/ExchangeNotAvailable）时先按
    clientOrderId 反查——查到原单则接管继续等待成交（不重下），查不到才允许
    下一轮重下（新 coid）。
    """
    if contracts_to_trade is None and not value_to_trade:
        raise ValueError("下单数量或下单价值必须提供其一。")

    params = dict(params or {})
    side = str(side).lower()
    target_amount: Optional[float] = float(contracts_to_trade) if contracts_to_trade else None
    target_value: Optional[float] = float(value_to_trade) if value_to_trade else None
    total_filled = 0.0
    filled_notional = 0.0
    max_attempts = max(int(retries), 0) + 1
    order_fill_timeout = float(timeout)
    coid_prefix = _client_order_prefix(params)

    for attempt in range(max_attempts):
        if stop_event.is_set():
            raise TaskInterruptedError()
        order_id = None
        price: Optional[float] = None
        coid = make_client_order_id(coid_prefix, symbol)
        try:
            order_book = await exchange.fetch_order_book(symbol, limit=5)
            bids = order_book.get('bids') or []
            asks = order_book.get('asks') or []
            if not bids or not asks:
                raise RetriableOrderError(f"{symbol} 盘口数据为空，无法确定限价。")
            price = float(bids[0][0]) if side == constants.ORDER_SIDE_BUY else float(asks[0][0])
            if price <= 0:
                raise RetriableOrderError(f"{symbol} 盘口价格无效: {price}")

            if target_amount is not None:
                # 数量模式（平仓）：目标数量固定，只补未成交的剩余量
                remaining = _amount_to_precision(exchange, symbol, target_amount - total_filled)
            else:
                # 价值模式（开仓）：按剩余名义价值与当前价重算数量
                remaining_value = (target_value or 0.0) - filled_notional
                if remaining_value <= 1e-9:
                    await async_logger(
                        f"✅ {symbol} 已累计成交名义价值 {filled_notional:.2f}"
                        f"/{target_value:.2f} USD，无需继续下单。", "success")
                    return True
                remaining = _amount_to_precision(exchange, symbol, remaining_value / price)
            if remaining <= 0:
                if target_amount is not None or filled_notional > 1e-12:
                    await async_logger(
                        f"✅ {symbol} 已按目标全部成交（已成交名义价值 "
                        f"{filled_notional:.2f}/{target_value if target_value is not None else '-'} USD），无需继续下单。",
                        "success")
                    return True
                raise ValueError(f"根据价值 {target_value} 计算出的下单数量为 0。")

            min_amount = _min_order_amount(exchange, symbol)
            if min_amount and remaining < min_amount:
                if total_filled > 1e-12:
                    progress = (f"{filled_notional:.2f}/{target_value:.2f} USD"
                                if target_value is not None
                                else f"{total_filled}/{target_amount}")
                    await async_logger(
                        f"⚠️ {symbol} 剩余数量 {remaining} 低于最小下单量 {min_amount}，停止重试"
                        f"（已成交 {progress}，避免超额敞口）。", "warning")
                    return True
                raise ValueError(f"计算数量 {remaining} 小于最小下单量 {min_amount}。")

            # R-P0-4 最小名义价值校验：只对开仓（非 reduceOnly）单生效。
            # Binance 对 reduceOnly 平仓单豁免 minNotional，残留小仓位也必须能被清干净。
            min_notional = _min_notional(exchange, symbol)
            if not (params or {}).get('reduceOnly') and min_notional and remaining * price < min_notional:
                if total_filled > 1e-12:
                    await async_logger(
                        f"⚠️ {symbol} 剩余名义价值 {remaining * price:.2f} USD 低于最小名义价值 "
                        f"{min_notional}（已成交 {filled_notional:.2f} USD），停止重试。", "warning")
                    return True
                await async_logger(
                    f"⏭️ {symbol} 目标名义价值 {remaining * price:.2f} USD 低于最小名义价值 "
                    f"{min_notional}，跳过该币种（-4164 预防），任务继续。", "normal")
                return False

            if stop_event.is_set():
                raise TaskInterruptedError()

            # R-P1-5：reduceOnly 平仓路径启用让价 chase（连续 2 轮 0 成交 → 让价重挂）
            is_reduce_only = bool((params or {}).get('reduceOnly'))
            chase_ticks = max(0, int(price_chase_ticks or 0)) if is_reduce_only else 0

            timed_out = True
            order_filled = 0.0
            if chase_ticks > 0:
                chase = await _wait_fill_or_chase_async(
                    exchange, symbol, side, params, position_side, price, remaining,
                    order_fill_timeout, chase_ticks, coid_prefix, async_logger, stop_event)
                order_id = chase.get('order_id')
                timed_out = not chase['complete']
                order_filled = float(chase.get('last_order_filled') or 0.0)
                # chase 循环中已撤/已成交批次先入账；最后一张由下方统一撤单复核/累计
                total_filled += float(chase.get('prior_filled') or 0.0)
                filled_notional += float(chase.get('prior_filled') or 0.0) * price
                if timed_out and order_id is None:
                    # chase 撤单失败：挂单可能仍在簿，禁止继续重下
                    await async_logger(
                        f"❌ {symbol} chase 撤单失败后无法确认订单状态，已中止本次执行，请人工核对。", "error")
                    return False
            else:
                # 仅允许限价 post-only 单，禁止市价开仓；每轮带确定性 coid（幂等）；
                # hedge 模式（R-P0-3）由调用方算好 positionSide 注入，单向模式不携带
                attempt_params = {**params, 'postOnly': True, 'newClientOrderId': coid}
                if position_side:
                    attempt_params['positionSide'] = position_side
                order = await exchange.create_order(symbol, constants.ORDER_TYPE_LIMIT, side, remaining, price,
                                                    attempt_params)
                order_id = (order or {}).get('id')
                order_filled = _to_float((order or {}).get('filled'), 0.0) or 0.0
                await async_logger(
                    f"✅ {symbol} 限价单已提交 (ID: {order_id}，coid: {coid})，价格: {price}，数量: {remaining}，等待成交...")

                timed_out, order_filled = await _await_order_fill_async(
                    exchange, symbol, order_id, order_filled, order_fill_timeout, async_logger, stop_event)

            if timed_out:
                # P0：撤单失败意味着订单可能仍在簿上，若继续重下会造成双倍敞口 → 立即中止
                confirmed_filled = await _cancel_and_confirm_filled_async(
                    exchange, symbol, order_id, order_filled, async_logger)
                if confirmed_filled is None:
                    return False
                order_filled = confirmed_filled

            total_filled += order_filled
            filled_notional += order_filled * price

            if not timed_out:
                if target_value is not None:
                    await async_logger(
                        f"✅ {symbol} 订单 {order_id} 已成交！"
                        f"名义价值 {filled_notional:.2f}/{target_value:.2f} USD。", "success")
                else:
                    await async_logger(f"✅ {symbol} 订单 {order_id} 已成交！", "success")
                return True

            raise RetriableOrderError(
                f"订单 {order_id} 在 {order_fill_timeout} 秒内超时未成交（本单成交 {order_filled}）。")

        except TaskInterruptedError:
            if order_id:
                try:
                    await exchange.cancel_order(order_id, symbol)
                except Exception:
                    pass
            raise

        except (ccxt.RequestTimeout, ccxt.NetworkError, ccxt.ExchangeNotAvailable) as e:
            # R-P0-1 幂等反查：create_order 网络异常（order_id 未知）时，订单可能已入簿。
            # 反查命中 → 接管原单等待成交；未命中 → 落到下方常规重试（新 coid 重下）。
            if order_id is None:
                recovered = await recover_order_by_client_id_async(exchange, symbol, coid)
                if isinstance(recovered, dict) and recovered.get('id'):
                    order_id = str(recovered.get('id'))
                    await async_logger(
                        f"🔁 {symbol} 网络异常（{type(e).__name__}）后按 clientOrderId 反查到订单 "
                        f"{order_id}，接管原单继续等待成交（不重下）。", "warning")
                    timed_out, recovered_filled = await _await_order_fill_async(
                        exchange, symbol, order_id, 0.0, order_fill_timeout, async_logger, stop_event)
                    if timed_out:
                        confirmed_filled = await _cancel_and_confirm_filled_async(
                            exchange, symbol, order_id, recovered_filled, async_logger)
                        if confirmed_filled is None:
                            return False
                        recovered_filled = confirmed_filled
                    total_filled += recovered_filled
                    filled_notional += recovered_filled * float(price if price else 0.0)
                    if not timed_out:
                        if target_value is not None:
                            await async_logger(
                                f"✅ {symbol} 订单 {order_id}（接管）已成交！"
                                f"名义价值 {filled_notional:.2f}/{target_value:.2f} USD。", "success")
                        else:
                            await async_logger(f"✅ {symbol} 订单 {order_id}（接管）已成交！", "success")
                        return True
                    await async_logger(
                        f"⚠️ {symbol} 接管订单 {order_id} 超时未成交（本单成交 {recovered_filled}），"
                        f"按剩余量继续重试。", "warning")
                    if attempt < max_attempts - 1:
                        if stop_event.is_set():
                            raise TaskInterruptedError()
                        await asyncio.sleep(3)
                        continue
                    await async_logger(f"❌ {symbol} 订单在 {max_attempts} 次尝试后仍然失败。", "error")
                    return False
            if attempt < max_attempts - 1:
                if stop_event.is_set():
                    raise TaskInterruptedError()
                await asyncio.sleep(3)
            else:
                await async_logger(f"❌ {symbol} 订单在 {max_attempts} 次尝试后仍然失败。", "error")
                return False

        except (ccxt.DDoSProtection, ccxt.OrderImmediatelyFillable,
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
                    raise TaskInterruptedError()
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
        raise TaskInterruptedError()

    desired_leverage = int(config.get('leverage', 1) or 1)
    actual_leverage = await _set_leverage_safe_async(exchange, full_symbol, desired_leverage, async_logger)

    side = str(plan.get('side') or '').lower()
    # R-P0-3：hedge 模式下开仓单 positionSide 跟随订单方向（buy→LONG / sell→SHORT）
    open_position_side = position_side_for(exchange, side)
    filled = await _execute_maker_order_with_retry_async(
        exchange, full_symbol, side, {},
        int(config.get('open_order_fill_timeout_seconds', 60) or 60),
        int(config.get('open_maker_retries', 5) or 5),
        async_logger, stop_event, value_to_trade=plan.get('value'),
        position_side=open_position_side
    )
    if not filled:
        return False
    if stop_event.is_set():
        return False

    # P0-2：只按 full_symbol + 方向精确匹配刚成交的仓位。
    # 不再按 base coin 猜测：新单尚未反映到持仓接口时，猜测会命中旧仓/反向仓并挂错 SL/TP。
    expected_side = constants.SIDE_LONG if side == constants.ORDER_SIDE_BUY else constants.SIDE_SHORT
    final_pos = None
    for _ in range(5):
        if stop_event.is_set():
            raise TaskInterruptedError()
        positions = await fetch_positions_with_pnl_async(exchange, actual_leverage)
        final_pos = next(
            (p for p in positions
             if p.full_symbol == full_symbol and str(p.side).lower() == expected_side),
            None,
        )
        if final_pos:
            break
        await asyncio.sleep(2)

    if not final_pos:
        raise Exception("下单成功后，无法获取最终仓位信息。")

    # 将 leverage 替换为实际成功的杠杆，保证金百分比计算依赖它
    effective_config = dict(config)
    effective_config['leverage'] = actual_leverage
    sltp_ok = await set_tp_sl_for_position_async(
        exchange, final_pos, effective_config, async_logger, stop_event)
    if not sltp_ok:
        await async_logger(
            f"❌ {base_coin} 已开仓但止盈止损设置失败（交易对: {full_symbol}），"
            f"当前仓位处于无保护状态，请立即人工处理。", "error")
        # R-P0-2 裸仓回收：处置权协调（late import 避免 logic→protection 循环依赖）
        if await _handle_unprotected_position_async(exchange, full_symbol, expected_side,
                                                    config, async_logger, stop_event):
            plan['_auto_closed'] = True
        else:
            plan['_danger'] = 'unprotected'
        return False

    await async_logger(
        f"✅ {base_coin} 订单流程完全成功！(交易对: {full_symbol}, 杠杆: {actual_leverage}x)", "success")
    return True


async def _handle_unprotected_position_async(exchange: ccxt.binanceusdm, full_symbol: str,
                                             side: str, config: dict, async_logger,
                                             stop_event: asyncio.Event) -> bool:
    """SL/TP 注入失败后的裸仓处置（R-P0-2）。返回是否触发了自动平仓。

    1. protection v2 已接管该仓位 → 跳过自动平仓（单一处置权归 protection，
       避免两边同时发单互相顶单），只记 error 强提示；
    2. 未接管且 unprotected_position_action=auto_close（默认）→ 立即全平
       （复用 close_position_async：reduceOnly 限价 post-only + 全平复核）；
    3. keep_alert → 不触碰仓位，任务标记危险态（调用方落 _danger 标记）。
    无论回收与否，任务一律计失败（D1：结果项带 auto_closed 供台账区分）。
    """
    try:
        from ..protection.service import protection_active_for
        protection_managed = protection_active_for(full_symbol, side)
    except Exception as e:  # noqa: BLE001 - 查询失败按未接管处理
        protection_managed = False
        await async_logger(f"⚠️ 查询仓位保护接管状态失败（按未接管处理）: {e}", "warning")

    if protection_managed:
        await async_logger(
            f"🛡️ {full_symbol}（{side}）已由仓位保护引擎接管，跳过自动平仓"
            f"（应急减仓/灾难止损由保护引擎执行，避免双重处置）。", "error")
        return False

    action = str(config.get('unprotected_position_action', 'auto_close') or 'auto_close').lower()
    if action not in ('auto_close', 'keep_alert'):
        action = 'auto_close'

    if action == 'keep_alert':
        await async_logger(
            f"🚨 {full_symbol}（{side}）SL/TP 失败且配置为 keep_alert：仓位保持无保护状态，"
            f"请立即人工处理！", "error")
        return False

    await async_logger(f"♻️ {full_symbol}（{side}）开始自动回收裸仓（reduceOnly 全平）...", "warning")
    try:
        closed = await close_position_async(exchange, full_symbol, 1.0, async_logger, stop_event)
    except TaskInterruptedError:
        raise
    except Exception as e:  # noqa: BLE001 - 回收失败要落到 error 日志
        closed = False
        await async_logger(f"❌ {full_symbol} 自动回收异常: {e}", "error")
    if closed:
        await async_logger(f"✅ {full_symbol} 裸仓已自动回收（SL/TP 注入失败兜底）。", "warning")
        return True
    await async_logger(
        f"❌ {full_symbol} 自动平仓也失败，仓位无保护，请立即人工处理！", "error")
    return False
