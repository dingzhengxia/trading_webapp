# backend/app/api/reports.py
"""周期报告 API：状态查询、配置热更新、立即生成。"""
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException
from loguru import logger

from ..config import config as app_config
from ..core.security import verify_api_key
from ..reports.engine import REPORT_INTERVALS
from ..reports.service import get_reports_status, trigger_report
from .validators import validate_numbers

router = APIRouter(prefix="/api/reports", tags=["Reports"],
                   dependencies=[Depends(verify_api_key)])

# 数值范围（下限, 上限）——报告参数只影响统计口径，仍需防止明显非法值
NUMERIC_RANGES: Dict[str, tuple] = {
    'top_n_by_volume': (5, 500),
    'top_n_gainers': (1, 50),
    'top_n_volume_ratio': (1, 50),
    'min_consecutive_candles': (1, 20),
    'volume_ma_period': (2, 200),
    'rsi_period': (2, 100),
    'rsi_overbought': (50, 100),
    'rsi_oversold': (0, 50),
}

MAX_REPORTS = 5


def _validate_number(key: str, raw: Any) -> int:
    """报告参数都是正整数，越界/非数字直接 400。"""
    conf = {key: raw}
    validate_numbers(conf, NUMERIC_RANGES, default_int=True)
    return conf[key]


def _validate_report(conf: Any) -> Dict[str, Any]:
    if not isinstance(conf, dict):
        raise HTTPException(status_code=400, detail="每份报告配置必须是对象。")

    name = str(conf.get('report_name') or '').strip()
    if not name or len(name) > 40:
        raise HTTPException(status_code=400, detail="report_name 不能为空且不超过 40 个字符。")

    enabled = conf.get('enabled', False)
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=400, detail="enabled 必须是布尔值。")

    interval = str(conf.get('run_interval') or '4h')
    if interval not in REPORT_INTERVALS:
        raise HTTPException(
            status_code=400,
            detail=f"run_interval 必须是 {', '.join(REPORT_INTERVALS)} 之一。")

    result: Dict[str, Any] = {
        'report_name': name,
        'enabled': enabled,
        'run_interval': interval,
    }
    for key in ('top_n_by_volume', 'top_n_gainers', 'top_n_volume_ratio',
                'min_consecutive_candles', 'volume_ma_period'):
        if key in conf:
            result[key] = _validate_number(key, conf[key])

    sentiment_raw = conf.get('market_sentiment')
    if isinstance(sentiment_raw, dict):
        sentiment: Dict[str, Any] = {'enabled': bool(sentiment_raw.get('enabled', False))}
        for key in ('rsi_period', 'rsi_overbought', 'rsi_oversold'):
            if key in sentiment_raw:
                sentiment[key] = _validate_number(key, sentiment_raw[key])
        result['market_sentiment'] = sentiment
    return result


@router.get("")
def reports_status() -> Dict[str, Any]:
    """周期报告状态：每份报告的开关/周期/上次与下次运行时间 + 最近一份内容。"""
    return get_reports_status()


@router.post("/config")
async def update_reports_config(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """增量更新周期报告配置（整表替换 reports 列表；可同时切换钉钉推送开关）。"""
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="配置内容必须是对象。")

    settings = app_config.load_settings()
    updated: Dict[str, Any] = {}

    if 'reports' in payload:
        reports_raw = payload['reports']
        if not isinstance(reports_raw, list):
            raise HTTPException(status_code=400, detail="reports 必须是数组。")
        if not 1 <= len(reports_raw) <= MAX_REPORTS:
            raise HTTPException(status_code=400, detail=f"报告数量必须在 1~{MAX_REPORTS} 之间。")
        validated: List[Dict[str, Any]] = [_validate_report(item) for item in reports_raw]
        names = [item['report_name'] for item in validated]
        if len(set(names)) != len(names):
            raise HTTPException(status_code=400, detail="report_name 不能重复。")

        # 未显式提供的字段沿用当前同名配置，避免前端只改开关时丢掉周期/阈值
        current_by_name = {
            str(item.get('report_name')): item
            for item in (settings.get('periodic_reports') or [])
            if isinstance(item, dict)
        }
        merged_reports = []
        for item in validated:
            base = dict(current_by_name.get(item['report_name']) or {})
            base.update(item)
            if 'market_sentiment' in item:
                base['market_sentiment'] = {**(current_by_name.get(item['report_name'], {}).get('market_sentiment') or {}),
                                            **item['market_sentiment']}
            merged_reports.append(base)
        updated['periodic_reports'] = merged_reports

    if 'dingtalk_enabled' in payload:
        if not isinstance(payload['dingtalk_enabled'], bool):
            raise HTTPException(status_code=400, detail="dingtalk_enabled 必须是布尔值。")
        updated['dingtalk_enabled'] = payload['dingtalk_enabled']

    if not updated:
        raise HTTPException(status_code=400, detail="没有可更新的配置项。")

    settings.update(updated)
    if not app_config.save_settings(settings):
        raise HTTPException(status_code=500, detail="保存周期报告配置失败，请查看服务器日志。")

    logger.info(f"📰 周期报告配置已更新：{len(updated.get('periodic_reports') or [])} 份报告")
    return {"message": "周期报告配置已保存", **get_reports_status()}


@router.post("/run")
async def run_report_now(payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    """立即生成指定报告（不传 report_name 时用第一份启用的报告）。"""
    name = None
    if isinstance(payload, dict):
        raw_name = payload.get('report_name')
        if raw_name is not None:
            name = str(raw_name).strip()
    result = trigger_report(name)
    if not result.get('submitted'):
        raise HTTPException(status_code=400, detail=result.get('reason') or '无法提交报告任务')
    return {"message": f"已开始生成「{result['report_name']}」，完成后会出现在本页与网页日志中。"}
