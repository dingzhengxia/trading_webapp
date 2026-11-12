# backend/app/config/config.py (完整代码)
import copy
import os
from typing import List, Dict, Any
from threading import RLock

from ..core.paths import PROJECT_ROOT

# --- 路径定义 ---
# 旧 JSON 文件路径：仅作为一次性迁移到 SQLite 的来源保留（迁移后文件不动）
USER_SETTINGS_FILE = PROJECT_ROOT / 'user_settings.json'
COIN_LISTS_FILE = PROJECT_ROOT / 'coin_lists.json'
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
    'leverage': 5,
    'enable_long_sl_tp': True,
    # percent 口径只是 ATR 不可用时的兜底。40% ÷ leverage=5 → 价格 -8%/+8%，
    # 与回测最优的 atr 1.5/1R（中位止损 2.3%→约 8% 保证金占用）同一量级；
    # 注意 percent 与 leverage 强耦合：改杠杆必须同步核对这些值，否则止损会悄悄变宽/变窄
    'long_stop_loss_percentage': 40.0,
    'long_take_profit_percentage': 40.0,
    'enable_short_sl_tp': True,
    'short_stop_loss_percentage': 40.0,
    'short_take_profit_percentage': 40.0,

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
        'rsi_divergence', 'ob_luxalgo', 'ob_fluxcharts',
    ],
    # 1h 回测净收益只有 ~6bp（4126 笔换手，16bp 成本即归零），只推信号不自动开仓
    'signal_auto_trade_timeframes': ['4h'],
    'signal_auto_trade_confirmation_window_seconds': 300,
    'signal_auto_trade_confirmations': 1,
    'signal_auto_trade_cooldown_seconds': 900,
    'signal_auto_trade_max_positions': 5,
    'signal_auto_trade_value_usd': 100.0,
    # 币种信号的钉钉推送子开关（总开关仍是 dingtalk_enabled；默认开启）
    'signal_dingtalk_enabled': True,
    # 推送量能门槛：静态币(signal_scan_static_symbols)实时全推，
    # 其它币要求成交量达到「当前量/动态基准」≥ 该倍数才推送；0 表示不过滤
    'signal_push_volume_multiplier': 2.0,
    # 纸面跟踪：复用自动开仓过滤链，只记录不下单
    'signal_paper_enabled': False,
    # ---- 统一出场层（实盘挂单 + 纸面跟踪共用 core/exit_rules.py 的同一份实现）----
    # percent = 设置页的 {side}_stop_loss/take_profit_percentage ÷ leverage 折算价格距离；
    # atr     = N×ATR 止损 + R 倍数止盈（实盘取 signal_live_exit_timeframe 周期的 ATR，
    #           拿不到时自动回退 percent，绝不裸奔）
    # atr 是回测唯一在前/后半段都为正的口径（+12.4/+30.5bp）；percent 各宽度均劣于它
    'signal_exit_mode': 'atr',
    'signal_paper_sl_atr': 1.5,
    # TP 必须 ≤1R：持有 6/8/12/16/20 根下 1R 恒 +25~30bp，2R 恒负、3R 恒更负
    'signal_paper_tp_r': 1.0,
    'signal_paper_max_bars': 6,
    # 实盘 ATR 口径使用的周期（ATR 只影响「价格距离多大」，与持仓周期无关）
    'signal_live_exit_timeframe': '4h',
    # 实盘超时平仓：持有满 signal_paper_max_bars 根就市价平掉「信号自动开」的仓；
    # 回测里 19% 的交易靠超时退出，不开就少了这半边收益
    'signal_live_exit_timeout_enabled': True,
    # 信号前视收益的持有期（单位：根 K 线），用于「信号发出后到底赚不赚」的统计
    'signal_forward_bars': [4, 12],

    # 手动交易页持久化预设（选中币种/每行动作与价值/默认价值），随 settings 存入 SQLite
    'manual_trade_preset': {},

    # 仓位保护（Phase 3，自 monitor 并入）：完整的默认值见 app/protection/engine.py 的
    # DEFAULT_CONFIG；这里只保留空字典以允许该配置项写入 settings 表。
    # 默认 enabled=False，前端「仓位保护」页打开开关后才会启动引擎。
    'position_protection': {},

    # 周期报告（自 monitor periodic_reports 并入）：默认全部关闭，开启后按周期生成
    # 热门合约涨幅榜/放量榜/连涨榜/RSI 超买超卖，并推送到网页日志（可选钉钉）
    'periodic_reports': [
        {
            'enabled': False,
            'report_name': '4小时热点报告',
            'run_interval': '4h',
            'top_n_by_volume': 100,
            'top_n_gainers': 10,
            'min_consecutive_candles': 5,
            'volume_ma_period': 20,
            'top_n_volume_ratio': 10,
            'market_sentiment': {
                'enabled': True, 'rsi_period': 14, 'rsi_overbought': 70, 'rsi_oversold': 30,
            },
        },
        {
            'enabled': False,
            'report_name': '每日宏观复盘',
            'run_interval': '1d',
            'top_n_by_volume': 100,
            'top_n_gainers': 10,
            'min_consecutive_candles': 3,
            'volume_ma_period': 20,
            'top_n_volume_ratio': 10,
            'market_sentiment': {
                'enabled': True, 'rsi_period': 14, 'rsi_overbought': 75, 'rsi_oversold': 25,
            },
        },
    ],
    # 钉钉推送总开关（webhook/secret 只从环境变量读取，不写入此处）
    'dingtalk_enabled': False,
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

        # 用 or 而非默认参数：.env 里留空的 `BINANCE_API_KEY=` 会被 python-dotenv
        # 写成空字符串，用默认参数会让空值覆盖数据库里已保存的真实密钥（导致 -2015）。
        config['api_key'] = os.environ.get('BINANCE_API_KEY') or config.get('api_key', '')
        config['api_secret'] = os.environ.get('BINANCE_API_SECRET') or config.get('api_secret', '')

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
