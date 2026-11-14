# backend/app/core/trading_service.py
import asyncio
import inspect
import threading
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from fastapi import BackgroundTasks, HTTPException

from .exchange_manager import get_exchange_for_task
from .open_history import record_batch
from .websocket_manager import broadcast_progress_details, log_message, manager as ws_manager, update_status
from ..config.config import load_settings
from ..logic.exchange_logic_async import (
    TaskInterruptedError,
    _set_leverage_safe_async,
    close_position_async,
    fetch_positions_with_pnl_async,
    process_order_with_sl_tp_async,
)
from ..logic.manual_trade_logic import (
    build_manual_trade_tasks,
    normalize_action,
    validate_manual_items,
)
from ..logic.plan_calculator import calculate_trade_plan
from ..logic.sl_tp_logic_async import cleanup_orphan_sltp_orders_async, set_tp_sl_for_position_async
from ..models.schemas import ExecutionPlanRequest, ManualTradeRequest, SyncSltpRequest, TradePlanRequest


class TradingService:
    def __init__(self):
        self._is_running = False
        self._stop_event = asyncio.Event()
        self._task_progress: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._last_request_id: Optional[str] = None

        self.CONCURRENT_OPEN_TASKS = 5
        self.CONCURRENT_CLOSE_TASKS = 10

    def get_current_status(self) -> Dict[str, Any]:
        with self._lock:
            if self._is_running:
                return {"is_running": True, "progress": self._task_progress}
            return {"is_running": False}

    async def _execute_and_log_task(self, task_name: str, task_coro: Awaitable):
        start_time = time.time()
        await log_message(f"--- [LOG] 后台任务 '{task_name}' 已调度，准备执行 ---", "info")
        try:
            await task_coro
        except TaskInterruptedError:
            await log_message(f"--- [LOG] ⚠️ 任务 '{task_name}' 被用户停止 ---", "warning")
        except Exception as e:
            await log_message(f"--- [LOG] ❌ 任务 '{task_name}' 执行时发生顶层异常: {e} ---", "error")
        finally:
            with self._lock:
                self._is_running = False
                self._task_progress = {}
                self._last_request_id = None
            end_time = time.time()
            await log_message(f"--- [LOG] ✅ 任务 '{task_name}' 已结束，总耗时: {end_time - start_time:.2f} 秒 ---",
                              "success")
            await update_status(f"'{task_name}' 已结束", is_running=False)

    @staticmethod
    def _discard_coro(task_coro: Awaitable) -> None:
        """任务被拒绝时关闭未 await 的协程，避免 "coroutine was never awaited" 警告与资源泄漏。"""
        close = getattr(task_coro, "close", None)
        if callable(close):
            close()

    def _start_task(self, task_name: str, task_coro: Awaitable, background_tasks: BackgroundTasks,
                    request_id: Optional[str] = None):
        with self._lock:
            if self._is_running:
                self._discard_coro(task_coro)
                if request_id and request_id == self._last_request_id:
                    return {"message": "重复的任务请求已被忽略。"}
                raise HTTPException(status_code=400, detail="已有任务在运行中，请稍后再试。")

            self._is_running = True
            self._stop_event.clear()
            self._last_request_id = request_id
            self._task_progress = {"task_name": task_name}
            background_tasks.add_task(self._execute_and_log_task, task_name, task_coro)

        return {"message": f"任务 '{task_name}' 已成功提交到后台。"}

    async def _run_task_loop(self, items: List[Any], worker_func: Callable, concurrency: int, task_name: str):
        total_tasks = len(items)
        success_count, failure_count = 0, 0
        self._task_progress = {"success_count": 0, "failed_count": 0, "total": total_tasks, "task_name": task_name}
        await broadcast_progress_details(**self._task_progress)

        if not items:
            await log_message(f"任务 '{task_name}' 列表为空。", "info")
            await broadcast_progress_details(0, 0, 0, "任务列表为空", is_final=True)
            return

        semaphore = asyncio.Semaphore(concurrency)

        async def worker_wrapper(item):
            nonlocal success_count, failure_count
            if self._stop_event.is_set():
                return
            async with semaphore:
                if self._stop_event.is_set():
                    return
                is_success = False
                try:
                    is_success = await worker_func(item)
                except Exception as e:
                    await log_message(f"执行子任务时发生意外错误: {e}", "error")
                finally:
                    if is_success:
                        success_count += 1
                    else:
                        failure_count += 1
                    processed = success_count + failure_count
                    current_progress = self._task_progress.copy()
                    current_progress.update({"success_count": success_count, "failed_count": failure_count,
                                             "task_name": f"{task_name}: {processed}/{total_tasks}"})
                    await broadcast_progress_details(**current_progress)

        tasks = [asyncio.create_task(worker_wrapper(item)) for item in items]
        await asyncio.wait(tasks)

        if self._stop_event.is_set():
            raise TaskInterruptedError()

        status_text = "部分成功" if failure_count > 0 else "全部成功"
        final_progress = self._task_progress.copy()
        final_progress.update(
            {"is_final": True, "task_name": f"{task_name} {status_text}", "success_count": success_count,
             "failed_count": failure_count})
        await broadcast_progress_details(**final_progress)
        await log_message(f"{task_name}完成, 成功: {success_count}, 失败: {failure_count}",
                          "success" if failure_count == 0 else "warning")

    def start_trading(self, plan_request: TradePlanRequest, background_tasks: BackgroundTasks):
        return self._start_task("自动开仓", self._trading_loop_task(plan_request.model_dump()), background_tasks,
                                plan_request.request_id)

    async def stop_trading(self):
        if not self._is_running:
            return {"message": "No active task."}
        await log_message("收到停止信号，任务将在当前子项完成后停止。", "warning")
        self._stop_event.set()
        return {"message": "Stop event set. Task will terminate shortly."}

    # --- 信号自动开仓（MERGE_PLAN §5）---
    def schedule_task(self, task_name: str, task_coro: Awaitable,
                      request_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """不经 FastAPI BackgroundTasks 的任务提交入口（信号自动开仓用）。

        与 _start_task 一样受全局任务锁互斥：_is_running 时返回 None（调用方 skip）。
        """
        with self._lock:
            if self._is_running:
                self._discard_coro(task_coro)
                return None
            self._is_running = True
            self._stop_event.clear()
            self._last_request_id = request_id
            self._task_progress = {"task_name": task_name}
        try:
            asyncio.get_running_loop().create_task(self._execute_and_log_task(task_name, task_coro))
        except RuntimeError:
            # 无运行中的事件循环：回滚标志位，否则后续所有交易任务都会被永久拒绝
            with self._lock:
                self._is_running = False
                self._task_progress = {}
                self._last_request_id = None
            self._discard_coro(task_coro)
            raise
        return {"message": f"任务 '{task_name}' 已成功提交到后台。"}

    async def auto_open_from_signal(self, signal: Dict[str, Any], config: Dict[str, Any],
                                    on_opened: Optional[Callable[[], Any]] = None) -> bool:
        """信号驱动的自动开仓入口。

        复用现有 process_order_with_sl_tp_async（限价 post-only、USDC 优先、开仓后挂 SL/TP）；
        与用户任务互斥：_is_running 时记 warning 并 skip（不打断用户任务）。

        :param on_opened: 真正成交后回调（用于登记实盘出场/超时平仓），失败不影响开仓结果
        """
        if self._is_running:
            await log_message("已有交易任务在运行，跳过本次信号自动开仓。", "warning")
            return False

        direction = str(signal.get('direction') or '').lower()
        side = 'buy' if direction == 'long' else 'sell'
        plan = {
            'coin': str(signal.get('symbol') or '').upper(),
            'value': float(config.get('signal_auto_trade_value_usd', 100.0) or 100.0),
            'side': side,
            # 信号自身周期：ATR 出场必须按它取，否则 1h 信号会错用 4h 的 ATR（止损宽一倍）
            'timeframe': str(signal.get('timeframe') or ''),
            # 记录触发策略，开仓台账里能对上「哪个信号开的仓」
            'strategy': str(signal.get('strategy') or ''),
        }
        signal_desc = f"{plan['coin']} {direction} ({signal.get('strategy')} @ {signal.get('timeframe')})"

        submitted = self.schedule_task(
            "信号自动开仓", self._auto_open_task(plan, config, on_opened))
        if submitted is None:
            await log_message("已有交易任务在运行，跳过本次信号自动开仓。", "warning")
            return False
        await log_message(f"信号自动开仓任务已提交: {signal_desc}，"
                          f"金额 {plan['value']} USD。", "info")
        return True

    async def _auto_open_task(self, plan: Dict[str, Any], config: Dict[str, Any],
                              on_opened: Optional[Callable[[], Any]] = None):
        config = dict(config)
        config.setdefault('leverage', 1)
        if plan.get('timeframe'):
            # 供 sl_tp_logic 取 ATR 用（跟随信号周期，而不是全局 signal_live_exit_timeframe）
            config['_signal_timeframe'] = plan['timeframe']
        results: List[Dict[str, Any]] = []
        try:
            async with get_exchange_for_task() as exchange:
                opened = await process_order_with_sl_tp_async(
                    exchange, plan, config, log_message, self._stop_event)
            results.append({'coin': plan.get('coin'), 'side': plan.get('side'),
                            'target_value': plan.get('value'), 'success': bool(opened),
                            # R-P0-2：SL/TP 失败被自动回收 / 危险态标记（供台账区分"开仓成功"与"开仓后回收"）
                            'auto_closed': bool(plan.get('_auto_closed')),
                            'danger': plan.get('_danger'),
                            'strategy': plan.get('strategy'), 'timeframe': plan.get('timeframe')})
            if opened and on_opened is not None:
                try:
                    result = on_opened()
                    if inspect.isawaitable(result):
                        await result
                except Exception as e:  # noqa: BLE001 - 登记失败不应改变开仓结果
                    await log_message(f"⚠️ 开仓后登记出场失败（不影响持仓）: {e}", "warning")
            return opened
        except Exception as e:
            results.append({'coin': plan.get('coin'), 'side': plan.get('side'),
                            'target_value': plan.get('value'), 'success': False,
                            'error': str(e), 'strategy': plan.get('strategy'),
                            'timeframe': plan.get('timeframe')})
            raise
        finally:
            # 信号开仓也要留下记录（来源/策略/结果），与控制面板开仓同一份台账
            alloc_key = 'long' if str(plan.get('side')) == 'buy' else 'short'
            record_batch('signal', f"信号自动开仓 {plan.get('strategy') or ''}@{plan.get('timeframe') or ''}",
                         items=results,
                         allocations={alloc_key: {str(plan.get('coin')): plan.get('value')}})

    async def _trading_loop_task(self, config: Dict[str, Any]):
        # P1-1 / P1-5：整个任务只创建一个 exchange，worker 共享
        long_plan, short_plan = calculate_trade_plan(config)
        order_plan = [item for item in (
            [{'coin': c, 'value': v, 'side': 'buy'} for c, v in long_plan.items()] if config.get(
                'enable_long_trades') else []
        ) + ([{'coin': c, 'value': v, 'side': 'sell'} for c, v in short_plan.items()] if config.get(
            'enable_short_trades') else [])]

        # 开仓记录：先固化「当时选的币种/权重/总价值」快照，任务结束后逐笔落库
        snapshot = {
            'enable_long_trades': config.get('enable_long_trades'),
            'enable_short_trades': config.get('enable_short_trades'),
            'long_coin_list': config.get('long_coin_list'),
            'long_custom_weights': config.get('long_custom_weights'),
            'total_long_position_value': config.get('total_long_position_value'),
            'short_coin_list': config.get('short_coin_list'),
            'total_short_position_value': config.get('total_short_position_value'),
        }
        results: List[Dict[str, Any]] = []

        # 任务一开始就落一条「进行中」记录，长任务也能在面板上看到；跑完用同 ID 更新结果
        pending_items = [{'coin': item.get('coin'), 'side': item.get('side'),
                          'target_value': item.get('value'), 'success': None}
                         for item in order_plan]
        pending_batch = record_batch('plan', '自动开仓', items=pending_items,
                                     snapshot=snapshot,
                                     allocations={'long': long_plan, 'short': short_plan})
        pending_id = (pending_batch or {}).get('id')

        async with get_exchange_for_task() as exchange:
            async def worker(plan_item):
                try:
                    ok = await process_order_with_sl_tp_async(
                        exchange, plan_item, config, log_message, self._stop_event)
                except Exception as e:
                    results.append({'coin': plan_item.get('coin'), 'side': plan_item.get('side'),
                                    'target_value': plan_item.get('value'), 'success': False,
                                    'error': str(e)})
                    raise
                results.append({'coin': plan_item.get('coin'), 'side': plan_item.get('side'),
                                'target_value': plan_item.get('value'), 'success': bool(ok),
                                'auto_closed': bool(plan_item.get('_auto_closed')),
                                'danger': plan_item.get('_danger')})
                return ok

            try:
                await self._run_task_loop(order_plan, worker, self.CONCURRENT_OPEN_TASKS, "自动开仓")
            finally:
                final_items = results or [
                    {**item, 'success': False, 'error': '任务中断，无执行结果'} for item in pending_items]
                record_batch('plan', '自动开仓', items=final_items, snapshot=snapshot,
                             allocations={'long': long_plan, 'short': short_plan},
                             record_id=pending_id)

    def dispatch_tasks(self, task_name: str, tasks_data: List[Tuple[str, float]], task_type: str,
                       config: Dict[str, Any], background_tasks: BackgroundTasks, request_id: Optional[str] = None):
        task_coro = self._generic_task_loop(tasks_data, task_type, config, task_name)
        return self._start_task(task_name, task_coro, background_tasks, request_id)

    async def _generic_task_loop(self, tasks_data: List, task_type: str, config: Dict[str, Any], task_name: str):
        async with get_exchange_for_task() as exchange:
            async def worker(task_item):
                if task_type == 'CLOSE_ORDER':
                    full_symbol, ratio = task_item
                    is_success = await close_position_async(
                        exchange, full_symbol, ratio, log_message, self._stop_event)
                    if is_success:
                        await ws_manager.broadcast(
                            {"type": "position_closed", "payload": {"full_symbol": full_symbol, "ratio": ratio}})
                    return is_success
                return False

            await self._run_task_loop(tasks_data, worker, self.CONCURRENT_CLOSE_TASKS, task_name)

    def sync_all_sltp(self, settings: SyncSltpRequest, background_tasks: BackgroundTasks):
        return self._start_task("同步所有止盈止损", self._sync_sltp_task(settings.model_dump()), background_tasks,
                                settings.request_id)

    async def _sync_sltp_task(self, settings: dict):
        task_name = "同步SL/TP"
        # 杠杆：优先用请求携带值；payload 缺失/非法时回退服务端配置。
        # 防御点：SyncSltpRequest.leverage 默认 1，若直接 fallback 到 1 会把持仓悄悄降到 1x。
        leverage = int(settings.get('leverage') or 0)
        if leverage <= 0:
            leverage = int(load_settings().get('leverage', 1) or 1)
        async with get_exchange_for_task() as exchange:
            positions = await fetch_positions_with_pnl_async(exchange, leverage)

            async def worker(pos):
                # 杠杆推送到已有持仓（影响清算价，set_leverage 幂等，同值无副作用）。
                # 失败不阻断 SL/TP 同步——降级警告由 _set_leverage_safe_async 记录。
                try:
                    await _set_leverage_safe_async(exchange, pos.full_symbol, leverage, log_message)
                except Exception as exc:
                    await log_message(
                        f"⚠️ {pos.full_symbol}: 杠杆 {leverage}x 推送失败，保持原杠杆继续同步 SL/TP: {exc}",
                        "warning")
                return await set_tp_sl_for_position_async(exchange, pos, settings, log_message, self._stop_event)

            await self._run_task_loop(positions, worker, self.CONCURRENT_CLOSE_TASKS, task_name)
            if not self._stop_event.is_set():
                active_symbols = {p.full_symbol for p in positions}
                await cleanup_orphan_sltp_orders_async(exchange, active_symbols, log_message)

    # --- 手动做多 / 做空 / 反手 ---
    def manual_trade(self, request: ManualTradeRequest, background_tasks: BackgroundTasks):
        payload = {
            "request_id": request.request_id,
            "default_value": request.default_value,
            "items": [
                {"symbol": item.symbol, "action": normalize_action(item.action), "value": item.value}
                for item in request.items
            ],
        }
        try:
            validate_manual_items(payload["items"])
        except ValueError as e:
            # API 层转换为 400，且不创建 exchange / 不触达交易所
            raise HTTPException(status_code=400, detail=str(e))

        return self._start_task("手动交易", self._manual_trade_task(payload), background_tasks,
                                request.request_id)

    async def _manual_trade_task(self, payload: Dict[str, Any]):
        config = load_settings()
        items = payload.get("items") or []
        default_value = payload.get("default_value")

        # 反手必须先平后开，所有 worker 共用同一个 exchange（1 个任务 1 个实例）
        async with get_exchange_for_task() as exchange:
            positions = await fetch_positions_with_pnl_async(exchange, config.get('leverage', 1))
            tasks = build_manual_trade_tasks(items, positions, config, default_value=default_value)
            results: List[Dict[str, Any]] = []

            async def worker(task):
                try:
                    if task.skip_reason:
                        await log_message(f"⚠️ {task.coin}: {task.skip_reason}", "warning")
                        results.append({'coin': task.coin, 'side': task.side,
                                        'target_value': task.value, 'success': False,
                                        'skip_reason': task.skip_reason})
                        return False

                    if task.close_full_symbols:
                        for full_symbol in task.close_full_symbols:
                            if self._stop_event.is_set():
                                raise TaskInterruptedError()
                            closed = await close_position_async(
                                exchange, full_symbol, 1.0, log_message, self._stop_event)
                            if not closed:
                                await log_message(
                                    f"❌ {task.coin}: 平仓 {full_symbol} 失败或仍有残留，已取消反手开仓。", "error")
                                results.append({'coin': task.coin, 'side': task.side,
                                                'target_value': task.value, 'success': False,
                                                'error': f'反手平仓 {full_symbol} 失败'})
                                return False
                            await ws_manager.broadcast(
                                {"type": "position_closed",
                                 "payload": {"full_symbol": full_symbol, "ratio": 1.0}})
                            if self._stop_event.is_set():
                                raise TaskInterruptedError()

                    plan = {"coin": task.coin, "value": task.value, "side": task.side}
                    ok = await process_order_with_sl_tp_async(
                        exchange, plan, config, log_message, self._stop_event)
                    results.append({'coin': task.coin, 'side': task.side,
                                    'target_value': task.value, 'success': bool(ok),
                                    'auto_closed': bool(plan.get('_auto_closed')),
                                    'danger': plan.get('_danger'),
                                    'action': task.action})
                    return ok
                except Exception as e:
                    results.append({'coin': task.coin, 'side': task.side,
                                    'target_value': task.value, 'success': False, 'error': str(e)})
                    raise

            try:
                await self._run_task_loop(tasks, worker, self.CONCURRENT_OPEN_TASKS, "手动交易")
            finally:
                record_batch('manual', '手动交易', items=results)

    def execute_rebalance_plan(self, plan: ExecutionPlanRequest, background_tasks: BackgroundTasks):
        return self._start_task("执行仓位再平衡", self._rebalance_execution_task(plan), background_tasks,
                                plan.request_id)

    async def _rebalance_execution_task(self, plan: ExecutionPlanRequest):
        config = load_settings()
        task_name = "执行再平衡"

        # 统一使用一个 exchange：持仓快照与 worker 共用，避免重复 load_markets
        async with get_exchange_for_task() as exchange:
            all_positions = await fetch_positions_with_pnl_async(exchange, config.get('leverage', 1))
            position_map = {p.symbol: p.full_symbol for p in all_positions}
            results: List[Dict[str, Any]] = []

            # 再平衡也是长任务：开始即落「进行中」记录，结束更新
            pending_items = []
            for order_item in plan.orders:
                if order_item.action == 'CLOSE':
                    pending_items.append({'coin': order_item.symbol, 'side': 'close',
                                          'close_ratio': order_item.close_ratio, 'success': None})
                elif order_item.action == 'OPEN':
                    pending_items.append({'coin': order_item.symbol, 'side': order_item.side,
                                          'target_value': order_item.value_to_trade, 'success': None})
            pending_batch = record_batch('rebalance', '执行再平衡', items=pending_items)
            pending_id = (pending_batch or {}).get('id')

            async def worker(order_item):
                if self._stop_event.is_set():
                    return False
                try:
                    if order_item.action == 'CLOSE':
                        base_symbol = order_item.symbol
                        full_symbol = position_map.get(base_symbol)
                        if not full_symbol:
                            await log_message(f"⚠️ 无法为 {base_symbol} 找到当前持仓的完整交易对名称，跳过平仓。",
                                              "warning")
                            results.append({'coin': base_symbol, 'side': 'close', 'success': False,
                                            'skip_reason': '未找到持仓'})
                            return False

                        is_success = await close_position_async(
                            exchange, full_symbol, order_item.close_ratio, log_message, self._stop_event)
                        if is_success:
                            await ws_manager.broadcast(
                                {"type": "position_closed",
                                 "payload": {"full_symbol": full_symbol, "ratio": order_item.close_ratio}})
                        results.append({'coin': base_symbol, 'side': 'close',
                                        'close_ratio': order_item.close_ratio, 'success': bool(is_success)})
                        return is_success
                    elif order_item.action == 'OPEN':
                        order_plan_item = {'coin': order_item.symbol, 'value': order_item.value_to_trade,
                                           'side': order_item.side}
                        ok = await process_order_with_sl_tp_async(
                            exchange, order_plan_item, config, log_message, self._stop_event)
                        results.append({'coin': order_item.symbol, 'side': order_item.side,
                                        'target_value': order_item.value_to_trade, 'success': bool(ok)})
                        return ok
                    return False
                except Exception as e:
                    results.append({'coin': getattr(order_item, 'symbol', ''), 'success': False,
                                    'error': str(e)})
                    raise

            try:
                await self._run_task_loop(plan.orders, worker, self.CONCURRENT_OPEN_TASKS, task_name)
            finally:
                final_items = results or [
                    {**item, 'success': False, 'error': '任务中断，无执行结果'} for item in pending_items]
                record_batch('rebalance', '执行再平衡', items=final_items, record_id=pending_id)


trading_service = TradingService()
