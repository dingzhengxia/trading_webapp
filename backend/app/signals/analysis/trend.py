# --- START OF FILE analysis/trend.py (CORRECTED V35.2) ---
# 从 monitor/app/analysis/trend.py 复制；仅将 app.utils 顶层导入改为包内相对导入，
# 策略判定逻辑未改动。
import pandas_ta as pta
from loguru import logger
# 包内相对导入（原 monitor: from app.utils import timeframe_to_minutes）
from ..runtime import timeframe_to_minutes  # noqa: F401  <-- 从 runtime 导入


def get_current_trend(df, timeframe, trend_params_config):
    df_trend = df.copy()
    tf_minutes = timeframe_to_minutes(timeframe)
    trend_params = trend_params_config.get('trend_ema_short' if tf_minutes <= 60 else 'trend_ema_long',
                                           trend_params_config.get('trend_ema', {}))

    emas = {'fast': trend_params.get('fast'), 'medium': trend_params.get('medium'), 'long': trend_params.get('long')}
    if not all(period and period > 0 for period in emas.values()):
        logger.debug(f"趋势EMA参数配置不完整或周期不合法: {trend_params}")
        return "趋势未知", "↔️"

    for name, period in emas.items():
        df_trend[f'ema_{name}'] = pta.ema(df_trend['close'], length=period)

    required_cols = [f'ema_{name}' for name in emas.keys()]
    if not all(c in df_trend.columns for c in required_cols):
        return "趋势未知", "↔️"

    df_trend = df_trend.dropna()
    if df_trend.empty:
        return "趋势未知", "↔️"

    last = df_trend.iloc[-1]
    if last['ema_fast'] > last['ema_medium'] and last['ema_medium'] > last['ema_long']:
        return "多头趋势", "🐂"
    if last['ema_fast'] < last['ema_medium'] and last['ema_medium'] < last['ema_long']:
        return "空头趋势", "🐻"

    return "震荡趋势", "↔️"
# --- END OF FILE analysis/trend.py (CORRECTED V35.2) ---
