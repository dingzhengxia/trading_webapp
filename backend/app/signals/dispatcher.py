# backend/app/signals/dispatcher.py
"""信号统一分发器：一条链完成「网页展示 → 钉钉推送 → 自动开仓」。

重构自原 service._consume_loop 的三段拼接。每批信号（同一次队列排空）按序：

1. store.add            —— 网页信号列表（全量保留，不受任何过滤影响）；
2. 钉钉推送（独立 task） —— notifier 内部做量能门槛过滤后合并推送，
   不阻塞开仓链路，失败只记日志；
3. 自动开仓（逐条）     —— auto_trader 过滤链：开关/方向/策略/周期/确认数/
   冷却/持仓约束，全部通过才调用 TradingService 开仓。

后续新增输出渠道（邮件/TG/声音报警）或全局过滤，只需扩展 dispatch_batch。
"""
import asyncio
import queue
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from ..core.tasks import cancel_task
from . import notifier
from . import runtime
from .auto_trader import SignalAutoTrader
from .signal_store import SignalStore

QUEUE_GET_TIMEOUT = 0.5   # 阻塞取队首的超时（秒）
IDLE_SLEEP = 0.2          # 队列空转轮询间隔（秒）
MAX_BATCH = notifier.MAX_BATCH


class SignalDispatcher:
    """消费 runtime.signal_queue 并按固定顺序分发每批信号。"""

    def __init__(self, store: SignalStore, auto_trader: SignalAutoTrader,
                 queue_obj: Optional["queue.Queue"] = None):
        self._store = store
        self._auto_trader = auto_trader
        self._queue = queue_obj if queue_obj is not None else runtime.signal_queue
        self._task: Optional[asyncio.Task] = None

    # -------------------------------------------------------------- 生命周期
    def start(self) -> None:
        """启动消费循环（幂等）。"""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._consume_loop())
            logger.info("📡 [信号] 分发器消费循环已启动")

    async def stop(self) -> None:
        task, self._task = self._task, None
        await cancel_task(task)
        logger.info("📡 [信号] 分发器消费循环已停止")

    # -------------------------------------------------------------- 消费循环
    async def _consume_loop(self) -> None:
        while True:
            try:
                first = await asyncio.to_thread(self._queue.get, True, QUEUE_GET_TIMEOUT)
            except queue.Empty:
                await asyncio.sleep(IDLE_SLEEP)
                continue
            except asyncio.CancelledError:
                raise
            try:
                await self.dispatch_batch(self._drain_batch(first))
            except asyncio.CancelledError:
                raise
            except Exception as e:  # 单批失败不能杀死消费循环
                logger.error(f"📡 [信号] 分发批次异常: {e}")

    def _drain_batch(self, first: Dict[str, Any]) -> List[Dict[str, Any]]:
        """以队首信号为起点，非阻塞取尽队列中已排队的信号，组成一批。"""
        batch = [first]
        while len(batch) < MAX_BATCH:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return batch

    # -------------------------------------------------------------- 分发
    async def dispatch_batch(self, batch: List[Dict[str, Any]]) -> Dict[str, int]:
        """按「展示 → 推送 → 开仓」顺序处理一批信号，返回动作统计。"""
        if not batch:
            return {'total': 0, 'open': 0, 'skip': 0, 'error': 0}

        # 1. 网页展示：全量入环形缓冲
        for record in batch:
            self._store.add(record)

        # 2. 钉钉推送：独立 task，量能门槛/合并/重试细节都在 notifier 内
        asyncio.create_task(notifier.push_signal_batch(batch))

        # 3. 自动开仓：逐条过滤链
        stats = {'total': len(batch), 'open': 0, 'skip': 0, 'error': 0}
        for record in batch:
            try:
                result = await self._auto_trader.on_signal(record)
            except Exception as e:
                logger.error(f"📡 [信号] 开仓链异常 {record.get('symbol')}: {e}")
                stats['error'] += 1
                continue
            action = str(result.get('action') or 'skip')
            if action in stats:
                stats[action] += 1
            if action != 'skip':
                logger.info(f"📡 [信号] {record.get('symbol')} {record.get('strategy')} -> "
                            f"{action}: {result.get('reason')}")
        return stats
