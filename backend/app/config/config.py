# backend/app/config/config.py (修改版)
import json
import os
from pathlib import Path
from typing import List, Dict, Any
from threading import RLock

# --- 路径定义 ---
if os.environ.get("IS_DOCKER"):
    _PROJECT_ROOT = Path('/app')
else:
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

USER_SETTINGS_FILE = _PROJECT_ROOT / 'user_settings.json'
COIN_LISTS_FILE = _PROJECT_ROOT / 'coin_lists.json'
# --- 路径定义结束 ---

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
    'open_maker_retries': 5,
    'open_order_fill_timeout_seconds': 60,
    'close_maker_retries': 3,
    'close_order_fill_timeout_seconds': 12,
    'rebalance_method': 'multi_factor_weakness',
    'rebalance_top_n': 10,
    'rebalance_min_volume_usd': 5000000.0,
    'rebalance_abs_momentum_days': 21,
    'rebalance_rel_strength_days': 21,
    'rebalance_foam_days': 21,
    'enable_proxy': False,
    'proxy_url': 'http://127.0.0.1:7890',
    'long_coin_list': [],
    'short_coin_list': [],
    'long_custom_weights': {},
    # --- 新增配置项 ---
    'rebalance_volume_ma_days': 20,  # 计算成交量均线的天数
    'rebalance_volume_spike_ratio': 3.0,  # 成交量放大过滤倍数
}

# 内存中全局变量
AVAILABLE_COINS: List[str] = []
AVAILABLE_LONG_COINS: List[str] = []
AVAILABLE_SHORT_COINS: List[str] = []

_cached_settings: Dict[str, Any] | None = None
_settings_lock = RLock()
_coin_list_lock = RLock() # 为币种列表文件添加专用的锁


def load_coin_lists() -> None:
    """加载 coin_lists.json 文件到内存中的全局变量。"""
    global AVAILABLE_COINS, AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS
    with _coin_list_lock:
        if not COIN_LISTS_FILE.exists():
            print(f"--- [WARNING] {COIN_LISTS_FILE} not found. Creating a new one.")
            # 如果文件不存在，创建一个空的结构
            with open(COIN_LISTS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"coins_pool": [], "long_coins_pool": [], "short_coins_pool": []}, f, indent=4)
            AVAILABLE_COINS, AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS = [], [], []
            return

        try:
            with open(COIN_LISTS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                AVAILABLE_COINS = data.get('coins_pool', [])
                AVAILABLE_LONG_COINS = data.get('long_coins_pool', [])
                AVAILABLE_SHORT_COINS = data.get('short_coins_pool', [])
            print(
                f"--- [INFO] Loaded coin lists from '{COIN_LISTS_FILE}'. Total: {len(AVAILABLE_COINS)}, Long: {len(AVAILABLE_LONG_COINS)}, Short: {len(AVAILABLE_SHORT_COINS)} ---")
        except json.JSONDecodeError as e:
            print(f"--- [ERROR] Failed to decode JSON from {COIN_LISTS_FILE}: {e} ---")


def load_settings() -> Dict[str, Any]:
    """
    加载用户配置，如果不存在则使用默认值。
    """
    global _cached_settings
    with _settings_lock:
        if _cached_settings is not None:
            return _cached_settings.copy()

        config = DEFAULT_CONFIG.copy()
        if USER_SETTINGS_FILE.exists():
            try:
                with open(USER_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    user_settings = json.load(f)
                    config.update(user_settings)
            except json.JSONDecodeError as e:
                print(f"--- [ERROR] Failed to load {USER_SETTINGS_FILE}: {e}. Using default settings. ---")

        config['api_key'] = os.environ.get('BINANCE_API_KEY', config.get('api_key', ''))
        config['api_secret'] = os.environ.get('BINANCE_API_SECRET', config.get('api_secret', ''))

        _cached_settings = config
        print(f"--- [DEBUG] Settings loaded and cached. Leverage={_cached_settings.get('leverage')} ---")
        return _cached_settings.copy()


def save_settings(current_config: Dict[str, Any]) -> bool:
    """
    保存用户配置到文件。
    """
    global _cached_settings
    try:
        settings_to_write = {key: value for key, value in current_config.items() if key in DEFAULT_CONFIG}

        with open(USER_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings_to_write, f, indent=4, ensure_ascii=False)

        print(f"--- [INFO] User settings successfully saved to '{USER_SETTINGS_FILE}'. ---")

        with _settings_lock:
            _cached_settings = None
        return True
    except Exception as e:
        print(f"--- [ERROR] Failed to save user settings: {e} ---")
        return False


# --- 新增函数 ---
def add_coin_to_pool(coin_symbol: str) -> List[str]:
    """
    添加新币种到总池中，并保存到文件。
    """
    global AVAILABLE_COINS
    if not coin_symbol or not isinstance(coin_symbol, str):
        raise ValueError("Coin symbol cannot be empty.")

    symbol_upper = coin_symbol.strip().upper()
    if not symbol_upper:
        raise ValueError("Coin symbol cannot be empty.")

    with _coin_list_lock:
        # 重新从文件读取以获取最新状态
        try:
            with open(COIN_LISTS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {"coins_pool": [], "long_coins_pool": [], "short_coins_pool": []}

        current_pool = set(data.get('coins_pool', []))
        if symbol_upper in current_pool:
            raise ValueError(f"'{symbol_upper}' already exists in the coin pool.")

        current_pool.add(symbol_upper)
        data['coins_pool'] = sorted(list(current_pool))

        with open(COIN_LISTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        # 更新内存中的全局变量
        AVAILABLE_COINS = data['coins_pool']
        print(f"--- [INFO] Added '{symbol_upper}' to coin pool. Total now: {len(AVAILABLE_COINS)} ---")
        return AVAILABLE_COINS
# --- 修改结束 ---


# 首次加载
load_coin_lists()