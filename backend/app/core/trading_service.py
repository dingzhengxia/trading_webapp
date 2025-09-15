# backend/app/core/trading_service.py (新增的完整文件)
import asyncio
from fastapi import HTTPException
from typing import Dict, Any, List, Tuple

from ..config.config import load_settings
from ..logic.plan_calculator import calculate_trade_plan
from ..logic.exchange_logic_async import process_order_with_sl_tp_async, close_position_async, \
    InterruptedError, fetch_positions_with_pnl_async
from ..logic.sl_tp_logic_async import set_tp_sl_for_position_async, cleanup_orphan_sltp_orders_async
from ..models.schemas import ExecutionPlanRequest, Position
from .websocket_manager import log_message, update_status, broadcast_progress
from .exchange_manager import get_exchange_for_task


class TradingService:
    def __init__(self):
        self._is_running = False
        self._current_task: asyncio.Task = None
        self._stop_event = asyncio.Event()
        self._worker_task: asyncio.Task = None

    async def start_worker(self):
        """启动一个常驻的worker，用于监控和执行任务"""
        if self._worker_task and not self._worker_task.done():
            return
        self._worker_task = asyncio.create_task(self._task_executor())
        await log_message("Trading Service worker has started.", "info")

    async def _task_executor(self):
        """这是一个简化的执行器，实际应用中可能需要一个任务队列"""
        # 在这个应用场景中，由于任务是单一的长时间运行，我们主要用它来管理任务生命周期
        # 在更复杂的系统中，这里会是一个 while True 循环，从队列中获取任务
        pass

    def is_running(self) -> bool:
        return self._is_running

    async def _execute_and_log_task(self, task_name: str, task_coro):
        """统一的带日志的任务执行器"""
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
            # 确保在HTTP响应中也返回错误
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

        # 将 Pydantic 模型转换为字典以便传递
        config = plan_request.model_dump()

        # --- 诊断日志 1：检查传入 start_trading 的配置 ---
        print("\n--- [BACKEND DEBUG 1] Config received by start_trading ---")
        print(f"    'enable_long_trades': {config.get('enable_long_trades')}")
        print(f"    'enable_short_trades': {config.get('enable_short_trades')}")
        print("----------------------------------------------------\n")
        # ---------------------------------------------------------

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
            # 等待任务响应取消信号并结束
            await asyncio.wait_for(self._current_task, timeout=30)
        except asyncio.TimeoutError:
            self._current_task.cancel()
            await log_message("任务在30秒内未正常停止，已强制取消。", "error")
        except Exception:
            # 忽略其他可能在任务被取消时抛出的异常
            pass
        finally:
            self._is_running = False
            self._current_task = None
            await update_status("交易已停止", is_running=False)

        return {"message": "Trading task stopped."}

    async def _trading_loop_task(self, config: Dict[str, Any]):
        """核心的交易执行循环"""
        await update_status("交易任务初始化...", is_running=True)

        # --- 诊断日志 2：检查传入 _trading_loop_task 的配置 ---
        print("\n--- [BACKEND DEBUG 2] Config inside _trading_loop_task ---")
        print(f"    'enable_long_trades': {config.get('enable_long_trades')}")
        print(f"    'enable_short_trades': {config.get('enable_short_trades')}")
        print("-----------------------------------------------------\n")
        # ----------------------------------------------------------

        long_plan, short_plan = calculate_trade_plan(config, config.get('long_custom_weights', {}))

        # --- 诊断日志 3：检查 plan_calculator 的输出 ---
        print("\n--- [BACKEND DEBUG 3] Plan calculated ---")
        print(f"    Long Plan: {long_plan}")
        print(f"    Short Plan: {short_plan}")
        print("-------------------------------------\n")
        # ----------------------------------------------

        order_plan = []
        if config.get('enable_long_trades'):
            order_plan.extend([{'coin': c, 'value': v, 'side': 'buy'} for c, v in long_plan.items()])
        if config.get('enable_short_trades'):
            order_plan.extend([{'coin': c, 'value': v, 'side': 'sell'} for c, v in short_plan.items()])

        if not order_plan:
            await log_message("没有计算出有效的交易计划，任务结束。", "warning")
            return

        total_tasks = len(order_plan)
        await log_message(f"交易计划生成完毕，共需处理 {total_tasks} 个订单。", "info")

        async with get_exchange_for_task() as exchange:
            for i, plan_item in enumerate(order_plan):
                if self._stop_event.is_set():
                    raise InterruptedError("Trading was stopped by user.")

                await broadcast_progress(i, total_tasks, f"正在处理 {plan_item['coin']} ({plan_item['side']})")

                # 这里是关键：将 log_message 作为 async_logger 传递下去
                await process_order_with_sl_tp_async(exchange, plan_item, config, log_message, self._stop_event)

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
        """处理通用任务，如批量平仓"""
        total = len(tasks_data)
        if total == 0:
            await log_message("任务列表为空，无需执行。", "info")
            return

        await update_status("正在执行批量操作...", is_running=True)

        async with get_exchange_for_task() as exchange:
            for i, task_item in enumerate(tasks_data):
                if self._stop_event.is_set():
                    raise InterruptedError("操作被用户停止。")

                symbol, ratio = task_item
                await broadcast_progress(i, total, f"处理: {symbol}")

                if task_type == 'CLOSE_ORDER':
                    await close_position_async(exchange, symbol, ratio, log_message)

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
        """同步所有持仓的止盈止损"""
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
        """执行一个再平衡计划"""
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
        """执行再平衡计划的核心逻辑"""
        config = load_settings()

        # 分离平仓和开仓任务
        close_orders = [o for o in plan.orders if o.action == 'CLOSE']
        open_orders = [o for o in plan.orders if o.action == 'OPEN']

        total_steps = len(close_orders) + len(open_orders)
        current_step = 0

        await update_status("开始执行再平衡计划...", is_running=True)

        async with get_exchange_for_task() as exchange:
            # 1. 执行所有平仓操作
            if close_orders:
                await log_message(f"开始执行 {len(close_orders)} 个平仓任务...", "info")
                for order_item in close_orders:
                    current_step += 1
                    if self._stop_event.is_set(): raise InterruptedError("再平衡任务被取消")
                    await broadcast_progress(current_step, total_steps, f"平仓: {order_item.symbol}")
                    await close_position_async(exchange, order_item.symbol, order_item.close_ratio, log_message)

            # 2. 执行所有开仓操作
            if open_orders:
                await log_message(f"开始执行 {len(open_orders)} 个开仓任务...", "info")
                for order_item in open_orders:
                    current_step += 1
                    if self._stop_event.is_set(): raise InterruptedError("再平衡任务被取消")
                    await broadcast_progress(current_step, total_steps, f"开仓: {order_item.symbol}")

                    order_plan_item = {
                        'coin': order_item.symbol.split('/')[0],
                        'value': order_item.value_to_trade,
                        'side': order_item.side
                    }
                    await process_order_with_sl_tp_async(exchange, order_plan_item, config, log_message,
                                                         self._stop_event)

        await broadcast_progress(total_steps, total_steps, "再平衡计划执行完毕")
        await log_message("✅ 所有再平衡操作已成功执行完毕。", "success")


# 创建一个全局单例
trading_service = TradingService()