# backend/app/signals/config_store.py
"""策略参数配置（signal_config.json）的持久化存储。

优先级：SQLite `signal_state.strategy_config` > 仓库内 signal_config.json。

- 首次启动（DB 无记录）用文件内容播种，之后一律以 DB 为准；
- 这样 `deploy.sh` 重建镜像不会把线上调过的参数回滚成镜像里的旧值；
- 需要回到仓库默认值时调 `reset_signal_config()`（保留文件本身不动）。
"""
import copy
import json
import os
from typing import Any, Dict

from loguru import logger

from ..core import database
from ..core.paths import PROJECT_ROOT

SIGNAL_CONFIG_FILE = os.path.join(str(PROJECT_ROOT), 'signal_config.json')

_STATE_TABLE = 'signal_state'
_STATE_KEY = 'strategy_config'

# signal_config.json 缺失/损坏时的兜底配置（策略全部关闭，保证可运行）
FALLBACK_SIGNAL_CONFIG: Dict[str, Any] = {
    'config_version': 0,
    'app_settings': {'exchange': 'binance', 'default_market_type': 'swap', 'check_interval_minutes': 5},
    'market_settings': {
        'timeframes': ['1h', '4h'],
        'static_symbols': ['BTC', 'ETH', 'BNB'],
        'dynamic_scan': {'enabled': False, 'top_n_for_signals': 100, 'exclude_symbols': []},
    },
    'strategy_params': {},
}


def _read_file() -> Dict[str, Any]:
    """读取仓库内 signal_config.json；缺失或损坏时返回兜底配置。"""
    try:
        with open(SIGNAL_CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get('strategy_params'):
            return data
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"signal_config.json 加载失败，使用兜底配置: {e}")
    return copy.deepcopy(FALLBACK_SIGNAL_CONFIG)


def _read_db() -> Dict[str, Any] | None:
    try:
        stored = database.get_value(_STATE_TABLE, _STATE_KEY, None)
    except Exception as e:  # DB 不可用时不阻塞扫描，退回文件
        logger.warning(f"读取策略配置失败，退回 signal_config.json: {e}")
        return None
    return stored if isinstance(stored, dict) and stored.get('strategy_params') else None


def load_signal_config() -> Dict[str, Any]:
    """加载策略配置：DB 优先，DB 为空时用文件播种。"""
    stored = _read_db()
    if stored is not None:
        return stored
    config = _read_file()
    if config.get('strategy_params'):  # 兜底配置（策略全关）不值得写进 DB
        save_signal_config(config)
        logger.info("策略配置首次播种到数据库（signal_state.strategy_config）。")
    return config


def save_signal_config(config: Dict[str, Any]) -> bool:
    """整份写入数据库；失败返回 False（调用方自行决定是否报错）。"""
    if not isinstance(config, dict) or not config.get('strategy_params'):
        raise ValueError("策略配置必须是非空字典且包含 strategy_params")
    try:
        database.set_value(_STATE_TABLE, _STATE_KEY, config)
        return True
    except Exception as e:
        logger.error(f"保存策略配置失败: {e}")
        return False


def reset_signal_config() -> Dict[str, Any]:
    """丢弃数据库内容，用仓库内文件重新播种。"""
    config = _read_file()
    save_signal_config(config)
    return config


def config_source() -> str:
    """当前生效来源：'db'（数据库）或 'file'（尚未播种，读的是仓库文件）。"""
    return 'db' if _read_db() is not None else 'file'


def deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并：dict 逐键合并，其它类型（含 list）整体替换。不修改入参。"""
    result = copy.deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def validate_strategy_patch(patch: Any, current: Dict[str, Any]) -> None:
    """校验局部更新内容；非法时抛 ValueError（由 API 转 400）。"""
    if not isinstance(patch, dict) or not patch:
        raise ValueError("请求体必须是非空字典。")
    unknown_roots = [k for k in patch if k not in ('strategy_params',)]
    if unknown_roots:
        raise ValueError(f"只支持更新 strategy_params，不支持: {', '.join(sorted(unknown_roots))}")

    params = patch.get('strategy_params')
    if not isinstance(params, dict) or not params:
        raise ValueError("strategy_params 必须是非空字典。")

    known = current.get('strategy_params') or {}
    unknown = [k for k in params if k not in known]
    if unknown:
        raise ValueError(f"未知策略: {', '.join(sorted(unknown))}")

    for name, value in params.items():
        origin = known.get(name)
        if isinstance(origin, list) or isinstance(value, list):
            if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
                raise ValueError(f"{name} 是多参数组，必须传对象数组。")
        elif not isinstance(value, dict):
            raise ValueError(f"{name} 必须是对象。")


def update_signal_config(patch: Dict[str, Any]) -> Dict[str, Any]:
    """校验 + 深合并 + 落库，返回合并后的完整配置。"""
    current = load_signal_config()
    validate_strategy_patch(patch, current)
    merged = deep_merge(current, patch)
    if not save_signal_config(merged):
        raise RuntimeError("保存策略配置失败")
    return merged
