# backend/app/api/validators.py
"""API 层的数值校验。

设置、仓位保护、周期报告三个接口原先各写了一份「范围检查 + 类型转换」的循环，
规则一致（bool 要显式排除、越界一律 400、整数字段要拒绝小数），这里合并为一处。

范围表格式：(下限, 上限) 或 (下限, 上限, 是否整数)；
调用方也可以用 default_int 给整张表指定默认类型。
"""
from typing import Any, Dict, Tuple

from fastapi import HTTPException

NumericSpec = Tuple[float, float] | Tuple[float, float, bool]


def _coerce(key: str, raw: Any, is_int: bool) -> float:
    try:
        if isinstance(raw, bool):  # bool 是 int 子类，必须显式排除
            raise ValueError
        number = float(raw)
        if is_int and number != int(number):
            raise ValueError
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"配置项 {key} 必须是有效数字。")
    return number


def validate_numbers(conf: Dict[str, Any],
                     ranges: Dict[str, NumericSpec],
                     default_int: bool = False) -> None:
    """就地校验并规范化 conf 中出现在 ranges 里的字段，非法值抛 400。"""
    for key, spec in ranges.items():
        if key not in conf:
            continue
        low, high = spec[0], spec[1]
        is_int = bool(spec[2]) if len(spec) > 2 else default_int
        number = _coerce(key, conf[key], is_int)
        if not (low <= number <= high):
            raise HTTPException(
                status_code=400, detail=f"配置项 {key} 超出允许范围 [{low}, {high}]。")
        conf[key] = int(number) if is_int else number
