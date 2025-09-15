# backend/app/core/trading_service.py (完整代码)
import asyncio
from fastapi import HTTPException
from typing import Dict, Any, List, Tuple

from ..config.config import load_settings
from ..logic.plan_calculator import calculate_trade_plan
from ..logic.exchange_logic_async import process_order_with_sl_tp_async, close_position_async, \
    InterruptedError, fetch_positions_with_pnl_async
from ..logic.sl_tp_logic_async import set_tp_sl_for_position_async, cleanup_orphan_sltp_orders_async
from ..models.schemas import ExecutionPlanRequest, Position
from .websocket_manager import log_message, update_status, broadcast_progress, manager as ws_manager
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
            result = await task_coro
            await log_message(f"--- ✅ 任务 '{task_name}' 执行成功 ---", "success")
            return {"message": f"任务 '{task_name}' 执行成功", "details": result}
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
            await log_message("交易任务正在进行中，请勿重复启动。", "warning")
            raise HTTPException(status_code=400, detail="A trading task is already in progress.")

        self._is_running = True
        self._stop_event.clear()

        config = plan_request.model_dump()

        self._current_task = asyncio.create_task(
            self._execute_and_log_task(
                "自动交易",
                self._trading_loop_task(config)
            )
        )
        return {"message": "Trading task started successfully."}

    async def stop_trading(self):
        if not self._is_running or not self._current_task:
            return {"message": "No active trading task to stop."}

        await log_message("收到停止信号，正在停止所有交易活动...", "warning")
        self._stop_event.set()

        try:
            await asyncio.wait_for(self._current_task, timeout=30)
        except asyncio.TimeoutError:
            self._current_task.cancel()
            await log_message("任务在30秒内未正常停止，已强制取消。", "error")
        except Exception:
            pass
        finally:
            self._is_running = False
            self._current_task = None
            await update_status("交易已停止", is_running=False)

        return {"message": "Trading task stopped."}

    async def _trading_loop_task(self, config: Dict[str, Any]):
        await update_status("交易任务初始化...", is_running=True)

        long_plan, short_plan = calculate_trade_plan(config, config.get('long_custom_weights', {}))

        order_plan = []
        if config.get('enable_long_trades'):
            order_plan.extend([{'coin': c, 'value': v, 'side': 'buy'} for c, v in long_plan.items()])
        if config.get('enable_short_trades'):
            order_plan.extend([{'coin': c, 'value': v, 'side': 'sell'} for c, v in short_plan.items()])

        if not order_plan:
            await log_message("没有计算出有效的交易计划，任务结束。", "warning")
            return

        total_tasks = len(order_plan)
        await log_message(f"交易计划生成完毕，共 {total_tasks} 个订单，将以 {self.CONCURRENT_OPEN_TASKS} 个并发执行。",
                          "info")

        semaphore = asyncio.Semaphore(self.CONCURRENT_OPEN_TASKS)

        processed_count = 0

        async def worker(plan_item):
            nonlocal processed_count
            async with semaphore:
                if self._stop_event.is_set():
                    return

                try:
                    async with get_exchange_for_task() as exchange:
                        await process_order_with_sl_tp_async(exchange, plan_item, config, log_message, self._stop_event)
                except Exception as e:
                    await log_message(f"处理 {plan_item.get('coin')} 时出现顶层错误: {e}", "error")
                finally:
                    processed_count += 1
                    await broadcast_progress(processed_count, total_tasks, f"已完成 {processed_count}/{total_tasks}")

        tasks = [worker(plan_item) for plan_item in order_plan]
        await asyncio.gather(*tasks)

        if self._stop_event.is_set():
            raise InterruptedError("Trading was stopped by user.")

        await broadcast_progress(total_tasks, total_tasks, "所有订单处理完毕")
        await log_message("所有计划订单均已处理完毕。", "success")

    async def dispatch_tasks(self, task_name: str, tasks_data: List[Tuple[str, float]], task_type: str,
                             config: Dict[str, Any]):
        if self._is_running:
            raise HTTPException(status_code=400, detail="主交易任务正在运行，请稍后再试。")

        self._is_running = True
        self._stop_event.clear()

        self._current_task = asyncio.create_task(
            self._execute_and_log_task(
                task_name,
                self._generic_task_loop(tasks_data, task_type, config)
            )
        )
        return {"message": f"任务 '{task_name}' 已开始执行。"}

    async def _generic_task_loop(self, tasks_data: List, task_type: str, config: Dict[str, Any]):
        total = len(tasks_data)
        if total == 0:
            await log_message("任务列表为空，无需执行。", "info")
            return

        await update_status("正在执行批量操作...", is_running=True)

        if task_type == 'CLOSE_ORDER':
            concurrency_limit = self.CONCURRENT_CLOSE_TASKS
            await log_message(f"批量平仓任务启动，共 {total} 个仓位，将以 {concurrency_limit} 个并发执行。", "info")
        else:
            concurrency_limit = 1

        semaphore = asyncio.Semaphore(concurrency_limit)
        processed_count = 0

        async def worker(task_item):
            nonlocal processed_count
            async with semaphore:
                if self._stop_event.is_set():
                    return

                full_symbol, ratio = task_item
                try:
                    async with get_exchange_for_task() as exchange:
                        if task_type == 'CLOSE_ORDER':
                            success = await close_position_async(exchange, full_symbol, ratio, log_message)
                            if success:
                                await ws_manager.broadcast({
                                    "type": "position_closed",
                                    "payload": {
                                        "full_symbol": full_symbol,
                                        "ratio": ratio
                                    }
                                })
                except Exception as e:
                    await log_message(f"处理 {full_symbol} 时出现错误: {e}", "error")
                finally:
                    processed_count += 1
                    await broadcast_progress(processed_count, total, f"已处理 {processed_count}/{total}")

        tasks = [worker(item) for item in tasks_data]
        await asyncio.gather(*tasks)

        if self._stop_event.is_set():
            raise InterruptedError("操作被用户停止。")

        await broadcast_progress(total, total, "批量操作完成")

    async def sync_all_sltp(self, settings: dict):
        if self._is_running:
            raise HTTPException(status_code=400, detail="有其他任务正在运行，请稍后再试。")

        self._is_running = True
        self._stop_event.clear()

        self._current_task = asyncio.create_task(
            self._execute_and_log_task(
                "同步所有止盈止损",
                self._sync_sltp_task(settings)
            )
        )
        return {"message": "同步SL/TP任务已开始。"}

    async def _sync_sltp_task(self, settings: dict):
        await update_status("正在同步所有SL/TP...", is_running=True)
        async with get_exchange_for_task() as exchange:
            positions = await fetch_positions_with_pnl_async(exchange, settings.get('leverage', 1))
            if not positions:
                await log_message("未发现任何持仓，无需同步SL/TP。", "info")
                return

            total = len(positions)
            active_symbols = [p.full_symbol for p in positions]

            for i, pos in enumerate(positions):
                if self._stop_event.is_set():
                    raise InterruptedError("SL/TP同步任务被取消。")
                await broadcast_progress(i, total, f"同步 {pos.symbol}")
                await log_message(f"--- 正在为 {pos.symbol} ({pos.side}) 校准 SL/TP ---")
                await set_tp_sl_for_position_async(exchange, pos, settings, log_message)

            await broadcast_progress(total, total, "同步完成")
            await cleanup_orphan_sltp_orders_async(exchange, active_symbols, log_message)
        await log_message("所有持仓的SL/TP同步完成。", "success")

    async def execute_rebalance_plan(self, plan: ExecutionPlanRequest):
        if self._is_running:
            raise HTTPException(status_code=400, detail="有其他任务正在运行，请稍后再试。")

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
        config = load_settings()

        close_orders = [o for o in plan.orders if o.action == 'CLOSE']
        open_orders = [o for o in plan.orders if o.action == 'OPEN']

        total_steps = len(close_orders) + len(open_orders)
        current_step = 0

        await update_status("开始执行再平衡计划...", is_running=True)

        if close_orders:
            await log_message(f"开始执行 {len(close_orders)} 个平仓任务，并发数: {self.CONCURRENT_CLOSE_TASKS}...",
                              "info")
            close_semaphore = asyncio.Semaphore(self.CONCURRENT_CLOSE_TASKS)

            async def close_worker(order_item):
                nonlocal current_step
                async with close_semaphore:
                    if self._stop_event.is_set(): return
                    current_step += 1
                    await broadcast_progress(current_step, total_steps, f"平仓: {order_item.symbol}")
                    try:
                        async with get_exchange_for_task() as exchange:
                           success = await close_position_async(exchange, order_item.symbol, order_item.close_ratio, log_message)
                           if success:
                                await ws_manager.broadcast({
                                    "type": "position_closed",
                                    "payload": {
                                        "full_symbol": order_item.symbol,
                                        "ratio": order_item.close_ratio
                                    }
                                })
                    except Exception as e:
                        await log_message(f"再平衡平仓 {order_item.symbol} 失败: {e}", "error")

            close_tasks = [close_worker(item) for item in close_orders]
            await asyncio.gather(*close_tasks)

        if open_orders:
            await log_message(f"开始执行 {len(open_orders)} 个开仓任务，并发数: {self.CONCURRENT_OPEN_TASKS}...", "info")
            open_semaphore = asyncio.Semaphore(self.CONCURRENT_OPEN_TASKS)

            async def open_worker(order_item):
                nonlocal current_step
                async with open_semaphore:
                    if self._stop_event.is_set(): return
                    current_step += 1
                    await broadcast_progress(current_step, total_steps, f"开仓: {order_item.symbol}")
                    order_plan_item = {
                        'coin': order_item.symbol.split('/')[0],
                        'value': order_item.value_to_trade,
                        'side': order_item.side
                    }
                    try:
                        async with get_exchange_for_task() as task_exchange:
                            await process_order_with_sl_tp_async(task_exchange, order_plan_item, config, log_message,
                                                                 self._stop_event)
                    except Exception as e:
                        await log_message(f"再平衡开仓 {order_item.symbol} 失败: {e}", "error")

            open_tasks = [open_worker(item) for item in open_orders]
            await asyncio.gather(*open_tasks)

        if self._stop_event.is_set():
            raise InterruptedError("再平衡任务被取消")

        await broadcast_progress(total_steps, total_steps, "再平衡计划执行完毕")
        await log_message("✅ 所有再平衡操作已成功执行完毕。", "success")


trading_service = TradingService()