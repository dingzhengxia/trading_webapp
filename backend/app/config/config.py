import json
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple

# --- 路径定义 ---
if os.environ.get("IS_DOCKER"):
    _PROJECT_ROOT = Path('/app')
else:
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

USER_SETTINGS_FILE = _PROJECT_ROOT / 'user_settings.json'
COIN_LISTS_FILE = _PROJECT_ROOT / 'coin_lists.json'
# --- 路径定义结束 ---

STABLECOIN_PREFERENCE = ['USDC', 'USDT']

DEFAULT_CONFIG = {
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
    # 新增默认字段
    'long_coin_list': [],
    'short_coin_list': [],
    'long_coins_selected_pool': [],
    'short_coins_selected_pool': []
}

# 内存中全局变量，用于缓存币种列表
AVAILABLE_COINS: List[str] = []
AVAILABLE_LONG_COINS: List[str] = []
AVAILABLE_SHORT_COINS: List[str] = []


def load_coin_lists() -> None:
    """加载 coin_lists.json 文件到内存中的全局变量。"""
    global AVAILABLE_COINS, AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS
    try:
        with open(COIN_LISTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            AVAILABLE_COINS = data.get('coins_pool', [])
            AVAILABLE_LONG_COINS = data.get('long_coins_pool', [])
            AVAILABLE_SHORT_COINS = data.get('short_coins_pool', [])
        print(
            f"--- [INFO] Loaded coin lists from '{COIN_LISTS_FILE}'. Total: {len(AVAILABLE_COINS)}, Long: {len(AVAILABLE_LONG_COINS)}, Short: {len(AVAILABLE_SHORT_COINS)} ---")
    except FileNotFoundError:
        print(f"--- [ERROR] {COIN_LISTS_FILE} not found. Please create it. ---")
    except json.JSONDecodeError as e:
        print(f"--- [ERROR] Failed to decode JSON from {COIN_LISTS_FILE}: {e} ---")


def load_settings() -> Dict[str, Any]:
    """加载用户配置，如果不存在则使用默认值。"""
    config = DEFAULT_CONFIG.copy()

    # 加载 user_settings.json
    if USER_SETTINGS_FILE.exists():
        with open(USER_SETTINGS_FILE, 'r', encoding='utf-8') as f:
            try:
                user_settings = json.load(f)
                config.update(user_settings)
            except json.JSONDecodeError as e:
                print(f"--- [ERROR] Failed to load {USER_SETTINGS_FILE}: {e}. Using default settings. ---")

    # 确保新增的选中池字段存在，如果不存在则初始化为空列表
    if 'long_coins_selected_pool' not in config:
        config['long_coins_selected_pool'] = []
    if 'short_coins_selected_pool' not in config:
        config['short_coins_selected_pool'] = []

    # 如果用户没有配置 long/short_coin_list，则使用备选池作为默认值
    if not config.get('long_coin_list') and AVAILABLE_LONG_COINS:
        print(
            f"--- [INFO] User settings missing 'long_coin_list', using default pool ({len(AVAILABLE_LONG_COINS)} items). ---")
        config['long_coin_list'] = AVAILABLE_LONG_COINS
    elif config.get('long_coin_list') is None:
        config['long_coin_list'] = AVAILABLE_LONG_COINS

    if not config.get('short_coin_list') and AVAILABLE_SHORT_COINS:
        print(
            f"--- [INFO] User settings missing 'short_coin_list', using default pool ({len(AVAILABLE_SHORT_COINS)} items). ---")
        config['short_coin_list'] = AVAILABLE_SHORT_COINS
    elif config.get('short_coin_list') is None:
        config['short_coin_list'] = AVAILABLE_SHORT_COINS

    config['api_key'] = os.environ.get('BINANCE_API_KEY', config.get('api_key', ''))
    config['api_secret'] = os.environ.get('BINANCE_API_SECRET', config.get('api_secret', ''))

    print(
        f"--- [DEBUG] Loaded Settings: Leverage={config.get('leverage')}, Long Coins={len(config.get('long_coin_list', []))}, Short Coins={len(config.get('short_coin_list', []))} ---")

    return config


def save_settings(current_config):
    try:
        config_to_save = current_config.copy()

        # 核心修改：移除同步币种列表到 user_settings.json 的逻辑
        print(f"--- [INFO] User settings successfully saved to '{USER_SETTINGS_FILE}'. ---")

        settings_data_to_write = {key: value for key, value in config_to_save.items() if key in DEFAULT_CONFIG}

        with open(USER_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings_data_to_write, f, indent=4, ensure_ascii=False)

        print(f"--- [INFO] User settings successfully saved to '{USER_SETTINGS_FILE}'. ---")

    except Exception as e:
        print(f"--- [ERROR] Failed to save user settings: {e} ---")
        return False

    return True


def get_all_coins() -> List[str]:
    """获取所有可用币种。"""
    if not AVAILABLE_COINS:
        load_coin_lists()
    return AVAILABLE_COINS


# 首次加载
load_coin_lists()