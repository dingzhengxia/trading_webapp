# backend/app/config/config.py

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
    'long_coin_list': ["BTC", "ETH"],
    'short_coin_list': ["SOL", "AVAX"],
    'long_custom_weights': {},
    'open_order_fill_timeout_seconds': 120,
    'open_maker_retries': 5,
    'close_order_fill_timeout_seconds': 12,
    'close_maker_retries': 3,
    'enable_proxy': False,
    'proxy_url': 'http://127.0.0.1:7890',
    'rebalance_method': 'multi_factor_weakest',
    'rebalance_top_n': 50,
    'rebalance_min_volume_usd': 20000000.0,
    'rebalance_abs_momentum_days': 30,
    'rebalance_rel_strength_days': 60,
    'rebalance_foam_days': 1,
    'rebalance_short_ratio_max': 0.70,
    'rebalance_short_ratio_min': 0.35
}


def load_coin_pools():
    """
    从 coin_lists.json 加载币种池。
    """
    all_coins = []
    long_coins = []
    short_coins = []
    try:
        if not COIN_LISTS_FILE.exists():
            print(f"--- [WARN] Core coin list file '{COIN_LISTS_FILE}' not found! Using empty pools. ---")
            return [], [], []
        with open(COIN_LISTS_FILE, 'r', encoding='utf-8') as f:
            pools = json.load(f)
            all_coins = sorted(list(set(pools.get("coins_pool", []))))  # 新增：读取 coins_pool 字段
            long_coins = sorted(list(set(pools.get("long_coins_pool", []))))
            short_coins = sorted(list(set(pools.get("short_coins_pool", []))))
            print(
                f"--- [INFO] Loaded coin pools from '{COIN_LISTS_FILE}'. All coins size: {len(all_coins)}, Long pool size: {len(long_coins)}, Short pool size: {len(short_coins)} ---")
            return all_coins, long_coins, short_coins
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"--- [ERROR] Failed to load or parse coin list file '{COIN_LISTS_FILE}': {e}! Using empty pools. ---")
        return [], [], []


# --- 核心逻辑：在启动时加载一次，并存储在全局变量中 ---
AVAILABLE_COINS, AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS = load_coin_pools()
print(
    f"--- [INFO] Initial AVAILABLE_COINS: {AVAILABLE_COINS[:5]}..., AVAILABLE_LONG_COINS: {AVAILABLE_LONG_COINS[:5]}..., AVAILABLE_SHORT_COINS: {AVAILABLE_SHORT_COINS[:5]}... ---")


# --- 逻辑结束 ---


def load_settings():
    """
    加载用户设置。
    """
    config = DEFAULT_CONFIG.copy()

    if USER_SETTINGS_FILE.exists():
        try:
            with open(USER_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                user_settings = json.load(f)
                config.update({k: user_settings[k] for k in config if k in user_settings})
                print(f"--- [INFO] Loaded user settings from '{USER_SETTINGS_FILE}'. ---")
        except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
            print(f"--- [WARN] Could not load or parse '{USER_SETTINGS_FILE}' ({e}). Using default settings. ---")
    else:
        print(f"--- [INFO] User settings file '{USER_SETTINGS_FILE}' not found. Using default settings. ---")

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

        # 保存时不再同步币种列表到 user_settings.json，因为它们现在由 coin_lists.json 管理
        print(f"--- [INFO] User settings successfully saved to '{USER_SETTINGS_FILE}'. ---")

        settings_data_to_write = {key: config_to_save[key] for key in DEFAULT_CONFIG if key in config_to_save}

        with open(USER_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings_data_to_write, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"--- [ERROR] Failed to save settings to '{USER_SETTINGS_FILE}': {e} ---")
        raise