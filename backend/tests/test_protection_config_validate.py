"""仓位保护参数校验：判定周期写错必须 400 拒绝。

背景：黑天鹅判定周期（emergency_timeframe）从 15m 改成 1h 后暴露到前端下拉框。
它是 ATR 计算的时间粒度，一旦传进非法值（'60m' / '60'），ccxt 会直接抛错，
引擎整轮跳过 —— 等于把这层保护静默关掉，所以必须在写库前拦住。
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.protection import _validate
from app.protection.config import DEFAULT_CONFIG
from app.protection.risk_model import V2_DEFAULTS


@pytest.mark.parametrize(
    'key', ['v2_timeframe', 'emergency_timeframe', 'hard_stop_timeframe'])
def test_unknown_timeframe_is_rejected(key):
    with pytest.raises(HTTPException) as exc:
        _validate({key: '60m'})
    assert exc.value.status_code == 400
    assert key in exc.value.detail


@pytest.mark.parametrize('value', ['15m', '1h', '4h', '1d'])
def test_allowed_timeframes_pass(value):
    _validate({'emergency_timeframe': value})


def test_emergency_timeframe_defaults_to_1h():
    """15m 的 3×ATR 只有 ~1%，一根普通阴线就构成「黑天鹅」——默认必须是 1h。"""
    assert DEFAULT_CONFIG['position_protection']['emergency_timeframe'] == '1h'
    assert V2_DEFAULTS['emergency_timeframe'] == '1h'
