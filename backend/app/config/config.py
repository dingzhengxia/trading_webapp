import json
import os
from pathlib import Path

# --- 核心修复：统一路径解析逻辑 ---
# 在 Docker 中, WORKDIR 是 /app/backend, __file__ 会是 /app/backend/app/config/config.py
# 在本地, __file__ 是 .../trading_webapp/backend/app/config/config.py
# 无论哪种情况, 向上找三级目录都能到达 backend/ 的根目录
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

if os.environ.get("IS_DOCKER"):
    # 在 Docker 容器中, 配置文件与 backend 代码在同一顶级目录 /app/backend 下
    _CONFIG_BASE_DIR = _BACKEND_ROOT
else:
    # 在本地开发时, 您的配置文件也位于 backend 目录内部
    _CONFIG_BASE_DIR = _BACKEND_ROOT

USER_SETTINGS_FILE = _CONFIG_BASE_DIR / 'user_settings.json'
COIN_LISTS_FILE = _CONFIG_BASE_DIR / 'coin_lists.json'
# --- 修复结束 ---

STABLECOIN_PREFERENCE = ['USDC', 'USDT']

DEFAULT_CONFIG = {
    'api_key': '', 'api_secret': '', 'use_testnet': True,

    'enable_long_trades': True,
    'enable_short_trades': True,

    'total_long_position_value': 1000.0, 'total_short_position_value': 500.0,
    'leverage': 20,

    'enable_long_sl_tp': True, 'long_stop_loss_percentage': 50.0, 'long_take_profit_percentage': 100.0,
    'enable_short_sl_tp': True, 'short_stop_loss_percentage': 80.0, 'short_take_profit_percentage': 150.0,

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
    """加载多头和空头的备选币种池"""
    try:
        if not COIN_LISTS_FILE.exists():
            print(f"严重警告: 核心配置文件 {COIN_LISTS_FILE} 未找到！将使用空列表。")
            return [], []
        with open(COIN_LISTS_FILE, 'r', encoding='utf-8') as f:
            pools = json.load(f)
            long_coins = sorted(pools.get("long_coins_pool", []))
            short_coins = sorted(pools.get("short_coins_pool", []))
            return long_coins, short_coins
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"严重警告: 加载币种列表失败: {e}！将使用空列表。")
        return [], []


AVAILABLE_LONG_COINS, AVAILABLE_SHORT_COINS = load_coin_pools()


def load_settings():
    """加载用户设置，如果文件不存在或无效，则使用默认值"""
    config = DEFAULT_CONFIG.copy()
    if not USER_SETTINGS_FILE.exists():
        print(f"用户配置文件 {USER_SETTINGS_FILE} 不存在，将使用默认配置。")
        return config
    try:
        with open(USER_SETTINGS_FILE, 'r') as f:
            user_settings = json.load(f)
            # 只用 user_settings 中存在的、且 DEFAULT_CONFIG 也存在的键来更新
            config.update({k: user_settings[k] for k in DEFAULT_CONFIG if k in user_settings})
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"警告: 无法加载或解析 {USER_SETTINGS_FILE} ({e})，将使用默认配置。")

    # 优先使用环境变量中的API密钥 (用于生产环境)
    config['api_key'] = os.environ.get('BINANCE_API_KEY', config.get('api_key', ''))
    config['api_secret'] = os.environ.get('BINANCE_API_SECRET', config.get('api_secret', ''))
    return config


def save_settings(current_config):
    """保存当前配置到 user_settings.json"""
    try:
        with open(USER_SETTINGS_FILE, 'w') as f:
            # 只保存 DEFAULT_CONFIG 中定义的键，避免写入未知字段
            settings_to_save = {key: current_config.get(key) for key in DEFAULT_CONFIG}
            json.dump(settings_to_save, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"错误：保存配置失败: {e}")
        raise