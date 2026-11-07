# backend/app/reports/service.py
"""周期报告的调度与状态管理。

设计：
- supervisor 每 30 秒检查一次配置（SQLite settings.periodic_reports），
  对 `enabled=True` 且到达周期的报告生成一份；
- 上次运行时间/最近一份报告内容持久化到 SQLite（signal_state 表），进程重启不丢；
- 生成过程与钉钉推送都在后台任务里，API 立即返回；
- 同一时刻只跑一份报告（asyncio.Lock），避免限流器被打爆。
"""
import asyncio
import time
from typing import Any, Dict, List, Optional

from loguru import logger

from ..config.config import load_settings
from ..core.database import get_value, set_value
from ..core.tasks import cancel_tasks
from ..core.websocket_manager import log_message
from . import dingtalk
from .engine import generate_report, interval_minutes

_STATE_TABLE = 'signal_state'

_supervisor_task: Optional[asyncio.Task] = None
_report_lock: Optional[asyncio.Lock] = None
_running_names: set = set()
last_results: Dict[str, Dict[str, Any]] = {}
last_errors: Dict[str, str] = {}
_trigger_task: Optional[asyncio.Task] = None


def _lock() -> asyncio.Lock:
    global _report_lock
    if _report_lock is None:
        _report_lock = asyncio.Lock()
    return _report_lock


def _state_key(name: str) -> str:
    return f"report_last:{name}"


def load_last_result(name: str) -> Optional[Dict[str, Any]]:
    """从 SQLite 读取某份报告的最近一次结果（内存命中优先）。"""
    if name in last_results:
        return last_results[name]
    try:
        cached = get_value(_STATE_TABLE, _state_key(name), None)
    except Exception as exc:  # noqa: BLE001 - 读取失败降级为无历史
        logger.debug(f"读取报告历史失败: {exc}")
        return None
    if isinstance(cached, dict):
        last_results[name] = cached
        return cached
    return None


def _save_last_result(name: str, payload: Dict[str, Any]) -> None:
    last_results[name] = payload
    try:
        set_value(_STATE_TABLE, _state_key(name), payload)
    except Exception as exc:  # noqa: BLE001 - 持久化失败不影响本次报告
        logger.warning(f"保存报告历史失败（本次结果仍在内存）: {exc}")


def get_reports_config() -> List[Dict[str, Any]]:
    settings = load_settings()
    reports = settings.get('periodic_reports')
    if not isinstance(reports, list):
        return []
    return [dict(item) for item in reports if isinstance(item, dict)]


async def run_report(report_conf: Dict[str, Any], trigger: str = 'schedule') -> Dict[str, Any]:
    """生成并发布一份报告（含 UI 日志 + 可选钉钉推送），返回结果字典。"""
    name = str(report_conf.get('report_name') or '周期报告')
    async with _lock():
        _running_names.add(name)
        started = time.monotonic()
        try:
            await log_message(f"📰 开始生成「{name}」（触发方式：{trigger}）", "info")
            result = await generate_report(report_conf)
            result['trigger'] = trigger
            _save_last_result(name, result)
            last_errors.pop(name, None)

            elapsed = time.monotonic() - started
            await log_message(
                f"📰 「{name}」生成完成：{result['scanned']}/{result['symbols_total']} 个合约，"
                f"耗时 {elapsed:.1f}s", "success")

            if bool(load_settings().get('dingtalk_enabled', False)):
                if dingtalk.is_configured():
                    sent = await dingtalk.send_markdown(result['title'], result['markdown'])
                    await log_message(
                        f"📰 「{name}」钉钉推送{'成功' if sent else '失败'}", "info" if sent else "warning")
                else:
                    logger.debug('未配置 DINGTALK_WEBHOOK_URL，跳过钉钉推送')
            return result
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 单份报告失败不影响调度器
            last_errors[name] = f"{type(exc).__name__}: {exc}"
            logger.error(f"周期报告「{name}」生成失败: {last_errors[name]}")
            await log_message(f"📰 「{name}」生成失败：{exc}", "error")
            raise
        finally:
            _running_names.discard(name)


