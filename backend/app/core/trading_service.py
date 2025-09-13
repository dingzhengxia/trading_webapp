# backend/app/core/trading_service.py
import asyncio
from ..models.schemas import TradePlanRequest
from ..logic import plan_calculator
from ..core.exchange_manager import get_exchange_for_task
from ..core.websocket_manager import log_message, update_status, manager
from ..config import i18n
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

        await log_message("--- [DEBUG] Received Config from Frontend ---", "info")
        await log_message(str(config_dict), "info")

        enable_long = config_dict.get('enable_long_trades')
        enable_short = config_dict.get('enable_short_trades')
        await log_message(f"--- [DEBUG] Long Trades Enabled: {enable_long} ---", "info")
        await log_message(f"--- [DEBUG] Short Trades Enabled: {enable_short} ---", "info")

        long_plan, short_plan = plan_calculator.calculate_trade_plan(config_dict,
                                                                     config_dict.get('long_custom_weights', {}))

        all_plans = []
        if long_plan: all_plans.extend(
            [{'coin': c, 'value': v, 'side': i18n.ORDER_SIDE_BUY} for c, v in long_plan.items()])
        if short_plan: all_plans.extend(
            [{'coin': c, 'value': v, 'side': i18n.ORDER_SIDE_SELL} for c, v in short_plan.items()])

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
                positions = await ex_async.fetch_positions_with_pnl_async(exchange)

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


trading_service = TradingService()