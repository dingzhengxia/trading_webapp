import asyncio
from asyncio import Queue
from ..models.schemas import TradePlanRequest, ExecutionPlanRequest
from ..logic import plan_calculator
from ..core.exchange_manager import get_exchange_for_task
from ..core.websocket_manager import log_message, update_status, manager
from ..config import i18n
from ..config.config import load_settings
from ..logic import exchange_logic_async as ex_async
from ..logic import sl_tp_logic_async as sltp_async

# 全局交易任务队列
TRADE_TASK_QUEUE = Queue()


class TradingService:
    def __init__(self):
        self.is_running = False
        self.stop_event = asyncio.Event()
        self.worker_task = None

    async def start_worker(self):
        """在应用启动时，启动唯一的 worker 任务来处理队列"""
        if self.worker_task is None or self.worker_task.done():
            self.worker_task = asyncio.create_task(self._trade_task_worker())
            print("Trading task worker has been started.")

    async def _trade_task_worker(self):
        """
        一个长期运行的 worker，以可控的速率从队列中获取并处理交易任务。
        """
        await log_message("交易任务处理器已启动，等待任务...", "info")
        while True:
            try:
                task_type, data, config_dict = await TRADE_TASK_QUEUE.get()

                if self.stop_event.is_set():
                    await log_message(f"任务 '{task_type}' 被用户取消，跳过执行。", "warning")
                    TRADE_TASK_QUEUE.task_done()
                    continue

                await update_status(f"正在处理 {task_type} 任务...", is_running=True)

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
                        position = data

                        def create_logger(symbol):
                            async def logger(message, level='normal'):
                                await log_message(f"  > [{symbol}] {message}", level)

                            return logger

                        await sltp_async.set_tp_sl_for_position_async(exchange, position, config_dict,
                                                                      create_logger(position.symbol))

                TRADE_TASK_QUEUE.task_done()

                # 速率限制：每完成一个任务后等待
                await asyncio.sleep(0.5)

            except Exception as e:
                await log_message(f"!!! Worker 任务发生严重错误: {e}", "error")
                # 即使出错也继续处理下一个任务
                if not TRADE_TASK_QUEUE.empty():
                    TRADE_TASK_QUEUE.task_done()

    async def start_trading(self, plan_request: TradePlanRequest):
        if self.is_running:
            await log_message("一个任务已在运行中，请稍后再试。", "warning")
            return {"message": "任务已在运行"}

        self.is_running = True
        self.stop_event.clear()

        asyncio.create_task(self._queue_trade_plan(plan_request))
        return {"message": "交易任务已加入队列"}

    async def stop_trading(self):
        if not self.is_running:
            return {"message": "没有正在运行的任务"}
        await log_message("...正在发送全局停止信号...", "warning")

        # 清空队列中未开始的任务
        while not TRADE_TASK_QUEUE.empty():
            TRADE_TASK_QUEUE.get_nowait()
            TRADE_TASK_QUEUE.task_done()

        self.stop_event.set()
        await update_status("正在停止当前任务...")
        self.is_running = False  # 立即更新状态
        return {"message": "停止信号已发送，队列已清空"}

    async def _queue_trade_plan(self, config: TradePlanRequest):
        await update_status("正在计算交易计划...", is_running=True)
        config_dict = config.model_dump()

        long_plan, short_plan = plan_calculator.calculate_trade_plan(config_dict,
                                                                     config_dict.get('long_custom_weights', {}))

        all_plans = []
        if config.enable_long_trades and long_plan:
            all_plans.extend([{'coin': c, 'value': v, 'side': i18n.ORDER_SIDE_BUY} for c, v in long_plan.items()])
        if config.enable_short_trades and short_plan:
            all_plans.extend([{'coin': c, 'value': v, 'side': i18n.ORDER_SIDE_SELL} for c, v in short_plan.items()])

        if not all_plans:
            await log_message("未生成任何有效交易计划。", "info")
            await update_status("准备就绪", is_running=False)
            self.is_running = False
            return

        await log_message(f"===== {len(all_plans)} 个开仓任务已加入队列 =====", "info")
        for plan in all_plans:
            await TRADE_TASK_QUEUE.put(('SINGLE_ORDER', plan, config_dict))

        await TRADE_TASK_QUEUE.join()

        if not self.stop_event.is_set():
            await log_message("===== 所有开仓任务已处理完毕 =====", "success")
            await update_status("准备就绪", is_running=False)
            self.is_running = False
            await manager.broadcast({"type": "refresh_positions"})
        else:
            await log_message("===== 任务队列已停止 =====", "warning")

    async def _run_single_order(self, exchange, plan: dict, config: dict):
        async def async_logger(message: str, level: str = 'normal'):
            await log_message(f"  > [{plan['coin']}] {message}", level)

        if self.stop_event.is_set():
            await async_logger("任务已取消，不再执行。", "warning")
            return False

        try:
            return await ex_async.process_order_with_sl_tp_async(
                exchange, plan, config, async_logger, self.stop_event
            )
        except Exception as e:
            await log_message(f"!!! [{plan['coin']}] 任务失败: {e}", "error")
            return False

    async def sync_all_sltp(self, config_request: dict):
        if self.is_running:
            await log_message("一个任务已在运行中，请稍后再试。", "warning")
            return {"message": "任务已在运行"}

        self.is_running = True
        self.stop_event.clear()
        asyncio.create_task(self._queue_sltp_sync(config_request))
        return {"message": "SL/TP校准任务已加入队列"}

    async def _queue_sltp_sync(self, config: dict):
        await update_status("正在准备SL/TP校准...", is_running=True)
        await log_message("===== 开始准备所有持仓的SL/TP校准任务 =====", "info")

        try:
            async with get_exchange_for_task() as exchange:
                positions = await ex_async.fetch_positions_with_pnl_async(exchange, config.get('leverage', 1))
                if not positions:
                    await log_message("未找到任何持仓，无需校准。", "info")
                else:
                    await log_message(f"===== {len(positions)} 个SL/TP校准任务已加入队列 =====", "info")
                    for pos in positions:
                        await TRADE_TASK_QUEUE.put(('SYNC_SLTP', pos, config))

            await TRADE_TASK_QUEUE.join()

            if not self.stop_event.is_set():
                await log_message("===== 所有SL/TP校准任务已处理完毕 =====", "success")
                await update_status("准备就绪", is_running=False)
                self.is_running = False
                await manager.broadcast({"type": "refresh_positions"})
            else:
                await log_message("===== 任务队列已停止 =====", "warning")

        except Exception as e:
            await log_message(f"!!! 准备SL/TP校准时发生严重错误: {e}", "error")
            await update_status("准备就绪", is_running=False)
            self.is_running = False

    async def execute_rebalance_plan(self, plan: ExecutionPlanRequest):
        if self.is_running:
            await log_message("一个任务已在运行中，请稍后再试。", "warning")
            return {"message": "任务已在运行"}

        self.is_running = True
        self.stop_event.clear()

        asyncio.create_task(self._queue_rebalance_plan(plan))
        return {"message": "再平衡任务已加入队列"}

    async def _queue_rebalance_plan(self, plan: ExecutionPlanRequest):
        config_dict = load_settings()
        close_orders = [o for o in plan.orders if o.action == 'CLOSE']
        open_orders = [o for o in plan.orders if o.action == 'OPEN']

        await update_status(f"正在准备再平衡...", is_running=True)
        await log_message(f"===== {len(close_orders) + len(open_orders)} 个再平衡任务已加入队列 =====", "info")

        try:
            async with get_exchange_for_task() as exchange:
                all_positions = await ex_async.fetch_positions_with_pnl_async(exchange, config_dict.get('leverage', 1))
                positions_map = {p.symbol: p.full_symbol for p in all_positions}

                for o in close_orders:
                    full_symbol = positions_map.get(o.symbol)
                    if full_symbol:
                        await TRADE_TASK_QUEUE.put(('CLOSE_ORDER', (full_symbol, o.close_ratio), config_dict))
                    else:
                        await log_message(f"  > [Warning] 无法为 {o.symbol} 找到对应的 full_symbol，跳过平仓。")

            # 等待所有平仓任务完成后再开始开仓
            await TRADE_TASK_QUEUE.join()

            if self.stop_event.is_set():
                raise InterruptedError("操作被用户取消")

            for o in open_orders:
                plan_item = {'coin': o.symbol, 'value': o.value_to_trade, 'side': o.side}
                await TRADE_TASK_QUEUE.put(('SINGLE_ORDER', plan_item, config_dict))

            await TRADE_TASK_QUEUE.join()

            if not self.stop_event.is_set():
                await log_message("===== 所有再平衡任务已处理完毕 =====", "success")
                await update_status("准备就绪", is_running=False)
                self.is_running = False
                await manager.broadcast({"type": "refresh_positions"})
            else:
                await log_message("===== 任务队列已停止 =====", "warning")

        except Exception as e:
            await log_message(f"!!! 准备再平衡时发生严重错误: {e}", "error")
            await update_status("准备就绪", is_running=False)
            self.is_running = False


trading_service = TradingService()