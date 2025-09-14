import asyncio
from asyncio import Queue
from ..models.schemas import TradePlanRequest, ExecutionPlanRequest, Position
from ..logic import plan_calculator
from ..core.exchange_manager import get_exchange_for_task
from ..core.websocket_manager import log_message, update_status, manager, broadcast_progress
from ..config import i18n
from ..config.config import load_settings
from ..logic import exchange_logic_async as ex_async
from ..logic import sl_tp_logic_async as sltp_async

TRADE_TASK_QUEUE = Queue()
# --- 核心修复：定义并发 worker 的数量 ---
NUM_WORKERS = 5  # 您可以根据服务器性能和API限制调整这个数字，3-5 是一个比较安全的值


# ------------------------------------

class TradingService:
    def __init__(self):
        self.is_running = False
        self.stop_event = asyncio.Event()
        self.worker_tasks = []  # 用于持有所有 worker 协程

    async def start_worker(self):
        """在应用启动时，启动一个并发 worker 池"""
        if not self.worker_tasks:
            self.worker_tasks = [
                asyncio.create_task(self._trade_task_worker(i + 1))
                for i in range(NUM_WORKERS)
            ]
            print(f"{NUM_WORKERS} trading task workers have been started.")

    async def _trade_task_worker(self, worker_id: int):
        await log_message(f"交易任务处理器 #{worker_id} 已启动，等待任务...", "info")
        while True:
            try:
                task_type, data, config_dict = await TRADE_TASK_QUEUE.get()

                if self.stop_event.is_set():
                    await log_message(f"[Worker #{worker_id}] 任务被用户取消，跳过执行。", "warning")
                    TRADE_TASK_QUEUE.task_done()
                    continue

                # 进度更新现在由分发器负责，worker 只执行

                async with get_exchange_for_task() as exchange:
                    if task_type == 'SINGLE_ORDER':
                        plan = data
                        await self._run_single_order(exchange, plan, config_dict)
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

                # 在任务完成后更新进度
                if self.current_task_info.get('total', 0) > 0:
                    self.current_task_info['current'] += 1
                    await broadcast_progress(
                        self.current_task_info['current'],
                        self.current_task_info['total'],
                        self.current_task_info['name']
                    )

                TRADE_TASK_QUEUE.task_done()

                # 速率限制：可以移除或减小，因为并发数已经受控
                # await asyncio.sleep(0.1)

            except Exception as e:
                await log_message(f"!!! Worker #{worker_id} 任务发生严重错误: {e}", "error")
                if not TRADE_TASK_QUEUE.empty():
                    TRADE_TASK_QUEUE.task_done()

    async def _dispatch_tasks(self, task_name: str, tasks: list, task_type: str, config: dict):
        if self.is_running:
            await log_message("一个任务已在运行中。", "warning")
            return {"message": "任务已在运行"}

        if not tasks:
            await log_message(f"{task_name}任务列表为空，无需执行。", "info")
            return {"message": "任务列表为空"}

        self.is_running = True
        self.stop_event.clear()

        total_tasks = len(tasks)
        self.current_task_info = {"name": task_name, "total": total_tasks, "current": 0}
        await broadcast_progress(0, total_tasks, task_name)
        await log_message(f"===== {total_tasks} 个{task_name}任务已加入队列 =====", "info")

        for task_data in tasks:
            await TRADE_TASK_QUEUE.put((task_type, task_data, config))

        asyncio.create_task(self._wait_for_queue_completion(f"{task_name}任务"))
        return {"message": f"{task_name}任务已加入队列"}

    async def _wait_for_queue_completion(self, task_name_for_log: str):
        await TRADE_TASK_QUEUE.join()

        if not self.stop_event.is_set():
            await log_message(f"===== 所有{task_name_for_log}已处理完毕 =====", "success")
        else:
            await log_message(f"===== {task_name_for_log}队列已停止 =====", "warning")

        if TRADE_TASK_QUEUE.empty():
            self.is_running = False
            await update_status("准备就绪", is_running=False)
            await manager.broadcast({"type": "refresh_positions"})

    async def start_trading(self, plan_request: TradePlanRequest):
        config_dict = plan_request.model_dump()
        long_plan, short_plan = plan_calculator.calculate_trade_plan(config_dict,
                                                                     config_dict.get('long_custom_weights', {}))

        all_plans = []
        if plan_request.enable_long_trades and long_plan:
            all_plans.extend([{'coin': c, 'value': v, 'side': i18n.ORDER_SIDE_BUY} for c, v in long_plan.items()])
        if plan_request.enable_short_trades and short_plan:
            all_plans.extend([{'coin': c, 'value': v, 'side': i18n.ORDER_SIDE_SELL} for c, v in short_plan.items()])

        return await self._dispatch_tasks("开仓", all_plans, 'SINGLE_ORDER', config_dict)

    async def stop_trading(self):
        if not self.is_running: return {"message": "没有正在运行的任务"}
        await log_message("...正在发送全局停止信号...", "warning")

        while not TRADE_TASK_QUEUE.empty():
            try:
                TRADE_TASK_QUEUE.get_nowait();
                TRADE_TASK_QUEUE.task_done()
            except asyncio.QueueEmpty:
                break

        self.stop_event.set()
        await update_status("正在停止当前任务...", is_running=False)
        self.is_running = False
        return {"message": "停止信号已发送，队列已清空"}

    async def _run_single_order(self, exchange, plan: dict, config: dict):
        async def async_logger(message: str, level: str = 'normal'):
            await log_message(f"  > [{plan['coin']}] {message}", level)

        try:
            return await ex_async.process_order_with_sl_tp_async(exchange, plan, config, async_logger, self.stop_event)
        except Exception as e:
            await log_message(f"!!! [{plan['coin']}] 任务失败: {e}", "error")
            return False

    async def sync_all_sltp(self, config_request: dict):
        try:
            async with get_exchange_for_task() as exchange:
                positions = await ex_async.fetch_positions_with_pnl_async(exchange, config_request.get('leverage', 1))
        except Exception as e:
            await log_message(f"!!! 准备SL/TP校准时获取持仓失败: {e}", "error")
            return {"message": "获取持仓失败"}

        return await self._dispatch_tasks("校准SL/TP", positions, 'SYNC_SLTP', config_request)

    async def execute_rebalance_plan(self, plan: ExecutionPlanRequest):
        asyncio.create_task(self._execute_rebalance_plan_async(plan))
        return {"message": "再平衡任务已加入队列"}

    async def _execute_rebalance_plan_async(self, plan: ExecutionPlanRequest):
        if self.is_running:
            await log_message("一个任务已在运行中，请等待其完成。", "warning")
            return

        self.is_running = True
        self.stop_event.clear()

        config_dict = load_settings()
        close_orders = [o for o in plan.orders if o.action == 'CLOSE']
        open_orders = [o for o in plan.orders if o.action == 'OPEN']

        try:
            if close_orders:
                close_tasks_data = []
                async with get_exchange_for_task() as exchange:
                    all_positions = await ex_async.fetch_positions_with_pnl_async(exchange,
                                                                                  config_dict.get('leverage', 1))
                    positions_map = {p.symbol: p.full_symbol for p in all_positions}
                    for o in close_orders:
                        full_symbol = positions_map.get(o.symbol)
                        if full_symbol:
                            close_tasks_data.append((full_symbol, o.close_ratio))
                        else:
                            await log_message(f"  > [Warning] 无法为 {o.symbol} 找到 full_symbol，跳过平仓。")

                await self._dispatch_tasks("再平衡-平仓", close_tasks_data, 'CLOSE_ORDER', config_dict)
                await TRADE_TASK_QUEUE.join()

            if self.stop_event.is_set():
                raise InterruptedError("操作被用户取消")

            if open_orders:
                open_tasks_data = [{'coin': o.symbol, 'value': o.value_to_trade, 'side': o.side} for o in open_orders]
                await self._dispatch_tasks("再平衡-开仓", open_tasks_data, 'SINGLE_ORDER', config_dict)
                await TRADE_TASK_QUEUE.join()

            if not self.stop_event.is_set():
                await log_message("===== 再平衡计划执行完毕 =====", "success")

        except Exception as e:
            await log_message(f"!!! 再平衡执行过程中发生错误: {e}", "error")
        finally:
            if TRADE_TASK_QUEUE.empty():
                self.is_running = False
                await update_status("准备就绪", is_running=False)
                await manager.broadcast({"type": "refresh_positions"})


trading_service = TradingService()