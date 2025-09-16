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
    如果文件不存在或解析错误，则返回空列表。
    """
    try:
        if not COIN_LISTS_FILE.exists():
            print(f"--- [WARN] Core coin list file '{COIN_LISTS_FILE}' not found! Using empty pools. ---")
            return [], []
        with open(COIN_LISTS_FILE, 'r', encoding='utf-8') as f:
            pools = json.load(f)
            long_coins = sorted(pools.get("long_coins_pool", []))
            short_coins = sorted(pools.get("short_coins_pool", []))
            print(f"--- [INFO] Loaded coin pools from '{COIN_LISTS_FILE}'. Long pool size: {len(long_coins)}, Short pool size: {len(short_coins)} ---")
            return long_coins, short_coins
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"--- [ERROR] Failed to load or parse coin list file '{COIN_LISTS_FILE}': {e}! Using empty pools. ---")
        return [], []

# --- 核心逻辑：在启动时加载一次，并存储在全局变量中 ---
AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS = load_coin_pools()
print(f"--- [INFO] Initial AVAILABLE_LONG_COINS: {AVAILABLE_LONG_COINS[:5]}..., AVAILABLE_SHORT_COINS: {AVAILABLE_SHORT_COINS[:5]}... ---")
# --- 逻辑结束 ---


def load_settings():
    """
    加载用户设置。
    1. 从默认配置开始。
    2. 如果 user_settings.json 存在，则覆盖默认配置。
    3. 如果 user_settings.json 中缺少某些项，则使用 AVAILABLE_XXX_COINS 中的值（如果内存中有）。
    4. 从环境变量 BINANCE_API_KEY 和 BINANCE_API_SECRET 获取 API Key/Secret。
    """
    config = DEFAULT_CONFIG.copy()

    if USER_SETTINGS_FILE.exists():
        try:
            with open(USER_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                user_settings = json.load(f)
                # 更新配置，只覆盖 user_settings.json 中存在的键
                config.update({k: user_settings[k] for k in config if k in user_settings})
                print(f"--- [INFO] Loaded user settings from '{USER_SETTINGS_FILE}'. ---")
        except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
            print(f"--- [WARN] Could not load or parse '{USER_SETTINGS_FILE}' ({e}). Using default settings. ---")
    else:
        print(f"--- [INFO] User settings file '{USER_SETTINGS_FILE}' not found. Using default settings. ---")

    # --- 核心修改：确保 coin_list 字段总是被正确加载 ---
    # 如果 user_settings.json 中没有 long_coin_list 或 short_coin_list，
    # 或者它们是空的，则使用从 coin_lists.json 加载的 AVAILABLE_XXX_COINS
    if not config.get('long_coin_list') and AVAILABLE_LONG_COINS:
        print(f"--- [INFO] User settings missing 'long_coin_list', using default pool ({len(AVAILABLE_LONG_COINS)} items). ---")
        config['long_coin_list'] = AVAILABLE_LONG_COINS
    elif config.get('long_coin_list') is None: # 如果 user_settings.json 中是 null
        config['long_coin_list'] = AVAILABLE_LONG_COINS

    if not config.get('short_coin_list') and AVAILABLE_SHORT_COINS:
        print(f"--- [INFO] User settings missing 'short_coin_list', using default pool ({len(AVAILABLE_SHORT_COINS)} items). ---")
        config['short_coin_list'] = AVAILABLE_SHORT_COINS
    elif config.get('short_coin_list') is None: # 如果 user_settings.json 中是 null
        config['short_coin_list'] = AVAILABLE_SHORT_COINS
    # --- 核心修改结束 ---

    # 从环境变量覆盖 API Key/Secret
    config['api_key'] = os.environ.get('BINANCE_API_KEY', config.get('api_key', ''))
    config['api_secret'] = os.environ.get('BINANCE_API_SECRET', config.get('api_secret', ''))

    # 打印一些关键配置值用于调试
    print(f"--- [DEBUG] Loaded Settings: Leverage={config.get('leverage')}, Long Coins={len(config.get('long_coin_list', []))}, Short Coins={len(config.get('short_coin_list', []))} ---")

    return config


def save_settings(current_config):
    try:
        # 创建一个副本以避免修改传入的字典
        config_to_save = current_config.copy()

        # --- 核心修改：保存时，用内存中的 AVAILABLE_XXX_COINS 覆盖 user_settings.json 中的值 ---
        config_to_save['long_coin_list'] = AVAILABLE_LONG_COINS
        config_to_save['short_coin_list'] = AVAILABLE_SHORT_COINS
        print(f"--- [INFO] Syncing coin lists to user settings before saving. Long pool size: {len(AVAILABLE_LONG_COINS)}, Short pool size: {len(AVAILABLE_SHORT_COINS)} ---")
        # --- 核心修改结束 ---

        # 准备要写入的数据，只包含 DEFAULT_CONFIG 中的键
        settings_data_to_write = {}
        for key in DEFAULT_CONFIG:
            if key in config_to_save: # <-- 这里检查的是 config_to_save
                settings_data_to_write[key] = config_to_save[key]
            # elif key in config: # <-- 这里出现的错误，应该是 'config' 而不是 'config_to_save'
            elif key in current_config: # <-- 修正为 current_config，它是传入的那个字典
                settings_data_to_write[key] = current_config[key] # <-- 使用 current_config

        with open(USER_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings_data_to_write, f, indent=4, ensure_ascii=False)
        print(f"--- [INFO] User settings successfully saved to '{USER_SETTINGS_FILE}'. ---")
    except Exception as e:
        print(f"--- [ERROR] Failed to save settings to '{USER_SETTINGS_FILE}': {e} ---")
        raise