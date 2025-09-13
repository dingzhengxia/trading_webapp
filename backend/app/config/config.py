# backend/app/config.py (完整重构版)
import json
import os
from pathlib import Path

# --- 核心改动：路径解析 ---
# 以当前文件为基准，向上找两级到 backend/ 目录，再向上一级到项目根目录
_BASE_DIR = Path(__file__).resolve().parent.parent.parent
USER_SETTINGS_FILE = _BASE_DIR / 'user_settings.json'
COIN_LISTS_FILE = _BASE_DIR / 'coin_lists.json'
# ---------------------------

STABLECOIN_PREFERENCE = ['USDC', 'USDT']

DEFAULT_CONFIG = {
    'api_key': '', 'api_secret': '', 'use_testnet': True,
    'enable_long_trades': True,
    'enable_short_trades': True,
    'total_long_position_value': 1000.0, 'total_short_position_value': 500.0,
    'leverage': 20,
    'enable_long_sl_tp': True,
    'long_stop_loss_percentage': 50.0,
    'long_take_profit_percentage': 100.0,
    'enable_short_sl_tp': True,
    'short_stop_loss_percentage': 80.0,
    'short_take_profit_percentage': 150.0,

    'long_coin_list': ["BTC", "ETH"],
    'short_coin_list': ["TIA", "DYM", "ETHFI"],
    'long_custom_weights': {},
    'open_order_fill_timeout_seconds': 120,
    'open_maker_retries': 5,
    'close_order_fill_timeout_seconds': 12,
    'close_maker_retries': 3,
    'enable_proxy': False,
    'proxy_url': 'http://127.0.0.1:7890',

    # --- 新增/确保这些字段存在 ---
    'rebalance_method': 'multi_factor_weakest',
    'rebalance_top_n': 50,
    'rebalance_min_volume_usd': 20000000.0,
    'rebalance_abs_momentum_days': 30,
    'rebalance_rel_strength_days': 60,
    'rebalance_foam_days': 1,
    # ---------------------------

    'rebalance_short_ratio_max': 0.70,
    'rebalance_short_ratio_min': 0.35
}


def load_coin_pools():
    try:
        with open(COIN_LISTS_FILE, 'r', encoding='utf-8') as f:
            pools = json.load(f)
            long_coins = sorted(pools.get("long_coins_pool", []))
            short_coins = sorted(pools.get("short_coins_pool", []))
            return long_coins, short_coins
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"严重警告: 核心配置文件 {COIN_LISTS_FILE} 未找到！")
        return [], []


AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS = load_coin_pools()


def load_settings():
    config = DEFAULT_CONFIG.copy()
    if not USER_SETTINGS_FILE.exists():
        print(f"用户配置文件 {USER_SETTINGS_FILE} 不存在，将使用默认配置。")
        return config
    try:
        with open(USER_SETTINGS_FILE, 'r') as f:
            user_settings = json.load(f)
            config.update({k: user_settings[k] for k in DEFAULT_CONFIG if k in user_settings})
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"警告: 无法加载或解析 {USER_SETTINGS_FILE}，将使用默认配置。")

    # 优先使用环境变量中的API密钥
    config['api_key'] = os.environ.get('BINANCE_API_KEY', config.get('api_key', ''))
    config['api_secret'] = os.environ.get('BINANCE_API_SECRET', config.get('api_secret', ''))
    return config


def save_settings(current_config):
    try:
        with open(USER_SETTINGS_FILE, 'w') as f:
            settings_to_save = {key: current_config.get(key) for key in DEFAULT_CONFIG}
            json.dump(settings_to_save, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"错误：保存配置失败: {e}")
        raise
