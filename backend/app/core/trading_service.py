# backend/app/core/trading_service.py (最终完整版)
import asyncio
from fastapi import HTTPException, BackgroundTasks
from typing import Dict, Any, List, Tuple, Callable, Awaitable, Optional
import threading
import time

from ..config.config import load_settings
from ..logic.plan_calculator import calculate_trade_plan
from ..logic.exchange_logic_async import process_order_with_sl_tp_async, close_position_async, \
    InterruptedError, fetch_positions_with_pnl_async
from ..logic.sl_tp_logic_async import set_tp_sl_for_position_async, cleanup_orphan_sltp_orders_async
from ..models.schemas import ExecutionPlanRequest, TradePlanRequest, SyncSltpRequest
from .websocket_manager import log_message, update_status, broadcast_progress_details
from .exchange_manager import get_exchange_for_task


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
        except InterruptedError:
            await log_message(f"--- [LOG] ⚠️ 任务 '{task_name}' 被用户停止 ---", "warning")
        except Exception as e:
            await log_message(f"--- [LOG] ❌ 任务 '{task_name}' 执行时发生顶层异常: {e} ---", "error")
        finally:
            with self._lock:
                self._is_running = False
                self._task_progress = {}
                self._last_request_id = None  # 任务结束后清除请求ID
            end_time = time.time()
            await log_message(f"--- [LOG] ✅ 任务 '{task_name}' 已结束，总耗时: {end_time - start_time:.2f} 秒 ---",
                              "success")
            await update_status(f"'{task_name}' 已结束", is_running=False)

    def _start_task(self, task_name: str, task_coro: Awaitable, background_tasks: BackgroundTasks,
                    request_id: Optional[str] = None):
        print(f"[LOG] 接收到启动 '{task_name}' 的请求 (ID: {request_id})...")
        with self._lock:
            if self._is_running:
                if request_id and request_id == self._last_request_id:
                    print(f"[LOG] ⚠️ 捕获到重复的请求ID '{request_id}'，已忽略。")
                    return {"message": "重复的任务请求已被忽略。"}
                print(
                    f"[LOG] ❌ 启动 '{task_name}' 失败：已有任务 '{self._task_progress.get('task_name', '未知')}' 在运行。")
                raise HTTPException(status_code=400, detail="已有任务在运行中，请稍后再试。")

            self._is_running = True
            self._stop_event.clear()
            self._last_request_id = request_id
            self._task_progress = {"task_name": task_name}
            background_tasks.add_task(self._execute_and_log_task, task_name, task_coro)
            print(f"[LOG] ✅ 任务 '{task_name}' (ID: {request_id}) 已成功提交到后台队列。")

        return {"message": f"任务 '{task_name}' 已成功提交到后台。"}

    async def _run_task_loop(self, items: List[Any], worker_func: Callable, concurrency: int, task_name: str):
        total_tasks = len(items)
        success_count, failure_count = 0, 0
        self._task_progress = {"success_count": 0, "failed_count": 0, "total": total_tasks, "task_name": task_name}
        await broadcast_progress_details(**self._task_progress)

        if not items:
            await log_message(f"[LOG] 任务 '{task_name}' 列表为空，提前结束。", "info")
            await broadcast_progress_details(0, 0, 0, "任务列表为空", is_final=True)
            return

        semaphore = asyncio.Semaphore(concurrency)

        async def worker_wrapper(item):
            nonlocal success_count, failure_count
            if self._stop_event.is_set(): return
            async with semaphore:
                if self._stop_event.is_set(): return
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

        if self._stop_event.is_set(): raise InterruptedError()

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

    async def _trading_loop_task(self, config: Dict[str, Any]):
        long_plan, short_plan = calculate_trade_plan(config, config.get('long_custom_weights', {}))
        order_plan = [item for item in (
            [{'coin': c, 'value': v, 'side': 'buy'} for c, v in long_plan.items()] if config.get(
                'enable_long_trades') else []
        ) + ([{'coin': c, 'value': v, 'side': 'sell'} for c, v in short_plan.items()] if config.get(
            'enable_short_trades') else [])]

        async def worker(plan_item):
            async with get_exchange_for_task() as exchange:
                return await process_order_with_sl_tp_async(exchange, plan_item, config, log_message, self._stop_event)

        await self._run_task_loop(order_plan, worker, self.CONCURRENT_OPEN_TASKS, "自动开仓")

    def dispatch_tasks(self, task_name: str, tasks_data: List[Tuple[str, float]], task_type: str,
                       config: Dict[str, Any], background_tasks: BackgroundTasks, request_id: Optional[str] = None):
        task_coro = self._generic_task_loop(tasks_data, task_type, config, task_name)
        return self._start_task(task_name, task_coro, background_tasks, request_id)

    async def _generic_task_loop(self, tasks_data: List, task_type: str, config: Dict[str, Any], task_name: str):
        async def worker(task_item):
            if task_type == 'CLOSE_ORDER':
                full_symbol, ratio = task_item
                async with get_exchange_for_task() as exchange:
                    is_success = await close_position_async(exchange, full_symbol, ratio, log_message, self._stop_event)
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
        async with get_exchange_for_task() as exchange:
            positions = await fetch_positions_with_pnl_async(exchange, settings.get('leverage', 1))

            async def worker(pos):
                return await set_tp_sl_for_position_async(exchange, pos, settings, log_message, self._stop_event)

            await self._run_task_loop(positions, worker, self.CONCURRENT_CLOSE_TASKS, task_name)
            if not self._stop_event.is_set():
                active_symbols = {p.full_symbol for p in positions}
                await cleanup_orphan_sltp_orders_async(exchange, active_symbols, log_message)

    def execute_rebalance_plan(self, plan: ExecutionPlanRequest, background_tasks: BackgroundTasks):
        return self._start_task("执行仓位再平衡", self._rebalance_execution_task(plan), background_tasks,
                                plan.request_id)

    async def _rebalance_execution_task(self, plan: ExecutionPlanRequest):
        config = load_settings()
        task_name = "执行再平衡"

        async def worker(order_item):
            if self._stop_event.is_set(): return False
            if order_item.action == 'CLOSE':
                async with get_exchange_for_task() as exchange:
                    is_success = await close_position_async(exchange, order_item.symbol, order_item.close_ratio,
                                                            log_message, self._stop_event)
                    if is_success:
                        await ws_manager.broadcast({"type": "position_closed",
                                                    "payload": {"full_symbol": order_item.symbol,
                                                                "ratio": order_item.close_ratio}})
                    return is_success
            elif order_item.action == 'OPEN':
                async with get_exchange_for_task() as task_exchange:
                    order_plan_item = {'coin': order_item.symbol.split('/')[0], 'value': order_item.value_to_trade,
                                       'side': order_item.side}
                    return await process_order_with_sl_tp_async(task_exchange, order_plan_item, config, log_message,
                                                                self._stop_event)
            return False

        await self._run_task_loop(plan.orders, worker, self.CONCURRENT_OPEN_TASKS, task_name)


trading_service = TradingService()