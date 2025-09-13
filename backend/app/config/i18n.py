# backend/app/config/i18n.py

# --- Internal Constants for Logic (Aligned with CCXT) ---
SIDE_LONG = 'long'
SIDE_SHORT = 'short'
ORDER_SIDE_BUY = 'buy'
ORDER_SIDE_SELL = 'sell'

# --- User-Facing Strings (Localization) ---
TEXT_SIDE_LONG = "多头"
TEXT_SIDE_SHORT = "空头"
TEXT_SIDE_UNKNOWN = "未知"

SIDE_MAP = { SIDE_LONG: TEXT_SIDE_LONG, SIDE_SHORT: TEXT_SIDE_SHORT }
SIDE_MAP_REVERSE = {v: k for k, v in SIDE_MAP.items()}

# --- UI Texts ---
TITLE_APP = "币安合约对冲交易GUI (v26.0 - Dynamic Rebalance)"
TITLE_APP_CONFIG_FRAME = "应用配置"
TITLE_PARAMS_FRAME = "交易参数"
TITLE_LONG_SETTINGS_FRAME = f"{TEXT_SIDE_LONG}设置"
TITLE_SHORT_SETTINGS_FRAME = f"{TEXT_SIDE_SHORT}设置"
TITLE_COMMON_SETTINGS_FRAME = "通用开仓设置"
TITLE_CLOSE_SETTINGS_FRAME = "通用平仓设置"
TITLE_ACTION_FRAME = "执行开仓"
TITLE_POSITION_ACTIONS_FRAME = "持仓操作"
TITLE_POSITIONS_FRAME = "当前持仓"
TITLE_STATUS_FRAME = "任务状态"
TITLE_LOG_FRAME = "执行日志"

LABEL_LONG_POSITIONS = f"▲ {TEXT_SIDE_LONG}仓位"
LABEL_SHORT_POSITIONS = f"▼ {TEXT_SIDE_SHORT}仓位"
LABEL_TOTAL_VALUE = "| 总价值: {value:,.2f}"

# Buttons
BUTTON_REFRESH = "刷新持仓"
BUTTON_SYNC_SL_TP = "校准SL/TP"
BUTTON_EXECUTE_REBALANCE = "执行再平衡"
BUTTON_CLOSE_SELECTED = "平选中"
BUTTON_CLOSE_LONGS = f"平{TEXT_SIDE_LONG}"
BUTTON_CLOSE_SHORTS = f"平{TEXT_SIDE_SHORT}"
BUTTON_CLOSE_ALL = "全部平仓"
BUTTON_START = "▶ 开始开仓"
BUTTON_STOP = "⏹ 停止执行"
BUTTON_CONFIG_WEIGHTS = "配置权重"
BUTTON_CONFIG_API = "配置API"
BUTTON_SELECT_COINS = "选择交易币种"
BUTTON_REBALANCE = "更新币种列表" # Changed name to be more specific

# --- Dialogs & Messages ---
DIALOG_TITLE_API = "API 配置"
DIALOG_TITLE_COIN_SELECTION = "币种选择"
DIALOG_TITLE_CLOSE_SELECTED = "平掉选中仓位"
DIALOG_TITLE_CLOSE_ALL_LONGS = f"平掉所有{TEXT_SIDE_LONG}仓位"
DIALOG_TITLE_CLOSE_ALL_SHORTS = f"平掉所有{TEXT_SIDE_SHORT}仓位"
DIALOG_TITLE_CLOSE_ALL = "!!! 平掉所有仓位 !!!"

MSG_NO_POSITIONS_TO_CLOSE = "未找到可平仓的仓位。"
MSG_OPERATION_CANCELED = "操作已取消或平仓比例为0。"
MSG_SYNC_CONFIRM_TITLE = "确认校准"
MSG_SYNC_CONFIRM_BODY = "此操作将根据当前UI界面的参数，为所有持仓自动创建/修正止盈止损单。\n对于UI中禁用了SL/TP的方向，此操作会清理其所有止盈止损挂单。\n\n确定要继续吗？"