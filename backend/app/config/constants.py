# backend/app/config/constants.py
"""后端业务逻辑常量（与 CCXT 统一命名对齐）。

说明：这些常量是交易逻辑实际依赖的枚举值，前端展示文案由前端负责。
"""

# --- 仓位方向 ---
SIDE_LONG = 'long'
SIDE_SHORT = 'short'

# --- 订单方向 ---
ORDER_SIDE_BUY = 'buy'
ORDER_SIDE_SELL = 'sell'

# --- 订单类型 ---
ORDER_TYPE_LIMIT = 'limit'
ORDER_TYPE_STOP_MARKET = 'STOP_MARKET'
ORDER_TYPE_TAKE_PROFIT_MARKET = 'TAKE_PROFIT_MARKET'
ORDER_TYPE_TRAILING_STOP = 'TRAILING_STOP_MARKET'
