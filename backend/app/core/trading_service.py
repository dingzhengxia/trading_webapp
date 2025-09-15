# backend/app/core/trading_service.py (最终完整版)
import asyncio
from fastapi import HTTPException
from typing import Dict, Any, List, Tuple

from ..config.config import load_settings
from ..logic.plan_calculator import calculate_trade_plan
from ..logic.exchange_logic_async import process_order_with_sl_tp_async, close_position_async, \
    InterruptedError, fetch_positions_with_pnl_async
from ..logic.sl_tp_logic_async import set_tp_sl_for_position_async, cleanup_orphan_sltp_orders_async
from ..models.schemas import ExecutionPlanRequest
from .websocket_manager import log_message, update_status, broadcast_progress_details, manager as ws_manager
from .exchange_manager import get_exchange_for_task


class TradingService:
    def __init__(self):
        self._is_running = False
        self._current_task: asyncio.Task = None
        self._stop_event = asyncio.Event()
        self._worker_task: asyncio.Task = None

        self.CONCURRENT_OPEN_TASKS = 5
        self.CONCURRENT_CLOSE_TASKS = 10

    async def start_worker(self):
        if self._worker_task and not self._worker_task.done():
            return
        self._worker_task = asyncio.create_task(self._task_executor())
        await log_message("Trading Service worker has started.", "info")

    async def _task_executor(self):
        pass

    def is_running(self) -> bool:
        return self._is_running

    async def _execute_and_log_task(self, task_name: str, task_coro):
        try:
            await log_message(f"--- 开始执行任务: {task_name} ---", "info")
            await task_coro
            await log_message(f"--- ✅ 任务 '{task_name}' 执行成功 ---", "success")
            return {"message": f"任务 '{task_name}' 执行成功"}
        except InterruptedError:
            await log_message(f"--- ⚠️ 任务 '{task_name}' 已被用户取消 ---", "warning")
            raise HTTPException(status_code=400, detail=f"任务 '{task_name}' 已被用户取消")
        except Exception as e:
            error_msg = f"--- ❌ 任务 '{task_name}' 执行失败: {e} ---"
            await log_message(error_msg, "error")
            raise HTTPException(status_code=500, detail=error_msg)
        finally:
            self._is_running = False
            await update_status(f"'{task_name}' 已结束", is_running=False)

    async def start_trading(self, plan_request: Dict[str, Any]):
        if self._is_running:
            raise HTTPException(status_code=400, detail="A trading task is already in progress.")
        self._is_running = True
        self._stop_event.clear()
        self._current_task = asyncio.create_task(
            self._execute_and_log_task("自动开仓", self._trading_loop_task(plan_request))
        )
        return {"message": "Trading task started successfully."}

    async def stop_trading(self):
        if not self._is_running or not self._current_task:
            return {"message": "No active trading task to stop."}
        self._stop_event.set()
        await log_message("收到停止信号...", "warning")
        try:
            await asyncio.wait_for(self._current_task, timeout=30)
        except asyncio.TimeoutError:
            self._current_task.cancel()
            await log_message("任务在30秒内未正常停止，已强制取消。", "error")
        finally:
            self._is_running = False
            self._current_task = None
            await update_status("交易已停止", is_running=False)
        return {"message": "Trading task stopped."}

    async def _trading_loop_task(self, config: Dict[str, Any]):
        task_name = "自动开仓"
        await update_status(f"正在执行: {task_name}...", is_running=True)
        long_plan, short_plan = calculate_trade_plan(config, config.get('long_custom_weights', {}))
        order_plan = []
        if config.get('enable_long_trades'):
            order_plan.extend([{'coin': c, 'value': v, 'side': 'buy'} for c, v in long_plan.items()])
        if config.get('enable_short_trades'):
            order_plan.extend([{'coin': c, 'value': v, 'side': 'sell'} for c, v in short_plan.items()])

        if not order_plan:
            await log_message("没有计算出有效的交易计划。", "warning")
            return

        total_tasks = len(order_plan)
        await broadcast_progress_details(0, 0, total_tasks, task_name)

        semaphore = asyncio.Semaphore(self.CONCURRENT_OPEN_TASKS)
        success_count = 0
        failure_count = 0

        async def worker(plan_item):
            nonlocal success_count, failure_count
            try:
                async with semaphore:
                    if self._stop_event.is_set(): return
                    async with get_exchange_for_task() as exchange:
                        await process_order_with_sl_tp_async(exchange, plan_item, config, log_message, self._stop_event)
                    success_count += 1
            except Exception as e:
                failure_count += 1
                await log_message(f"处理 {plan_item.get('coin')} 时出错: {e}", "error")
            finally:
                processed = success_count + failure_count
                await broadcast_progress_details(success_count, failure_count, total_tasks,
                                                 f"{task_name}: {processed}/{total_tasks}")

        tasks = [worker(plan_item) for plan_item in order_plan]
        await asyncio.gather(*tasks)

        if self._stop_event.is_set(): raise InterruptedError("Trading stopped by user.")

        status_text = "部分成功" if failure_count > 0 else "全部成功"
        await broadcast_progress_details(success_count, failure_count, total_tasks, f"{task_name} {status_text}",
                                         is_final=True)

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
        total = len(tasks_data)
        if total == 0:
            await log_message("任务列表为空。", "info")
            return

        await update_status(f"正在执行: {task_name}...", is_running=True)
        await broadcast_progress_details(0, 0, total, task_name)

        concurrency_limit = self.CONCURRENT_CLOSE_TASKS if task_type == 'CLOSE_ORDER' else 1
        semaphore = asyncio.Semaphore(concurrency_limit)
        success_count = 0
        failure_count = 0

        async def worker(task_item):
            nonlocal success_count, failure_count
            full_symbol, ratio = task_item
            is_success = False
            try:
                async with semaphore:
                    if self._stop_event.is_set(): return
                    async with get_exchange_for_task() as exchange:
                        if task_type == 'CLOSE_ORDER':
                            is_success = await close_position_async(exchange, full_symbol, ratio, log_message)

                    if is_success:
                        success_count += 1
                        await ws_manager.broadcast(
                            {"type": "position_closed", "payload": {"full_symbol": full_symbol, "ratio": ratio}})
                    else:
                        failure_count += 1
            except Exception as e:
                failure_count += 1
                await log_message(f"处理 {full_symbol} 时出错: {e}", "error")
            finally:
                processed = success_count + failure_count
                await broadcast_progress_details(success_count, failure_count, total,
                                                 f"{task_name}: {processed}/{total}")

        tasks = [worker(item) for item in tasks_data]
        await asyncio.gather(*tasks)

        if self._stop_event.is_set(): raise InterruptedError("Operation stopped by user.")

        status_text = "部分成功" if failure_count > 0 else "全部成功"
        await broadcast_progress_details(success_count, failure_count, total, f"{task_name} {status_text}",
                                         is_final=True)

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

            total = len(positions)
            await broadcast_progress_details(0, 0, total, task_name)
            active_symbols = {p.full_symbol for p in positions}
            success_count = 0
            failure_count = 0

            semaphore = asyncio.Semaphore(self.CONCURRENT_CLOSE_TASKS)  # Use a semaphore for concurrency

            async def worker(pos):
                nonlocal success_count, failure_count
                async with semaphore:
                    try:
                        if self._stop_event.is_set(): return
                        await log_message(f"--- 正在为 {pos.symbol} ({pos.side}) 校准 SL/TP ---")
                        result = await set_tp_sl_for_position_async(exchange, pos, settings, log_message)
                        if result:
                            success_count += 1
                        else:
                            failure_count += 1
                    except Exception as e:
                        failure_count += 1
                        await log_message(f"为 {pos.symbol} 校准SL/TP时发生严重错误: {e}", "error")
                    finally:
                        processed = success_count + failure_count
                        await broadcast_progress_details(success_count, failure_count, total,
                                                         f"{task_name}: {processed}/{total}")

            tasks = [worker(p) for p in positions]
            await asyncio.gather(*tasks)

            if self._stop_event.is_set(): raise InterruptedError("SL/TP sync was cancelled.")

            await cleanup_orphan_sltp_orders_async(exchange, active_symbols, log_message)

        status_text = "部分成功" if failure_count > 0 else "全部成功"
        await broadcast_progress_details(success_count, failure_count, total, f"{task_name} {status_text}",
                                         is_final=True)

    async def execute_rebalance_plan(self, plan: ExecutionPlanRequest):
        if self._is_running:
            raise HTTPException(status_code=400, detail="有其他任务正在运行。")

        self._is_running = True
        self._stop_event.clear()

        self._current_task = asyncio.create_task(
            self._execute_and_log_task(
                "执行仓位再平衡",
                self._rebalance_execution_task(plan)
            )
        )
        return {"message": "再平衡任务已开始执行。"}

    async def _rebalance_execution_task(self, plan: ExecutionPlanRequest):
        # Note: This task can also be refactored to provide detailed progress,
        # but for now, it retains its original simpler progress logic.
        config = load_settings()
        task_name = "执行再平衡"

        close_orders = [o for o in plan.orders if o.action == 'CLOSE']
        open_orders = [o for o in plan.orders if o.action == 'OPEN']

        total_steps = len(close_orders) + len(open_orders)
        current_step = 0
        success_count, failure_count = 0, 0

        await update_status(f"正在执行: {task_name}...", is_running=True)
        await broadcast_progress_details(0, 0, total_steps, task_name)

        if close_orders:
            close_semaphore = asyncio.Semaphore(self.CONCURRENT_CLOSE_TASKS)

            async def close_worker(order_item):
                nonlocal current_step, success_count, failure_count
                async with close_semaphore:
                    if self._stop_event.is_set(): return
                    is_success = False
                    try:
                        async with get_exchange_for_task() as exchange:
                            is_success = await close_position_async(exchange, order_item.symbol, order_item.close_ratio,
                                                                    log_message)
                            if is_success:
                                success_count += 1
                                await ws_manager.broadcast({"type": "position_closed",
                                                            "payload": {"full_symbol": order_item.symbol,
                                                                        "ratio": order_item.close_ratio}})
                            else:
                                failure_count += 1
                    except Exception as e:
                        failure_count += 1
                        await log_message(f"再平衡平仓 {order_item.symbol} 失败: {e}", "error")
                    finally:
                        current_step += 1
                        await broadcast_progress_details(success_count, failure_count, total_steps,
                                                         f"{task_name}: {current_step}/{total_steps}")

            await asyncio.gather(*(close_worker(item) for item in close_orders))

        if open_orders:
            open_semaphore = asyncio.Semaphore(self.CONCURRENT_OPEN_TASKS)

            async def open_worker(order_item):
                nonlocal current_step, success_count, failure_count
                async with open_semaphore:
                    if self._stop_event.is_set(): return
                    try:
                        order_plan_item = {'coin': order_item.symbol.split('/')[0], 'value': order_item.value_to_trade,
                                           'side': order_item.side}
                        async with get_exchange_for_task() as task_exchange:
                            await process_order_with_sl_tp_async(task_exchange, order_plan_item, config, log_message,
                                                                 self._stop_event)
                        success_count += 1
                    except Exception as e:
                        failure_count += 1
                        await log_message(f"再平衡开仓 {order_item.symbol} 失败: {e}", "error")
                    finally:
                        current_step += 1
                        await broadcast_progress_details(success_count, failure_count, total_steps,
                                                         f"{task_name}: {current_step}/{total_steps}")

            await asyncio.gather(*(open_worker(item) for item in open_orders))

        if self._stop_event.is_set(): raise InterruptedError("再平衡任务被取消")

        status_text = "部分成功" if failure_count > 0 else "全部成功"
        await broadcast_progress_details(success_count, failure_count, total_steps, f"{task_name} {status_text}",
                                         is_final=True)


trading_service = TradingService()