# backend/app/core/tasks.py
"""asyncio 后台任务的取消与回收。

各 service 的 shutdown / restart 路径都需要「取消 → 等它退出 → 吞掉取消异常」，
原先在四个模块里各写了一份 try/except，统一收敛到这里。
"""
import asyncio
from typing import Iterable, Optional


async def cancel_task(task: Optional[asyncio.Task]) -> None:
    """取消任务并等待其退出；已结束或为 None 时直接返回（幂等）。"""
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):  # 取消与任务自身异常都不向调用方抛出
        pass


async def cancel_tasks(tasks: Iterable[Optional[asyncio.Task]]) -> None:
    """依次取消一组任务。"""
    for task in tasks:
        await cancel_task(task)
