# backend/app/signals/families.py
"""策略信号族（signal family）映射。

用于自动开仓的「确认数」统计：同一族内的多份策略实现共享同一套市场逻辑
（例如趋势突破族既有均线突破、EMA 交叉、通道突破），若按策略名计数，
一次趋势突破能同时点亮 3~4 条信号，确认数门槛形同虚设。

按族计数可保证「多个独立逻辑同时看多/看空」才构成真正共振。
"""
from typing import Dict

# 策略名 -> 信号族
STRATEGY_FAMILY: Dict[str, str] = {
    # 趋势突破族：均线 / EMA 交叉 / 通道突破，本质都是「顺势突破」
    'ma_breakout': 'trend',
    'ema_cross': 'trend',
    'trend_channel_breakout': 'trend',
    # 关键位族：前高前低、支撑阻力的测试与突破
    'level_breakout': 'level',
    # 订单块族：机构挂单区（LuxAlgo / FluxCharts 两种 swing 口径）
    'ob_luxalgo': 'order_block',
    'ob_fluxcharts': 'order_block',
    # 波动率族：压缩后的扩张突破
    'volatility_breakout': 'volatility',
    # 反转族：超买超卖 / 背离
    'rsi_divergence': 'reversal',
    'kdj_cross': 'reversal',
    # K 线动能族：连续同向 K 线后的衰竭提示
    'consecutive_candles': 'candle_streak',
}

FAMILY_LABELS: Dict[str, str] = {
    'trend': '趋势突破',
    'level': '关键位',
    'order_block': '订单块',
    'volatility': '波动率',
    'reversal': '反转',
    'candle_streak': 'K线动能',
}


def family_of(strategy: str) -> str:
    """返回策略所属信号族；未登记的策略退化为「自身的族」（按策略名独立计）。"""
    key = str(strategy or '')
    return STRATEGY_FAMILY.get(key, key)


def family_label(strategy: str) -> str:
    fam = family_of(strategy)
    return FAMILY_LABELS.get(fam, fam)
