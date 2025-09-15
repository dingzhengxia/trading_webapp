# backend/app/core/trading_service.py (最终修复版)
import asyncio
from fastapi import HTTPException, BackgroundTasks
from typing import Dict, Any, List, Tuple, Callable, Awaitable
import threading
import time

from ..config.config import load_settings
from ..logic.plan_calculator import calculate_trade_plan
from ..logic.exchange_logic_async import process_order_with_sl_tp_async, close_position_async, \
    InterruptedError, fetch_positions_with_pnl_async
from ..logic.sl_tp_logic_async import set_tp_sl_for_position_async, cleanup_orphan_sltp_orders_async
from ..models.schemas import ExecutionPlanRequest, TradePlanRequest
from .websocket_manager import log_message, update_status, broadcast_progress_details, manager as ws_manager
from .exchange_manager import get_exchange_for_task


class TradingService:
    def __init__(self):
        self._is_running = False
        self._stop_event = asyncio.Event()
        self._task_progress: Dict[str, Any] = {}
        self._lock = threading.Lock()

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
            end_time = time.time()
            await log_message(f"--- [LOG] ✅ 任务 '{task_name}' 已结束，总耗时: {end_time - start_time:.2f} 秒 ---",
                              "success")
            await update_status(f"'{task_name}' 已结束", is_running=False)

    # --- 核心修改在这里：将 def 改为 async def ---
    async def _start_task(self, task_name: str, task_coro: Awaitable, background_tasks: BackgroundTasks):
        await log_message(f"[LOG] 接收到启动 '{task_name}' 的请求...", "info")
        with self._lock:
            if self._is_running:
                await log_message(f"[LOG] ❌ 启动 '{task_name}' 失败：已有任务在运行。", "error")
                raise HTTPException(status_code=400, detail="已有任务在运行中，请稍后再试。")

            self._is_running = True
            self._stop_event.clear()
            self._task_progress = {"task_name": task_name}
            background_tasks.add_task(self._execute_and_log_task, task_name, task_coro)
            await log_message(f"[LOG] ✅ 任务 '{task_name}' 已成功提交到后台队列。", "success")

        return {"message": f"任务 '{task_name}' 已成功提交到后台。"}

    async def _run_task_loop(self, items: List[Any], worker_func: Callable, concurrency: int, task_name: str):
        total_tasks = len(items)
        success_count, failure_count = 0, 0
        self._task_progress = {"success_count": 0, "failed_count": 0, "total": total_tasks, "task_name": task_name}
        await broadcast_progress_details(**self._task_progress)
        await log_message(f"[LOG] '{task_name}' 循环开始，总任务数: {total_tasks}, 并发数: {concurrency}", "info")

        if not items:
            await log_message(f"[LOG] 任务 '{task_name}' 列表为空，提前结束。", "info")
            await broadcast_progress_details(0, 0, 0, "任务列表为空", is_final=True)
            return

        semaphore = asyncio.Semaphore(concurrency)

        async def worker_wrapper(item, index):
            nonlocal success_count, failure_count
            if self._stop_event.is_set(): return
            async with semaphore:
                if self._stop_event.is_set(): return
                is_success = False
                await log_message(f"[LOG] >> 子任务 {index + 1}/{total_tasks} 开始...", "normal")
                try:
                    is_success = await worker_func(item)
                except Exception as e:
                    await log_message(f"[LOG] >> ❌ 子任务 {index + 1} 发生意外错误: {e}", "error")
                finally:
                    if is_success:
                        success_count += 1
                        await log_message(f"[LOG] >> ✅ 子任务 {index + 1} 成功。", "success")
                    else:
                        failure_count += 1
                        await log_message(f"[LOG] >> ⚠️ 子任务 {index + 1} 失败。", "warning")

                    processed = success_count + failure_count
                    current_progress = self._task_progress.copy()
                    current_progress.update({"success_count": success_count, "failed_count": failure_count,
                                             "task_name": f"{task_name}: {processed}/{total_tasks}"})
                    await broadcast_progress_details(**current_progress)

        tasks = [asyncio.create_task(worker_wrapper(item, i)) for i, item in enumerate(items)]
        await asyncio.wait(tasks)

        if self._stop_event.is_set(): raise InterruptedError()

        status_text = "部分成功" if failure_count > 0 else "全部成功"
        final_progress = self._task_progress.copy()
        final_progress.update(
            {"is_final": True, "task_name": f"{task_name} {status_text}", "success_count": success_count,
             "failed_count": failure_count})
        await broadcast_progress_details(**final_progress)
        await log_message(f"[LOG] '{task_name}' 循环结束, 成功: {success_count}, 失败: {failure_count}", "info")

    async def start_trading(self, plan_request: TradePlanRequest, background_tasks: BackgroundTasks):
        return await self._start_task("自动开仓", self._trading_loop_task(plan_request.model_dump()), background_tasks)

    async def stop_trading(self):
        if not self._is_running:
            await log_message("[LOG] 收到停止请求，但当前无任务运行。", "warning")
            return {"message": "No active task."}
        await log_message("[LOG] 收到停止信号，正在设置停止事件...", "warning")
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

    async def dispatch_tasks(self, task_name: str, tasks_data: List[Tuple[str, float]], task_type: str,
                             config: Dict[str, Any], background_tasks: BackgroundTasks):
        task_coro = self._generic_task_loop(tasks_data, task_type, config, task_name)
        return await self._start_task(task_name, task_coro, background_tasks)

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

    async def sync_all_sltp(self, settings: dict, background_tasks: BackgroundTasks):
        return await self._start_task("同步所有止盈止损", self._sync_sltp_task(settings), background_tasks)

    async def _sync_sltp_task(self, settings: dict):
        task_name = "同步SL/TP"
        await log_message(f"[LOG] '{task_name}' 任务启动，正在获取交易所连接...", "info")
        async with get_exchange_for_task() as exchange:
            await log_message("[LOG] 交易所连接成功，正在获取持仓...", "info")
            positions = await fetch_positions_with_pnl_async(exchange, settings.get('leverage', 1))

            async def worker(pos):
                return await set_tp_sl_for_position_async(exchange, pos, settings, log_message, self._stop_event)

            await self._run_task_loop(positions, worker, self.CONCURRENT_CLOSE_TASKS, task_name)

            if not self._stop_event.is_set():
                await log_message("[LOG] 正在清理无主SL/TP订单...", "info")
                active_symbols = {p.full_symbol for p in positions}
                await cleanup_orphan_sltp_orders_async(exchange, active_symbols, log_message)

    async def execute_rebalance_plan(self, plan: ExecutionPlanRequest, background_tasks: BackgroundTasks):
        return await self._start_task("执行仓位再平衡", self._rebalance_execution_task(plan), background_tasks)

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