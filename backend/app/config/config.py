# backend/app/config/config.py
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple, Set # 引入 Set

# --- 核心修复：统一路径解析 ---
if os.environ.get("IS_DOCKER"):
    _PROJECT_ROOT = Path('/app')
else:
    # Path(__file__) -> .../backend/app/config/config.py
    # .parent.parent.parent -> .../backend/
    # .parent -> .../trading_webapp/ (项目根目录)
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

USER_SETTINGS_FILE = _PROJECT_ROOT / 'user_settings.json'
COIN_LISTS_FILE = _PROJECT_ROOT / 'coin_lists.json'
# --- 修复结束 ---

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

    # --- 新增/修改：用户选择的币种列表 ---
    'user_selected_long_coins': [], # 用户从大池子中选择的做多币种
    'user_selected_short_coins': [], # 用户从大池子中选择的做空币种
    # --- 修改结束 ---

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

# --- 新增/修改：全局变量 ---
ALL_AVAILABLE_COINS: List[str] = [] # 合并后的所有可用币种
# --- 修改结束 ---

def load_coin_pools():
    """
    加载所有可用的币种池，并返回一个合并后的唯一币种列表。
    """
    all_coins: Set[str] = set()
    try:
        if not COIN_LISTS_FILE.exists():
            print(f"严重警告: 核心配置文件 {COIN_LISTS_FILE} 未找到！将使用空列表。")
            return [] # 返回空列表
        with open(COIN_LISTS_FILE, 'r', encoding='utf-8') as f:
            pools = json.load(f)
            # 将 long_coins_pool 和 short_coins_pool 中的所有币种添加到集合中
            all_coins.update(pools.get("long_coins_pool", []))
            all_coins.update(pools.get("short_coins_pool", []))
            return sorted(list(all_coins)) # 返回排序后的唯一币种列表
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"严重警告: 加载币种列表失败: {e}！将使用空列表。")
        return [] # 返回空列表

# --- 修改：全局变量的加载方式 ---
# 只加载一次所有可用的币种池
ALL_AVAILABLE_COINS = load_coin_pools()
# --- 修改结束 ---

def load_settings():
    config = DEFAULT_CONFIG.copy() # 使用完整的默认配置作为基础
    if not USER_SETTINGS_FILE.exists():
        print(f"用户配置文件 {USER_SETTINGS_FILE} 不存在，将使用默认配置。")
        # 首次运行时，将默认配置写入文件，但保留用户选择的空列表
        config['user_selected_long_coins'] = []
        config['user_selected_short_coins'] = []
        return config
    try:
        with open(USER_SETTINGS_FILE, 'r') as f:
            user_settings = json.load(f)
            # 用用户配置更新默认配置，但保留默认值中的 user_selected_* 列表
            # 如果用户配置文件中没有这两个key，会保持DEFAULT_CONFIG的空数组
            for key in DEFAULT_CONFIG:
                if key in user_settings:
                    # 对于列表类型的配置，进行合并或覆盖
                    if key == 'user_selected_long_coins' or key == 'user_selected_short_coins':
                        config[key] = user_settings.get(key, []) # 确保是列表，即使文件中有null
                    else:
                        config[key] = user_settings[key]

    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"警告: 无法加载或解析 {USER_SETTINGS_FILE} ({e})，将使用默认配置。")
        # 首次运行且文件损坏，也写入默认配置
        config['user_selected_long_coins'] = []
        config['user_selected_short_coins'] = []


    # --- 核心修改：直接加载用户保存的列表 ---
    # 后端这里不需要回退逻辑，直接加载用户保存的就是最好的。
    # `load_settings` 会负责读取 `user_settings.json` 中的 `user_selected_long_coins` 和 `user_selected_short_coins`
    # 如果文件不存在或不存在这些键，则会使用 DEFAULT_CONFIG 中的空列表。

    config['api_key'] = os.environ.get('BINANCE_API_KEY', config.get('api_key', ''))
    config['api_secret'] = os.environ.get('BINANCE_API_SECRET', config.get('api_secret', ''))
    return config


def save_settings(current_config):
    try:
        with open(USER_SETTINGS_FILE, 'w') as f:
            # 确保只保存 DEFAULT_CONFIG 中定义的键值对
            settings_to_save = {key: current_config.get(key) for key in DEFAULT_CONFIG if key in current_config}
            # 确保 user_selected_* 列表是数组
            settings_to_save['user_selected_long_coins'] = settings_to_save.get('user_selected_long_coins', [])
            settings_to_save['user_selected_short_coins'] = settings_to_save.get('user_selected_short_coins', [])

            json.dump(settings_to_save, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"错误：保存配置失败: {e}")
        raise