async def _supervisor() -> None:
    """按配置周期触发报告。"""
    while True:
        try:
            reports = get_reports_config()
            now = time.time()
            for conf in reports:
                if not conf.get('enabled'):
                    continue
                name = str(conf.get('report_name') or '周期报告')
                if name in _running_names:
                    continue
                last = load_last_result(name)
                last_run = float(last.get('generated_at') or 0) if last else 0.0
                period = interval_minutes(conf.get('run_interval')) * 60
                if last_run and now - last_run < period - 30:
                    continue
                try:
                    await run_report(conf, trigger='schedule')
                except Exception:  # noqa: BLE001 - 已在 run_report 内记录
                    continue
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - supervisor 不能退出
            logger.error(f"周期报告 supervisor 异常: {exc}")
        await asyncio.sleep(30)


async def startup_reports() -> None:
    """lifespan 启动：注册 supervisor（无启用报告时不触达交易所）。"""
    global _supervisor_task
    if _supervisor_task is not None and not _supervisor_task.done():
        return
    enabled = [r for r in get_reports_config() if r.get('enabled')]
    _supervisor_task = asyncio.create_task(_supervisor(), name="reports-supervisor")
    logger.info(f"📰 周期报告 supervisor 就绪（启用 {len(enabled)} 份，默认关闭）")


async def shutdown_reports() -> None:
    """lifespan 关闭：停止 supervisor 与正在跑的报告任务。"""
    global _supervisor_task, _trigger_task
    await cancel_tasks((_trigger_task, _supervisor_task))
    _trigger_task = None
    _supervisor_task = None


def trigger_report(name: Optional[str] = None) -> Dict[str, Any]:
    """立即生成（后台任务），返回是否已提交。"""
    global _trigger_task
    reports = get_reports_config()
    if not reports:
        return {'submitted': False, 'reason': '未配置任何周期报告'}
    target = None
    if name:
        target = next((r for r in reports if str(r.get('report_name')) == name), None)
    else:
        target = next((r for r in reports if r.get('enabled')), reports[0])
    if target is None:
        return {'submitted': False, 'reason': f'未找到报告：{name}'}

    report_name = str(target.get('report_name') or '周期报告')
    if report_name in _running_names:
        return {'submitted': False, 'reason': f'「{report_name}」正在生成中'}
    if _trigger_task is not None and not _trigger_task.done():
        return {'submitted': False, 'reason': '已有报告任务在运行'}

    async def _runner():
        try:
            await run_report(target, trigger='manual')
        except Exception:  # noqa: BLE001 - 已在 run_report 内记录
            pass

    _trigger_task = asyncio.create_task(_runner(), name=f"report-manual-{report_name}")
    return {'submitted': True, 'report_name': report_name}


def get_reports_status() -> Dict[str, Any]:
    """报告页所需状态：每份报告的配置、上次/下次运行时间、最近内容。"""
    reports = get_reports_config()
    rows: List[Dict[str, Any]] = []
    now = time.time()
    for conf in reports:
        name = str(conf.get('report_name') or '周期报告')
        last = load_last_result(name)
        last_run = float(last.get('generated_at') or 0) if last else None
        period = interval_minutes(conf.get('run_interval')) * 60
        rows.append({
            'report_name': name,
            'enabled': bool(conf.get('enabled')),
            'run_interval': str(conf.get('run_interval') or '4h'),
            'top_n_by_volume': int(conf.get('top_n_by_volume') or 100),
            'top_n_gainers': int(conf.get('top_n_gainers') or 10),
            'top_n_volume_ratio': int(conf.get('top_n_volume_ratio') or 10),
            'min_consecutive_candles': int(conf.get('min_consecutive_candles') or 2),
            'volume_ma_period': int(conf.get('volume_ma_period') or 20),
            'market_sentiment': conf.get('market_sentiment') or {},
            'last_run': last_run,
            'next_run': (last_run + period) if (last_run and conf.get('enabled')) else None,
            'due_in_seconds': max(0, int(last_run + period - now)) if last_run else 0,
            'running': name in _running_names,
            'last_error': last_errors.get(name),
            'title': (last or {}).get('title'),
            'scanned': (last or {}).get('scanned'),
        })

    return {
        'reports': rows,
        'dingtalk_configured': dingtalk.is_configured(),
        'dingtalk_enabled': bool(load_settings().get('dingtalk_enabled', False)),
        'running': bool(_running_names),
        'latest': last_results,
    }
