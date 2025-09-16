# backend/app/config/config.py
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple, Set

# ... (路径设置保持不变) ...
# --- 核心修复：统一路径解析 ---
if os.environ.get("IS_DOCKER"):
    _PROJECT_ROOT = Path('/app')
else:
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

    # --- 保留原始的 coin_list 字段，用于向后兼容或作为用户选择的默认值 ---
    # --- 但在实际逻辑中使用 user_selected_* ---
    'long_coin_list': ["BTC", "ETH"],
    'short_coin_list': ["SOL", "AVAX"],
    # --- 结束 ---

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

# --- 保留全局变量 ---
ALL_AVAILABLE_COINS: List[str] = [] # 合并后的所有可用币种
AVAILABLE_LONG_COINS: List[str] = [] # 从 coin_lists.json 加载的原始多头池
AVAILABLE_SHORT_COINS: List[str] = [] # 从 coin_lists.json 加载的原始空头池
# --- 保留结束 ---

def load_coin_pools():
    """
    加载所有可用的币种池，并返回合并后的唯一币种列表，
    以及原始的多头和空头币种列表。
    """
    all_coins: Set[str] = set()
    long_coins_from_file: List[str] = []
    short_coins_from_file: List[str] = []

    try:
        if not COIN_LISTS_FILE.exists():
            print(f"严重警告: 核心配置文件 {COIN_LISTS_FILE} 未找到！将使用空列表。")
            return [], [], [] # 返回三个空列表
        with open(COIN_LISTS_FILE, 'r', encoding='utf-8') as f:
            pools = json.load(f)
            long_coins_from_file = sorted(pools.get("long_coins_pool", []))
            short_coins_from_file = sorted(pools.get("short_coins_pool", []))
            all_coins.update(long_coins_from_file)
            all_coins.update(short_coins_from_file)
            return sorted(list(all_coins)), long_coins_from_file, short_coins_from_file
    except (FileNotFoundError, json.MismatchedDataTypeError, json.JSONDecodeError) as e:
        print(f"严重警告: 加载币种列表失败: {e}！将使用空列表。")
        return [], [], [] # 返回三个空列表
    except Exception as e:
        print(f"严重警告: 加载币种列表时发生未知错误: {e}！将使用空列表。")
        return [], [], []

# --- 全局变量初始化 ---
ALL_AVAILABLE_COINS, AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS = load_coin_pools()
# --- 全局变量初始化结束 ---

def load_settings():
    config = DEFAULT_CONFIG.copy()
    if not USER_SETTINGS_FILE.exists():
        print(f"用户配置文件 {USER_SETTINGS_FILE} 不存在，将使用默认配置。")
        # 首次运行时，确保 user_selected_* 字段存在
        config['user_selected_long_coins'] = []
        config['user_selected_short_coins'] = []
        return config
    try:
        with open(USER_SETTINGS_FILE, 'r') as f:
            user_settings = json.load(f)
            # 用用户配置更新默认配置
            for key in DEFAULT_CONFIG:
                if key in user_settings:
                    config[key] = user_settings[key]

            # --- 核心：确保 user_selected_* 字段存在且是列表 ---
            # 如果用户配置文件中没有这两个key，或者值不是列表，则使用默认值
            if not isinstance(config.get('user_selected_long_coins'), list):
                config['user_selected_long_coins'] = []
            if not isinstance(config.get('user_selected_short_coins'), list):
                config['user_selected_short_coins'] = []
            # --- 核心结束 ---

    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"警告: 无法加载或解析 {USER_SETTINGS_FILE} ({e})，将使用默认配置。")
        # 首次运行且文件损坏，也设置默认空列表
        config['user_selected_long_coins'] = []
        config['user_selected_short_coins'] = []

    config['api_key'] = os.environ.get('BINANCE_API_KEY', config.get('api_key', ''))
    config['api_secret'] = os.environ.get('BINANCE_API_SECRET', config.get('api_secret', ''))
    return config

def save_settings(current_config):
    try:
        with open(USER_SETTINGS_FILE, 'w') as f:
            settings_to_save = {key: current_config.get(key) for key in DEFAULT_CONFIG if key in current_config}
            # 确保 user_selected_* 列表是数组
            settings_to_save['user_selected_long_coins'] = settings_to_save.get('user_selected_long_coins', [])
            settings_to_save['user_selected_short_coins'] = settings_to_save.get('user_selected_short_coins', [])

            json.dump(settings_to_save, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"错误：保存配置失败: {e}")
        raise