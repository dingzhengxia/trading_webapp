# backend/app/core/trading_service.py (最终完整版)
import asyncio
from fastapi import HTTPException
from typing import Dict, Any, List, Tuple, Callable, Awaitable

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
        self._current_task: asyncio.Task = None
        self._stop_event = asyncio.Event()
        self._active_workers: set[asyncio.Task] = set()

        self.CONCURRENT_OPEN_TASKS = 5
        self.CONCURRENT_CLOSE_TASKS = 10

    def is_running(self) -> bool:
        return self._is_running

    async def _execute_and_log_task(self, task_name: str, task_coro: Awaitable):
        try:
            await log_message(f"--- 开始执行任务: {task_name} ---", "info")
            await task_coro
        except asyncio.CancelledError:
            await log_message(f"--- 任务 '{task_name}' 已被强制取消 ---", "warning")
        except InterruptedError:
            await log_message(f"--- ⚠️ 任务 '{task_name}' 已被用户优雅停止 ---", "warning")
        except Exception as e:
            error_msg = f"--- ❌ 任务 '{task_name}' 执行失败: {e} ---"
            await log_message(error_msg, "error")
            # 在HTTP请求的上下文中，我们可能想重新抛出异常
            # 对于后台任务，我们可能只想记录它
        finally:
            self._is_running = False
            self._current_task = None
            self._active_workers.clear()
            await update_status(f"'{task_name}' 已结束", is_running=False)

    async def _run_workers(self, items: List[Any], worker_func: Callable[[Any], Awaitable[bool]], concurrency: int,
                           task_name: str):
        total_tasks = len(items)
        if total_tasks == 0:
            return 0, 0

        await broadcast_progress_details(0, 0, total_tasks, task_name)

        semaphore = asyncio.Semaphore(concurrency)
        success_count = 0
        failure_count = 0

        async def wrapper(item):
            nonlocal success_count, failure_count
            is_success = False
            try:
                async with semaphore:
                    if self._stop_event.is_set():
                        raise InterruptedError()
                    is_success = await worker_func(item)
            except (InterruptedError, asyncio.CancelledError):
                # 这是一个预期的中断，不计为失败，只记录日志
                await log_message(f"一个 '{task_name}' 子任务被中断。", "warning")
            except Exception as e:
                is_success = False
                await log_message(f"处理 '{item}' 时出错: {e}", "error")
            finally:
                if is_success:
                    success_count += 1
                else:
                    failure_count += 1

                processed = success_count + failure_count
                await broadcast_progress_details(success_count, failure_count, total_tasks,
                                                 f"{task_name}: {processed}/{total_tasks}")

            return is_success

        self._active_workers = {asyncio.create_task(wrapper(item)) for item in items}
        results = await asyncio.gather(*self._active_workers)

        final_success_count = sum(1 for r in results if r is True)
        final_failure_count = len(items) - final_success_count

        if self._stop_event.is_set():
            raise InterruptedError("Task stopped by user.")

        return final_success_count, final_failure_count

    async def start_trading(self, plan_request: TradePlanRequest):
        if self._is_running: raise HTTPException(status_code=400, detail="A trading task is already in progress.")
        self._is_running = True
        self._stop_event.clear()
        config_dict = plan_request.model_dump()
        self._current_task = asyncio.create_task(
            self._execute_and_log_task("自动开仓", self._trading_loop_task(config_dict))
        )
        return {"message": "Trading task started successfully."}

    async def stop_trading(self):
        if not self._is_running:
            return {"message": "No active trading task to stop."}

        await log_message("收到停止信号，正在立即中断所有子任务...", "warning")
        self._stop_event.set()

        for worker in self._active_workers:
            worker.cancel()

        if self._current_task and not self._current_task.done():
            self._current_task.cancel()

        return {"message": "Stop signal sent, task cancellation initiated."}

    async def _trading_loop_task(self, config: Dict[str, Any]):
        task_name = "自动开仓"
        await update_status(f"正在执行: {task_name}...", is_running=True)
        long_plan, short_plan = calculate_trade_plan(config, config.get('long_custom_weights', {}))
        order_plan = [item for item in (
            [{'coin': c, 'value': v, 'side': 'buy'} for c, v in long_plan.items()] if config.get(
                'enable_long_trades') else []
        ) + (
                          [{'coin': c, 'value': v, 'side': 'sell'} for c, v in short_plan.items()] if config.get(
                              'enable_short_trades') else []
                      )]

        async def open_position_worker(plan_item):
            async with get_exchange_for_task() as exchange:
                await process_order_with_sl_tp_async(exchange, plan_item, config, log_message, self._stop_event)
            return True

        s, f = await self._run_workers(order_plan, open_position_worker, self.CONCURRENT_OPEN_TASKS, task_name)
        status_text = "部分成功" if f > 0 else "全部成功"
        await broadcast_progress_details(s, f, len(order_plan), f"{task_name} {status_text}", is_final=True)
        await log_message(f"{task_name}完成, 成功: {s}, 失败: {f}", "success" if f == 0 else "warning")

    async def dispatch_tasks(self, task_name: str, tasks_data: List[Tuple[str, float]], task_type: str,
                             config: Dict[str, Any]):
        if self._is_running: raise HTTPException(status_code=400, detail="A task is already running.")
        self._is_running = True
        self._stop_event.clear()
        self._current_task = asyncio.create_task(
            self._execute_and_log_task(task_name, self._generic_task_loop(tasks_data, task_type, config, task_name))
        )
        return {"message": f"任务 '{task_name}' 已开始。"}

    async def _generic_task_loop(self, tasks_data: List, task_type: str, config: Dict[str, Any], task_name: str):
        async def close_position_worker(task_item):
            full_symbol, ratio = task_item
            async with get_exchange_for_task() as exchange:
                is_success = await close_position_async(exchange, full_symbol, ratio, log_message)
                if is_success:
                    await ws_manager.broadcast(
                        {"type": "position_closed", "payload": {"full_symbol": full_symbol, "ratio": ratio}})
                return is_success

        if task_type == 'CLOSE_ORDER':
            s, f = await self._run_workers(tasks_data, close_position_worker, self.CONCURRENT_CLOSE_TASKS, task_name)
            status_text = "部分成功" if f > 0 else "全部成功"
            await broadcast_progress_details(s, f, len(tasks_data), f"{task_name} {status_text}", is_final=True)
            await log_message(f"{task_name}完成, 成功: {s}, 失败: {f}", "success" if f == 0 else "warning")

    async def sync_all_sltp(self, settings: dict):
        if self._is_running: raise HTTPException(status_code=400, detail="有其他任务正在运行。")
        self._is_running = True
        self._stop_event.clear()
        self._current_task = asyncio.create_task(
            self._execute_and_log_task("同步所有止盈止损", self._sync_sltp_task(settings))
        )
        return {"message": "同步SL/TP任务已开始。"}

    async def _sync_sltp_task(self, settings: dict):
        task_name = "同步SL/TP"
        await update_status(f"正在执行: {task_name}...", is_running=True)
        async with get_exchange_for_task() as exchange:
            positions = await fetch_positions_with_pnl_async(exchange, settings.get('leverage', 1))
            if not positions:
                await log_message("未发现任何持仓。", "info")
                return

            active_symbols = {p.full_symbol for p in positions}

            async def sltp_worker(pos):
                return await set_tp_sl_for_position_async(exchange, pos, settings, log_message)

            s, f = await self._run_workers(positions, sltp_worker, self.CONCURRENT_CLOSE_TASKS, task_name)

            await cleanup_orphan_sltp_orders_async(exchange, active_symbols, log_message)

        status_text = "部分成功" if f > 0 else "全部成功"
        await broadcast_progress_details(s, f, len(positions), f"{task_name} {status_text}", is_final=True)
        await log_message(f"{task_name}完成, 成功: {s}, 失败: {f}", "success" if f == 0 else "warning")

    async def execute_rebalance_plan(self, plan: ExecutionPlanRequest):
        if self._is_running: raise HTTPException(status_code=400, detail="有其他任务正在运行。")
        self._is_running = True
        self._stop_event.clear()
        self._current_task = asyncio.create_task(
            self._execute_and_log_task("执行仓位再平衡", self._rebalance_execution_task(plan))
        )
        return {"message": "再平衡任务已开始执行。"}

    async def _rebalance_execution_task(self, plan: ExecutionPlanRequest):
        config = load_settings()
        task_name = "执行再平衡"
        await update_status(f"正在执行: {task_name}...", is_running=True)

        async def rebalance_worker(order_item):
            if order_item.action == 'CLOSE':
                async with get_exchange_for_task() as exchange:
                    is_success = await close_position_async(exchange, order_item.symbol, order_item.close_ratio,
                                                            log_message)
                    if is_success:
                        await ws_manager.broadcast({"type": "position_closed",
                                                    "payload": {"full_symbol": order_item.symbol,
                                                                "ratio": order_item.close_ratio}})
                    return is_success
            elif order_item.action == 'OPEN':
                order_plan_item = {'coin': order_item.symbol.split('/')[0], 'value': order_item.value_to_trade,
                                   'side': order_item.side}
                async with get_exchange_for_task() as task_exchange:
                    await process_order_with_sl_tp_async(task_exchange, order_plan_item, config, log_message,
                                                         self._stop_event)
                return True
            return False

        s, f = await self._run_workers(plan.orders, rebalance_worker, self.CONCURRENT_OPEN_TASKS, task_name)

        status_text = "部分成功" if f > 0 else "全部成功"
        await broadcast_progress_details(s, f, len(plan.orders), f"{task_name} {status_text}", is_final=True)
        await log_message(f"{task_name}完成, 成功: {s}, 失败: {f}", "success" if f == 0 else "warning")


trading_service = TradingService()