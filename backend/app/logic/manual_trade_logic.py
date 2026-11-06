# backend/app/logic/manual_trade_logic.py
"""手动做多 / 做空 / 反手的纯逻辑（禁止 IO / 禁止 import ccxt）。

TradingService.manual_trade() 负责启动后台任务并创建 exchange；本模块只做
参数校验与任务构建，便于离线单元测试。
"""
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

MANUAL_ACTIONS = ('long', 'short', 'reverse')
MAX_MANUAL_ITEMS = 100
ACTION_TO_SIDE = {'long': 'buy', 'short': 'sell'}
REVERSE_SIDE = {'long': 'sell', 'short': 'buy'}


@dataclass(frozen=True)
class ManualTradeTask:
    coin: str                      # 基础币种，大写
    action: str                    # long / short / reverse
    side: Optional[str]            # buy / sell（反手为平仓后的反向 side）
    value: Optional[float]         # 目标 USD 名义价值
    close_full_symbols: Tuple[str, ...] = ()  # 反手需要先全平的交易对
    skip_reason: Optional[str] = None         # 无持仓/混合持仓/价值无效等，worker 只记日志


def _get_field(item: Any, name: str, default: Any = None) -> Any:
    """同时兼容 dict 与 Pydantic 模型 / dataclass 对象。"""
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def normalize_action(action: Any) -> str:
    """把 'LONG' / ManualTradeAction.LONG 等统一成小写字符串。"""
    if isinstance(action, str):
        return action.strip().lower()
    value = getattr(action, 'value', None)
    if isinstance(value, str):
        return value.strip().lower()
    return ''


def _normalize_symbol(value: Any) -> str:
    if not isinstance(value, str):
        return ''
    symbol = value.strip().upper()
    if '/' in symbol:
        symbol = symbol.split('/')[0].strip()
    return symbol


def _to_positive_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result) or result <= 0:
        return None
    return result


def _position_full_symbol(position: Any) -> str:
    full_symbol = _get_field(position, 'full_symbol')
    if isinstance(full_symbol, str) and full_symbol.strip():
        return full_symbol.strip()
    symbol = _normalize_symbol(_get_field(position, 'symbol'))
    return symbol


def _position_base_coin(position: Any) -> str:
    full_symbol = _position_full_symbol(position)
    if '/' in full_symbol:
        return full_symbol.split('/')[0].upper()
    return full_symbol


def _position_side(position: Any) -> str:
    return str(_get_field(position, 'side') or '').strip().lower()


def _position_notional(position: Any) -> float:
    notional = _to_positive_float(_get_field(position, 'notional'))
    return notional or 0.0


def validate_manual_items(items: Sequence[Any]) -> List[Dict[str, Any]]:
    """校验手动交易参数并返回规范化后的 list[dict]。

    空列表、超过上限、重复币种、非法 action、value <= 0 → ValueError，
    由 API 层转换成 HTTP 400。
    """
    if items is None:
        raise ValueError("手动交易列表不能为空。")
    if not isinstance(items, (list, tuple)):
        raise ValueError("手动交易列表格式不正确。")
    if len(items) == 0:
        raise ValueError("手动交易列表不能为空。")
    if len(items) > MAX_MANUAL_ITEMS:
        raise ValueError(f"单次手动交易币种数量不能超过 {MAX_MANUAL_ITEMS} 个。")

    symbols: List[str] = []
    for index, item in enumerate(items):
        symbol = _normalize_symbol(_get_field(item, 'symbol'))
        if not symbol:
            raise ValueError(f"第 {index + 1} 项缺少有效的币种代码。")
        symbols.append(symbol)

    duplicates = sorted({symbol for symbol in symbols if symbols.count(symbol) > 1})
    if duplicates:
        raise ValueError(f"存在重复币种: {', '.join(duplicates)}")

    normalized: List[Dict[str, Any]] = []
    for index, item in enumerate(items):
        symbol = symbols[index]
        raw_action = _get_field(item, 'action')
        action = normalize_action(raw_action)
        if action not in MANUAL_ACTIONS:
            raise ValueError(f"{symbol} 的动作 '{raw_action}' 非法，仅支持 long/short/reverse。")

        raw_value = _get_field(item, 'value')
        if raw_value is None:
            value = None
        else:
            value = _to_positive_float(raw_value)
            if value is None:
                raise ValueError(f"{symbol} 的下单价值必须大于 0。")

        normalized.append({'symbol': symbol, 'action': action, 'value': value})

    return normalized


def _config_default_value(action: str, config: Dict[str, Any], long_count: int,
                          short_count: int) -> Optional[float]:
    if action == 'long':
        total = _to_positive_float(config.get('total_long_position_value'))
        return total / long_count if total and long_count > 0 else None
    if action == 'short':
        total = _to_positive_float(config.get('total_short_position_value'))
        return total / short_count if total and short_count > 0 else None
    return None


def build_manual_trade_tasks(items: Sequence[Any],
                             positions: Sequence[Any],
                             config: Dict[str, Any],
                             default_value: Optional[float] = None) -> List[ManualTradeTask]:
    """把 API 请求 + 当前持仓快照转换为可执行任务列表（纯函数）。"""
    normalized_items = validate_manual_items(items)
    config = config or {}
    positions = list(positions or [])
    valid_default_value = _to_positive_float(default_value)

    long_count = sum(1 for item in normalized_items if item['action'] == 'long')
    short_count = sum(1 for item in normalized_items if item['action'] == 'short')

    tasks: List[ManualTradeTask] = []
    for item in normalized_items:
        coin = item['symbol']
        action = item['action']
        explicit_value = item['value']

        if action == 'reverse':
            matches = [p for p in positions if _position_base_coin(p) == coin]
            if not matches:
                tasks.append(ManualTradeTask(coin, action, None, None, (), "无持仓，无法反手"))
                continue

            sides = {_position_side(p) for p in matches}
            if 'long' in sides and 'short' in sides:
                tasks.append(ManualTradeTask(coin, action, None, None, (), "多空持仓并存，无法反手"))
                continue

            side = REVERSE_SIDE['long'] if 'long' in sides else REVERSE_SIDE['short']
            close_full_symbols = tuple(dict.fromkeys(
                full_symbol for full_symbol in (_position_full_symbol(p) for p in matches) if full_symbol
            ))

            if explicit_value is not None:
                value: Optional[float] = explicit_value
            elif valid_default_value is not None:
                value = valid_default_value
            else:
                notional_sum = sum(_position_notional(p) for p in matches)
                value = notional_sum if notional_sum > 0 else None

            if value is None or value <= 0:
                tasks.append(ManualTradeTask(coin, action, side, None, close_full_symbols, "下单价值无效"))
                continue

            tasks.append(ManualTradeTask(coin, action, side, float(value), close_full_symbols))
        else:
            side = ACTION_TO_SIDE[action]
            if explicit_value is not None:
                value = explicit_value
            elif valid_default_value is not None:
                value = valid_default_value
            else:
                value = _config_default_value(action, config, long_count, short_count)

            if value is None or value <= 0:
                tasks.append(ManualTradeTask(coin, action, side, None, (), "下单价值无效"))
                continue

            tasks.append(ManualTradeTask(coin, action, side, float(value), ()))

    return tasks
