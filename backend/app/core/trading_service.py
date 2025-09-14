import asyncio
from ..models.schemas import TradePlanRequest, ExecutionPlanRequest
from ..logic import plan_calculator
from ..core.exchange_manager import get_exchange_for_task
from ..core.websocket_manager import log_message, update_status, manager
from ..config import i18n
from ..config.config import load_settings
from ..logic import exchange_logic_async as ex_async
from ..logic import sl_tp_logic_async as sltp_async


class TradingService:
    def __init__(self):
        self.is_running = False
        self.stop_event = asyncio.Event()

    async def start_trading(self, plan_request: TradePlanRequest):
        if self.is_running:
            await log_message("一个任务已在运行中，请稍后再试。", "warning")
            return {"message": "任务已在运行"}

        self.is_running = True
        self.stop_event.clear()

        asyncio.create_task(self._execute_trade_plan(plan_request))
        return {"message": "交易任务已启动"}

    async def stop_trading(self):
        if not self.is_running:
            return {"message": "没有正在运行的任务"}
        await log_message("...正在发送全局停止信号...", "warning")
        self.stop_event.set()
        await update_status("正在停止...")
        return {"message": "停止信号已发送"}

    async def _execute_trade_plan(self, config: TradePlanRequest):
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

        total_tasks = len(all_plans)
        await log_message(f"===== 准备派发 {total_tasks} 个开仓任务 =====", "info")

        async with get_exchange_for_task() as exchange:
            tasks = [self._run_single_order(exchange, plan, config_dict) for plan in all_plans]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if r is True)
        failed_count = total_tasks - success_count
        await log_message(f"===== 开仓执行完毕 (成功: {success_count}, 失败: {failed_count}) =====", "success")
        await update_status("准备就绪", is_running=False)
        self.is_running = False
        await manager.broadcast({"type": "refresh_positions"})

    async def _run_single_order(self, exchange, plan: dict, config: dict):
        async def async_logger(message: str, level: str = 'normal'):
            await log_message(f"  > [{plan['coin']}] {message}", level)

        if self.stop_event.is_set():
            await async_logger("任务已取消，不再执行。", "warning")
            return False

        try:
            result = await ex_async.process_order_with_sl_tp_async(
                exchange, plan, config, async_logger, self.stop_event
            )
            return result
        except Exception as e:
            await log_message(f"!!! [{plan['coin']}] 任务失败: {e}", "error")
            return False

    async def sync_all_sltp(self, config_request: dict):
        if self.is_running:
            await log_message("一个任务已在运行中，请稍后再试。", "warning")
            return {"message": "任务已在运行"}

        self.is_running = True
        asyncio.create_task(self._execute_sltp_sync(config_request))
        return {"message": "SL/TP校准任务已启动"}

    async def _execute_sltp_sync(self, config: dict):
        await update_status("正在校准SL/TP...", is_running=True)
        await log_message("===== 开始校准所有持仓的SL/TP =====", "info")

        def create_logger(symbol):
            async def logger(message, level='normal'):
                await log_message(f"  > [{symbol}] {message}", level)

            return logger

        try:
            async with get_exchange_for_task() as exchange:
                positions = await ex_async.fetch_positions_with_pnl_async(exchange, config.get('leverage', 1))

                if not positions:
                    await log_message("未找到任何持仓，无需校准。", "info")
                    return

                tasks = [
                    sltp_async.set_tp_sl_for_position_async(exchange, pos, config, create_logger(pos.symbol))
                    for pos in positions
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                success_count = sum(1 for r in results if r is True)
                failed_count = len(positions) - success_count
                await log_message(f"===== SL/TP校准完毕 (成功: {success_count}, 失败: {failed_count}) =====", "success")

        except Exception as e:
            await log_message(f"!!! SL/TP校准过程中发生严重错误: {e}", "error")
        finally:
            self.is_running = False
            await update_status("准备就绪", is_running=False)
            await manager.broadcast({"type": "refresh_positions"})

    async def execute_rebalance_plan(self, plan: ExecutionPlanRequest):
        if self.is_running:
            await log_message("一个任务已在运行中，请稍后再试。", "warning")
            return {"message": "任务已在运行"}

        self.is_running = True
        self.stop_event.clear()

        asyncio.create_task(self._execute_rebalance_plan_async(plan))
        return {"message": "再平衡任务已启动"}

    async def _execute_rebalance_plan_async(self, plan: ExecutionPlanRequest):
        config_dict = load_settings()
        close_orders = [o for o in plan.orders if o.action == 'CLOSE']
        open_orders = [o for o in plan.orders if o.action == 'OPEN']

        await update_status(f"正在执行再平衡...", is_running=True)
        await log_message(f"===== 开始执行再平衡计划 (平仓: {len(close_orders)}, 开仓: {len(open_orders)}) =====",
                          "info")

        try:
            async with get_exchange_for_task() as exchange:
                if close_orders:
                    await log_message(f"--- 正在执行 {len(close_orders)} 个平仓/减仓任务 ---", "info")

                    all_positions = await ex_async.fetch_positions_with_pnl_async(exchange,
                                                                                  config_dict.get('leverage', 1))
                    positions_map = {p.symbol: p.full_symbol for p in all_positions}

                    close_tasks = []
                    for o in close_orders:
                        full_symbol = positions_map.get(o.symbol)
                        if full_symbol:
                            close_tasks.append(
                                ex_async.close_position_async(exchange, full_symbol, o.close_ratio,
                                                              lambda msg, level='normal': log_message(
                                                                  f"  > [{o.symbol}] {msg}", level))
                            )
                        else:
                            await log_message(f"  > [Warning] 无法为 {o.symbol} 找到对应的 full_symbol，跳过平仓。")

                    await asyncio.gather(*close_tasks, return_exceptions=True)
                    await log_message("--- 所有平仓/减仓任务已派发 ---", "info")

                if self.stop_event.is_set():
                    raise InterruptedError("操作被用户取消")

                if open_orders:
                    await log_message(f"--- 正在执行 {len(open_orders)} 个开仓/加仓任务 ---", "info")
                    open_tasks = [
                        self._run_single_order(exchange, {
                            'coin': o.symbol,
                            'value': o.value_to_trade,
                            'side': o.side
                        }, config_dict)
                        for o in open_orders
                    ]
                    await asyncio.gather(*open_tasks, return_exceptions=True)
                    await log_message("--- 所有开仓/加仓任务已派发 ---", "info")

            await log_message("===== 再平衡计划执行完毕 =====", "success")

        except Exception as e:
            await log_message(f"!!! 再平衡执行过程中发生严重错误: {e}", "error")
        finally:
            self.is_running = False
            self.stop_event.clear()
            await update_status("准备就绪", is_running=False)
            await manager.broadcast({"type": "refresh_positions"})


trading_service = TradingService()