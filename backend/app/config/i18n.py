# backend/app/config/i18n.py (精简版)

# --- Internal Constants for Logic (Aligned with CCXT) ---
# 这些是后端业务逻辑实际依赖的常量，必须保留。
SIDE_LONG = 'long'
SIDE_SHORT = 'short'
ORDER_SIDE_BUY = 'buy'
ORDER_SIDE_SELL = 'sell'

# --- User-Facing Strings (Localization) ---
# REFACTOR: 以下所有常量都是为已不存在的Tkinter GUI准备的。
# 在当前的Web架构中，这些UI文本应由前端负责，后端不再需要它们。
# 因此，可以安全地将它们全部删除，以简化代码库。