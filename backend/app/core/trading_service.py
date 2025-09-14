import asyncio
from asyncio import Queue, Task
from typing import List, Set
from ..models.schemas import TradePlanRequest, ExecutionPlanRequest, Position
from ..logic import plan_calculator
from ..core.exchange_manager import get_exchange_for_task
from ..core.websocket_manager import log_message, update_status, manager, broadcast_progress
from ..config import i18n
from ..config.config import load_settings
from ..logic import exchange_logic_async as ex_async
from ..logic import sl_tp_logic_async as sltp_async

TRADE_TASK_QUEUE = Queue()
NUM_WORKERS = 5  # 可控的并发 worker 数量


class TradingService:
    def __init__(self):
        self.is_running_lock = asyncio.Lock()
        self.is_running = False
        self.stop_event = asyncio.Event()
        self.worker_tasks: Set[Task] = set()
        self.current_task_info = {}

    async def start_worker(self):
        """在应用启动时，启动并发 worker 池"""
        if not self.worker_tasks:
            self.worker_tasks = {
                asyncio.create_task(self._trade_task_worker(i + 1))
                for i in range(NUM_WORKERS)
            }
            print(f"{NUM_WORKERS} trading task workers have been started.")

    async def _trade_task_worker(self, worker_id: int):
        """一个长期运行的 worker，从队列中获取并处理交易任务。"""
        await log_message(f"交易任务处理器 #{worker_id} 已启动...", "info")
        while True:
            try:
                task_type, data, config_dict = await TRADE_TASK_QUEUE.get()

                if self.stop_event.is_set():
                    TRADE_TASK_QUEUE.task_done()
                    continue

                # 执行具体任务
                async with get_exchange_for_task() as exchange:
                    if task_type == 'SINGLE_ORDER':
                        await self._run_single_order(exchange, data, config_dict)
                    elif task_type == 'CLOSE_ORDER':
                        full_symbol, ratio = data

                        def create_logger(symbol):
                            async def logger(message, level='normal'):
                                await log_message(f"  > [{symbol}] {message}", level)

                            return logger

                        await ex_async.close_position_async(exchange, full_symbol, ratio,
                                                            create_logger(full_symbol.split('/')[0]))
                    elif task_type == 'SYNC_SLTP':
                        position: Position = data

                        def create_logger(symbol):
                            async def logger(message, level='normal'):
                                await log_message(f"  > [{symbol}] {message}", level)

                            return logger

                        await sltp_async.set_tp_sl_for_position_async(exchange, position, config_dict,
                                                                      create_logger(position.symbol))

                # 更新进度
                async with self.is_running_lock:
                    if self.current_task_info.get('total', 0) > 0:
                        self.current_task_info['current'] += 1
                        await broadcast_progress(
                            self.current_task_info['current'],
                            self.current_task_info['total'],
                            self.current_task_info['name']
                        )

                TRADE_TASK_QUEUE.task_done()

            except Exception as e:
                await log_message(f"!!! Worker #{worker_id} 任务错误: {e}", "error")
                if not TRADE_TASK_QUEUE.empty():
                    TRADE_TASK_QUEUE.task_done()  # 确保队列不会被阻塞

    async def _dispatch_and_wait(self, task_name: str, tasks: list, task_type: str, config: dict):
        """将一批任务放入队列，并等待它们全部完成。"""
        if not tasks:
            await log_message(f"{task_name}任务列表为空。", "info")
            return

        total_tasks = len(tasks)
        self.current_task_info = {"name": task_name, "total": total_tasks, "current": 0}
        await broadcast_progress(0, total_tasks, task_name)
        await log_message(f"===== {total_tasks} 个{task_name}任务已加入队列 =====", "info")

        for task_data in tasks:
            await TRADE_TASK_QUEUE.put((task_type, task_data, config))

        await TRADE_TASK_QUEUE.join()

    async def _run_batch_job(self, name: str, job_coro, *args, **kwargs):
        """统一的批量任务执行器，负责状态管理和错误处理"""
        async with self.is_running_lock:
            if self.is_running:
                await log_message("一个任务已在运行中。", "warning")
                return {"message": "任务已在运行"}
            self.is_running = True

        self.stop_event.clear()
        await update_status(f"正在准备{name}...", is_running=True)

        try:
            await job_coro(*args, **kwargs)
            if not self.stop_event.is_set():
                await log_message(f"===== 所有{name}任务已处理完毕 =====", "success")
        except Exception as e:
            await log_message(f"!!! {name}任务执行中发生错误: {e}", "error")
        finally:
            async with self.is_running_lock:
                self.is_running = False
                await update_status("准备就绪", is_running=False)
                if not self.stop_event.is_set():
                    await manager.broadcast({"type": "refresh_positions"})

    async def start_trading(self, plan_request: TradePlanRequest):
        return await self._run_batch_job("开仓", self._start_trading_job, plan_request)

    async def _start_trading_job(self, plan_request: TradePlanRequest):
        config_dict = plan_request.model_dump()
        long_plan, short_plan = plan_calculator.calculate_trade_plan(config_dict,
                                                                     config_dict.get('long_custom_weights', {}))

        all_plans = []
        if plan_request.enable_long_trades and long_plan:
            all_plans.extend([{'coin': c, 'value': v, 'side': i18n.ORDER_SIDE_BUY} for c, v in long_plan.items()])
        if plan_request.enable_short_trades and short_plan:
            all_plans.extend([{'coin': c, 'value': v, 'side': i18n.ORDER_SIDE_SELL} for c, v in short_plan.items()])

        await self._dispatch_and_wait("开仓", all_plans, 'SINGLE_ORDER', config_dict)

    async def stop_trading(self):
        async with self.is_running_lock:
            if not self.is_running: return {"message": "没有正在运行的任务"}
            await log_message("...正在发送全局停止信号...", "warning")
            while not TRADE_TASK_QUEUE.empty():
                try:
                    TRADE_TASK_QUEUE.get_nowait(); TRADE_TASK_QUEUE.task_done()
                except asyncio.QueueEmpty:
                    break
            self.stop_event.set()
            self.is_running = False
            await update_status("任务已停止", is_running=False)
        return {"message": "停止信号已发送"}

    async def _run_single_order(self, exchange, plan: dict, config: dict):
        async def async_logger(message: str, level: str = 'normal'):
            await log_message(f"  > [{plan['coin']}] {message}", level)

        try:
            return await ex_async.process_order_with_sl_tp_async(exchange, plan, config, async_logger, self.stop_event)
        except Exception as e:
            await log_message(f"!!! [{plan['coin']}] 任务失败: {e}", "error")
            return False

    async def sync_all_sltp(self, config_request: dict):
        return await self._run_batch_job("校准SL/TP", self._sync_sltp_job, config_request)

    async def _sync_sltp_job(self, config_request: dict):
        try:
            async with get_exchange_for_task() as exchange:
                positions = await ex_async.fetch_positions_with_pnl_async(exchange, config_request.get('leverage', 1))
        except Exception as e:
            await log_message(f"!!! 获取持仓失败: {e}", "error")
            return
        await self._dispatch_and_wait("校准SL/TP", positions, 'SYNC_SLTP', config_request)

    async def execute_rebalance_plan(self, plan: ExecutionPlanRequest):
        return await self._run_batch_job("再平衡", self._execute_rebalance_job, plan)

    async def _execute_rebalance_job(self, plan: ExecutionPlanRequest):
        config_dict = load_settings()
        close_orders = [o for o in plan.orders if o.action == 'CLOSE']
        open_orders = [o for o in plan.orders if o.action == 'OPEN']

        if close_orders:
            close_tasks_data = []
            async with get_exchange_for_task() as exchange:
                all_positions = await ex_async.fetch_positions_with_pnl_async(exchange, config_dict.get('leverage', 1))
                positions_map = {p.symbol: p.full_symbol for p in all_positions}
                for o in close_orders:
                    full_symbol = positions_map.get(o.symbol)
                    if full_symbol:
                        close_tasks_data.append((full_symbol, o.close_ratio))
                    else:
                        await log_message(f"  > [Warning] 无法为 {o.symbol} 找到 full_symbol，跳过平仓。")
            await self._dispatch_and_wait("再平衡-平仓", close_tasks_data, 'CLOSE_ORDER', config_dict)

        if self.stop_event.is_set(): return

        if open_orders:
            open_tasks_data = [{'coin': o.symbol, 'value': o.value_to_trade, 'side': o.side} for o in open_orders]
            await self._dispatch_and_wait("再平衡-开仓", open_tasks_data, 'SINGLE_ORDER', config_dict)


trading_service = TradingService()