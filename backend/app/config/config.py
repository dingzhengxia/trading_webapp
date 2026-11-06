# backend/app/config/config.py (完整代码)
import copy
import os
from pathlib import Path
from typing import List, Dict, Any
from threading import RLock

# --- 路径定义 ---
if os.environ.get("IS_DOCKER"):
    _PROJECT_ROOT = Path('/app')
else:
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# 旧 JSON 文件路径：仅作为一次性迁移到 SQLite 的来源保留（迁移后文件不动）
USER_SETTINGS_FILE = _PROJECT_ROOT / 'user_settings.json'
COIN_LISTS_FILE = _PROJECT_ROOT / 'coin_lists.json'
# --- 路径定义结束 ---

from ..core import database  # noqa: E402  SQLite 存储层（任务 A）

# 注入迁移源路径（与本项目根一致），并初始化数据库（幂等：建表 + 一次性迁移）
database.USER_SETTINGS_FILE = USER_SETTINGS_FILE
database.COIN_LISTS_FILE = COIN_LISTS_FILE
database.init_db()

STABLECOIN_PREFERENCE = ['USDC', 'USDT']

DEFAULT_CONFIG: Dict[str, Any] = {
    'api_key': '', 'api_secret': '', 'use_testnet': True,
    'app_access_key': 'CHANGE_THIS_IN_USER_SETTINGS.JSON',
    'enable_long_trades': True,
    'enable_short_trades': True,
    'total_long_position_value': 1000.0,
    'total_short_position_value': 500.0,
    'leverage': 20,
    'enable_long_sl_tp': True,
    'long_stop_loss_percentage': 50.0,
    'long_take_profit_percentage': 100.0,
    'enable_short_sl_tp': True,
    'short_stop_loss_percentage': 80.0,
    'short_take_profit_percentage': 150.0,

    # --- 新增：移动止盈止损配置 ---
    'enable_long_trailing_stop': False,
    'long_trailing_stop_callback_rate': 1.0,
    'enable_short_trailing_stop': False,
    'short_trailing_stop_callback_rate': 1.0,
    # ---------------------------

    'open_maker_retries': 5,
    'open_order_fill_timeout_seconds': 60,
    'close_maker_retries': 3,
    'close_order_fill_timeout_seconds': 12,
    'rebalance_method': 'multi_factor_weakest',
    'rebalance_top_n': 10,
    'rebalance_min_volume_usd': 5000000.0,
    'rebalance_abs_momentum_days': 21,
    'rebalance_rel_strength_days': 21,
    'rebalance_short_ratio_max': 0.70,
    'rebalance_short_ratio_min': 0.35,
    'enable_proxy': False,
    'proxy_url': 'http://127.0.0.1:7890',
    'long_coin_list': [],
    'short_coin_list': [],
    'long_custom_weights': {},
    'rebalance_volume_ma_days': 20,
    'rebalance_volume_spike_ratio': 3.0,
    'rebalance_benchmark_coin': ['BTC'],

    'enable_rebalance_filters': True,
    'rebalance_rsi_period': 14,
    'rebalance_rsi_threshold': 25.0,
    'rebalance_short_term_momentum_days': 3,
    'rebalance_short_term_momentum_threshold': 15.0,
    'rebalance_bollinger_period': 20,
    'rebalance_bollinger_std_dev': 2,
    'rebalance_bollinger_width_spike_ratio': 2.0,

    # --- 信号扫描 / 自动开仓配置（Phase 2，全部默认关闭，启动不触达交易所）---
    'signal_scan_enabled': False,
    'signal_scan_interval_seconds': 300,
    'signal_scan_static_symbols': ['BTC', 'ETH', 'BNB'],
    'signal_scan_top_n': 100,
    'signal_scan_timeframes': ['1h', '4h'],
    'signal_ticker_cache_seconds': 30,
    'signal_ohlcv_cache_seconds': 30,
    'signal_auto_trade_enabled': False,
    'signal_auto_trade_directions': ['long', 'short'],
    'signal_auto_trade_strategies': [
        'ema_cross', 'ma_breakout', 'kdj_cross', 'level_breakout',
        'rsi_divergence', 'trend_channel_breakout', 'ob_luxalgo', 'ob_fluxcharts',
    ],
    'signal_auto_trade_timeframes': ['1h', '4h'],
    'signal_auto_trade_confirmation_window_seconds': 300,
    'signal_auto_trade_confirmations': 1,
    'signal_auto_trade_cooldown_seconds': 900,
    'signal_auto_trade_max_positions': 5,
    'signal_auto_trade_value_usd': 100.0,

    # 手动交易页持久化预设（选中币种/每行动作与价值/默认价值），随 settings 存入 SQLite
    'manual_trade_preset': {},

    # 仓位保护（Phase 3，自 monitor 并入）：完整的默认值见 app/protection/engine.py 的
    # DEFAULT_CONFIG；这里只保留空字典以允许该配置项写入 settings 表。
    # 默认 enabled=False，前端「仓位保护」页打开开关后才会启动引擎。
    'position_protection': {},
}

