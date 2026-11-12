# backend/app/api/signals.py
"""信号扫描 / 自动开仓 API（MERGE_PLAN §6，前缀 /api/signals，鉴权同其它交易接口）。

约定：
- POST /api/signals/scan 允许手动扫描（即使 signal_scan_enabled=False 也可手动触发一次，
  契约 §8 端到端"二选一"中选择了允许手动扫描）；已有扫描在跑时返回 409；
- POST /api/signals/config 只接受 signal_* 字段的部分字典，Pydantic 校验非法值返回 400。
"""
import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from ..core.security import verify_api_key
from ..models.schemas import SignalConfigUpdate
from ..signals import config_store
from ..signals import service as signal_service

router = APIRouter(prefix="/api/signals", tags=["Signals"], dependencies=[Depends(verify_api_key)])


def _signal_config_view() -> Dict[str, Any]:
    from ..config.config import load_settings
    settings = load_settings()
    return {k: v for k, v in settings.items() if str(k).startswith('signal_')}


def _parse_signal_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Pydantic 校验 signal_* 配置；非法值 -> 400（而非默认的 422）。"""
    if not isinstance(payload, dict) or not payload:
        raise HTTPException(status_code=400, detail="请求体必须是非空的 signal_* 配置字典。")
    unknown = [k for k in payload if not str(k).startswith('signal_')]
    if unknown:
        raise HTTPException(status_code=400, detail=f"不支持的配置项: {', '.join(sorted(unknown))}")
    try:
        model = SignalConfigUpdate(**payload)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"配置校验失败: {e.errors()[0].get('msg')}")
    return model.model_dump(exclude_none=True)


def _validate_enum_fields(update: Dict[str, Any]) -> None:
    from ..models.schemas import SIGNAL_STRATEGIES, SIGNAL_TIMEFRAMES
    for field, allowed in (('signal_scan_timeframes', SIGNAL_TIMEFRAMES),
                           ('signal_auto_trade_timeframes', SIGNAL_TIMEFRAMES),
                           ('signal_auto_trade_strategies', SIGNAL_STRATEGIES)):
        values = update.get(field)
        if values is None:
            continue
        invalid = [v for v in values if v not in allowed]
        if invalid:
            raise HTTPException(status_code=400,
                                detail=f"{field} 含非法值: {', '.join(map(str, invalid))}")


def _normalize_static_symbols(update: Dict[str, Any]) -> None:
    """静态币种规范化：去空白、转大写、只取 base 币（SOL/USDT -> SOL）、去重。

    非法字符直接 400，避免脏值进到扫描循环里变成无效请求。
    """
    values = update.get('signal_scan_static_symbols')
    if values is None:
        return
    normalized: list[str] = []
    for raw in values:
        base = str(raw).strip().upper().split('/')[0].split(':')[0]
        if not base:
            continue
        if not base.replace('-', '').isalnum():
            raise HTTPException(status_code=400, detail=f"静态币种含非法字符: {raw}")
        if base not in normalized:
            normalized.append(base)
    update['signal_scan_static_symbols'] = normalized


@router.get("")
async def get_signals() -> Dict[str, Any]:
    """扫描状态 + 最近信号 + signal_* 配置 + 钉钉推送状态。"""
    from ..config.config import load_settings
    from ..reports import dingtalk

    scanner: Optional[signal_service.SignalScanner] = signal_service.scanner
    if scanner is None:
        status = signal_service.store.snapshot()
        status['enabled'] = False  # 扫描循环从未启动
    else:
        status = scanner.status()
    settings = load_settings()
    return {
        "status": status,
        "signals": signal_service.store.recent(200),
        "config": _signal_config_view(),
        "strategy": {
            "config": config_store.load_signal_config(),
            "source": config_store.config_source(),
        },
        "push": {
            "dingtalk_configured": dingtalk.is_configured(),
            "dingtalk_enabled": bool(settings.get('dingtalk_enabled', False)),
            "signal_dingtalk_enabled": bool(settings.get('signal_dingtalk_enabled', True)),
            "signal_push_volume_multiplier": float(
                settings.get('signal_push_volume_multiplier', 2.0) or 0),
            "static_symbols": list(settings.get('signal_scan_static_symbols') or []),
        },
    }


@router.post("/scan")
async def trigger_scan() -> Dict[str, str]:
    """手动触发一轮扫描（后台执行；即使扫描开关关闭也允许手动扫描）。"""
    scanner = signal_service._get_scanner()
    if scanner.is_scanning():
        raise HTTPException(status_code=409, detail="已有扫描在进行中，请稍后再试。")
    asyncio.get_running_loop().create_task(scanner.scan_once())
    return {"message": "扫描任务已提交"}


@router.post("/config")
async def update_signal_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    """部分更新 signal_* 配置：校验 -> 保存 -> 热应用。"""
    from ..config.config import load_settings, save_settings
    update = _parse_signal_config(payload)
    _validate_enum_fields(update)
    _normalize_static_symbols(update)

    settings = load_settings()
    settings.update(update)
    if not save_settings(settings):
        raise HTTPException(status_code=500, detail="保存配置失败。")
    # 热应用（返回值以本次合并结果为准，避免依赖持久化层回读时序）
    await signal_service.apply_signal_config(settings)
    return {"config": {k: v for k, v in settings.items() if str(k).startswith('signal_')}}


@router.post("/strategy-config")
async def update_strategy_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    """更新策略参数（signal_params.*，深合并后落库）。

    - 请求体 `{"strategy_params": {...}}`：局部更新，只允许已存在的策略名；
    - 请求体 `{"reset": true}`：丢弃数据库内容，用仓库内 signal_config.json 重新播种；
    - 落库后下一轮扫描自动生效（扫描器每轮重新读取配置），无需重启。
    """
    if not isinstance(payload, dict) or len(payload) != 1:
        raise HTTPException(status_code=400, detail='请求体必须为 {"strategy_params": {...}} 或 {"reset": true}。')

    if payload.get("reset") is True:
        config = config_store.reset_signal_config()
    else:
        try:
            config = config_store.update_signal_config(payload)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))

    return {"strategy": {"config": config, "source": config_store.config_source()},
            "message": "已保存到数据库，下一轮扫描生效"}


@router.post("/auto-trade")
async def toggle_auto_trade(payload: Dict[str, Any]) -> Dict[str, Any]:
    """自动开仓快捷开关（非法请求体 400）。"""
    from ..config.config import load_settings, save_settings
    if not isinstance(payload, dict) or set(payload) != {"enabled"} \
            or not isinstance(payload["enabled"], bool):
        raise HTTPException(status_code=400, detail='请求体必须为 {"enabled": true|false}。')
    enabled = payload["enabled"]
    settings = load_settings()
    settings['signal_auto_trade_enabled'] = enabled
    if not save_settings(settings):
        raise HTTPException(status_code=500, detail="保存配置失败。")
    await signal_service.apply_signal_config(settings)
    return {"enabled": enabled}


@router.post("/clear")
async def clear_signals() -> Dict[str, Any]:
    signal_service.store.clear()
    return {"cleared": True, "remaining": 0}