# 内存中全局变量
AVAILABLE_COINS: List[str] = []
AVAILABLE_LONG_COINS: List[str] = []
AVAILABLE_SHORT_COINS: List[str] = []

_cached_settings: Dict[str, Any] | None = None
_settings_lock = RLock()
_coin_list_lock = RLock()  # 为币种池读写添加专用的锁


def load_coin_lists() -> None:
    """从 SQLite coin_pools 表加载币种池到内存中的全局变量。"""
    global AVAILABLE_COINS, AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS
    with _coin_list_lock:
        pools = database.get_all('coin_pools')
        AVAILABLE_COINS = list(pools.get('coins_pool', []))
        AVAILABLE_LONG_COINS = list(pools.get('long_coins_pool', []))
        AVAILABLE_SHORT_COINS = list(pools.get('short_coins_pool', []))
        print(
            f"--- [INFO] Loaded coin pools from SQLite. Total: {len(AVAILABLE_COINS)}, "
            f"Long: {len(AVAILABLE_LONG_COINS)}, Short: {len(AVAILABLE_SHORT_COINS)} ---")


def load_settings() -> Dict[str, Any]:
    """
    加载用户配置（SQLite settings 表），不存在时使用默认值。
    """
    global _cached_settings
    with _settings_lock:
        if _cached_settings is not None:
            return _cached_settings.copy()

        config = DEFAULT_CONFIG.copy()
        stored = database.get_all('settings')
        config.update(stored)

        config['api_key'] = os.environ.get('BINANCE_API_KEY', config.get('api_key', ''))
        config['api_secret'] = os.environ.get('BINANCE_API_SECRET', config.get('api_secret', ''))

        _cached_settings = config
        # 深拷贝：嵌套的 list/dict 不能与缓存共享引用，否则调用方原地修改会污染全局配置
        return copy.deepcopy(_cached_settings)


def save_settings(current_config: Dict[str, Any]) -> bool:
    """
    保存用户配置到 SQLite settings 表。
    """
    global _cached_settings
    try:
        settings_to_write = {key: value for key, value in current_config.items() if key in DEFAULT_CONFIG}

        # 单事务批量写入：避免逐键 commit 导致“杠杆已改、止损未改”的半套配置
        database.set_many('settings', settings_to_write)

        print("--- [INFO] User settings successfully saved to SQLite. ---")

        with _settings_lock:
            _cached_settings = None
        return True
    except Exception as e:
        print(f"--- [ERROR] Failed to save user settings: {e} ---")
        return False


def add_coin_to_pool(coin_symbol: str) -> List[str]:
    """
    添加新币种到总池中，并保存到 SQLite。
    """
    global AVAILABLE_COINS
    if not coin_symbol or not isinstance(coin_symbol, str):
        raise ValueError("Coin symbol cannot be empty.")

    symbol_upper = coin_symbol.strip().upper()
    if not symbol_upper:
        raise ValueError("Coin symbol cannot be empty.")

    with _coin_list_lock:
        current_pool = set(AVAILABLE_COINS) | set(database.get_value('coin_pools', 'coins_pool', []))
        if symbol_upper in current_pool:
            raise ValueError(f"'{symbol_upper}' already exists in the coin pool.")

        current_pool.add(symbol_upper)
        new_pool = sorted(list(current_pool))
        database.set_value('coin_pools', 'coins_pool', new_pool)

        AVAILABLE_COINS = new_pool
        print(f"--- [INFO] Added '{symbol_upper}' to coin pool. Total now: {len(AVAILABLE_COINS)} ---")
        return AVAILABLE_COINS


def _normalize_coin_pool(pool: List[str]) -> List[str]:
    """去除空白、统一大写、去重并排序，过滤非法值。"""
    normalized = set()
    for coin in pool or []:
        if not isinstance(coin, str):
            continue
        symbol = coin.strip().upper()
        if symbol:
            normalized.add(symbol)
    return sorted(normalized)


def save_coin_pools(long_coins_pool: List[str], short_coins_pool: List[str]) -> Dict[str, List[str]]:
    """线程安全地保存做多/做空币种池到 SQLite，并同步刷新内存中的全局变量。

    这是 update-coin-pools API 的唯一写入口，避免绕过锁直接写存储导致
    内存与存储不一致、与其他任务写操作竞争。
    """
    global AVAILABLE_COINS, AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS

    long_pool = _normalize_coin_pool(long_coins_pool)
    short_pool = _normalize_coin_pool(short_coins_pool)

    with _coin_list_lock:
        database.set_value('coin_pools', 'coins_pool', list(AVAILABLE_COINS))
        database.set_value('coin_pools', 'long_coins_pool', long_pool)
        database.set_value('coin_pools', 'short_coins_pool', short_pool)

        AVAILABLE_LONG_COINS = long_pool
        AVAILABLE_SHORT_COINS = short_pool
        print(
            f"--- [INFO] Coin pools saved successfully. Long: {len(AVAILABLE_LONG_COINS)}, Short: {len(AVAILABLE_SHORT_COINS)} ---")

    return {
        "coins_pool": list(AVAILABLE_COINS),
        "long_coins_pool": list(long_pool),
        "short_coins_pool": list(short_pool),
    }


# 首次加载
load_coin_lists()
