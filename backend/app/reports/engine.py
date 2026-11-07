# backend/app/reports/engine.py
"""周期报告生成（自 monitor/app/tasks/periodic_reporter.py 并入）。

与原实现的差异：
- 行情统一走 signals.market_data（RestGuardian 限流 + TTL 缓存 + in-flight 去重），
  不再裸调 exchange / 手动 sleep(rateLimit)；
- 去掉 monitor 的全局 cached_top_symbols 共享状态，每次运行现算 TopN（无并发竞态）；
- 恐惧贪婪指数请求失败静默跳过，不影响报告主体；
- 输出纯文本 markdown，UI 报告页、网页日志、钉钉共用同一份内容。
"""
import asyncio
import json
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import pandas_ta as pta
from loguru import logger

from ..signals.service import get_market_data

# 报告周期 -> 分钟
REPORT_INTERVALS: Dict[str, int] = {
    '1h': 60, '2h': 120, '4h': 240, '6h': 360, '8h': 480, '12h': 720, '1d': 1440,
}

FEAR_GREED_URL = 'https://api.alternative.me/fng/?limit=1'


def interval_minutes(value: Any, default: int = 240) -> int:
    """把 '4h' / '1d' 之类的周期字符串换算成分钟；非法值返回 default。"""
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    text = str(value or '').strip().lower()
    if text in REPORT_INTERVALS:
        return REPORT_INTERVALS[text]
    try:
        if text.endswith('m'):
            return max(1, int(float(text[:-1])))
        if text.endswith('h'):
            return max(1, int(float(text[:-1]) * 60))
        if text.endswith('d'):
            return max(1, int(float(text[:-1]) * 1440))
    except (TypeError, ValueError):
        pass
    return default


def ohlcv_to_df(ohlcv: Any) -> Optional[pd.DataFrame]:
    """ccxt ohlcv 数组 -> DataFrame；数据不足或格式异常返回 None。"""
    if not ohlcv:
        return None
    try:
        df = pd.DataFrame(list(ohlcv), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        if df.empty or len(df) < 3:
            return None
        for column in ('open', 'high', 'low', 'close', 'volume'):
            df[column] = pd.to_numeric(df[column], errors='coerce')
        return df.dropna(subset=['open', 'close'])
    except Exception as exc:  # noqa: BLE001 - 单币种数据异常不应中断整份报告
        logger.debug(f"K 线转换失败: {exc}")
        return None


def summarize_ohlcv(df: pd.DataFrame, conf: Dict[str, Any]) -> Dict[str, Any]:
    """从单币种 K 线中提取报告所需的四项指标（纯函数，便于离线测试）。

    指标口径与 monitor 原实现一致：只看最后一根**已收盘**K 线（df.iloc[-2]）。
    """
    volume_ma_period = int(conf.get('volume_ma_period') or 20)
    min_consecutive = int(conf.get('min_consecutive_candles') or 2)
    result: Dict[str, Any] = {}

    if len(df) < volume_ma_period + 2:
        return result

    last = df.iloc[-2]
    open_price = float(last['open'])
    close_price = float(last['close'])
    if open_price > 0:
        result['gain'] = (close_price - open_price) / open_price * 100
    result['close'] = close_price

    # 连涨根数（从最后一根收盘 K 线往前数）
    count = 0
    for offset in range(2, len(df) + 1):
        candle = df.iloc[-offset]
        if float(candle['close']) > float(candle['open']):
            count += 1
        else:
            break
    if count >= min_consecutive:
        result['consecutive'] = count

    volume_ma = df['volume'].rolling(window=volume_ma_period).mean().shift(1).iloc[-2]
    if volume_ma and not pd.isna(volume_ma) and volume_ma > 0:
        result['volume_ratio'] = float(last['volume']) / float(volume_ma)
        result['volume'] = float(last['volume'])
        result['volume_ma'] = float(volume_ma)

    return result


def calc_rsi(df: pd.DataFrame, period: int) -> Optional[float]:
    """最后一根已收盘 K 线的 RSI；数据不足/计算失败返回 None。"""
    if len(df) < period + 1:
        return None
    try:
        rsi_series = pta.rsi(df['close'], length=period)
        value = rsi_series.iloc[-2] if rsi_series is not None else None
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception as exc:  # noqa: BLE001 - RSI 仅作参考，失败跳过
        logger.debug(f"RSI 计算失败: {exc}")
        return None


def _fetch_fear_greed_sync(timeout: float = 8.0) -> Optional[Dict[str, Any]]:
    try:
        with urllib.request.urlopen(FEAR_GREED_URL, timeout=timeout) as response:
            payload = json.loads(response.read().decode('utf-8'))
        item = (payload.get('data') or [{}])[0]
        value = int(item.get('value'))
        return {'value': value, 'classification': str(item.get('value_classification') or 'Unknown')}
    except Exception as exc:  # noqa: BLE001 - 外部依赖，失败不影响报告
        logger.debug(f"恐惧贪婪指数获取失败（跳过）: {exc}")
        return None


async def fetch_fear_greed() -> Optional[Dict[str, Any]]:
    """恐惧贪婪指数（第三方接口，异步线程执行，失败返回 None）。"""
    return await asyncio.to_thread(_fetch_fear_greed_sync)


def render_markdown(report_conf: Dict[str, Any], tf: str, sentiment: Optional[Dict[str, Any]],
                    gainers: List[Dict[str, Any]], volume_ratios: List[Dict[str, Any]],
                    overbought: List[Dict[str, Any]], oversold: List[Dict[str, Any]],
                    consecutive: List[Dict[str, Any]], scanned: int) -> str:
    """把统计结果渲染为 markdown 文本（与 monitor 原格式保持一致）。"""
    top_n_gainers = int(report_conf.get('top_n_gainers') or 10)
    top_n_volume_ratio = int(report_conf.get('top_n_volume_ratio') or 10)
    message = ''

    if sentiment:
        emoji = "😱" if sentiment['classification'] in ("Fear", "Extreme Fear") else "🤑"
        message += (f"### {emoji} 市场情绪: {sentiment['classification']} "
                    f"({sentiment['value']}/100)\n\n---\n\n")

    if gainers:
        message += f"### 🚀 {tf} 周期涨幅榜\n\n"
        for index, item in enumerate(sorted(gainers, key=lambda x: x['gain'], reverse=True)[:top_n_gainers]):
            message += f"{'🥇🥈🥉🔥'[index if index < 4 else 3]} **{item['symbol']}**\n> **涨幅: {item['gain']:.2f}%**\n\n"

    if volume_ratios:
        message += f"\n---\n\n### 📈 {tf} 周期成交量异动\n\n"
        for index, item in enumerate(sorted(volume_ratios, key=lambda x: x['ratio'], reverse=True)[:top_n_volume_ratio]):
            message += (f"{'🥇🥈🥉⚡️'[index if index < 4 else 3]} **{item['symbol']}**\n"
                        f"> **放量倍数: {item['ratio']:.2f} 倍**\n"
                        f"> (周期量: {item['volume']:.0f}, 均量: {item['volume_ma']:.0f})\n\n")

    if overbought:
        message += f"\n---\n\n### 🥵 {tf} 周期热门区超买合约\n\n"
        for item in overbought:
            message += f"🥵 **{item['symbol']}**\n> **RSI: {item['rsi']:.1f}**\n\n"

    if oversold:
        message += f"\n---\n\n### 🥶 {tf} 周期热门区超卖合约\n\n"
        for item in oversold:
            message += f"🥶 **{item['symbol']}**\n> **RSI: {item['rsi']:.1f}**\n\n"

    if consecutive:
        message += f"\n---\n\n### 💪 {tf} 周期连涨强势合约\n\n"
        for item in sorted(consecutive, key=lambda x: x['candles'], reverse=True):
            fire = '🔥' * (item['candles'] // 2) if item['candles'] > 3 else ('🔥' if item['candles'] == 3 else '')
            message += f"💪 **{item['symbol']}**\n> **连涨: {item['candles']} 根** {fire}\n\n"

    if not any([gainers, volume_ratios, overbought, oversold, consecutive]):
        message += "\n---\n\n### 😴 市场观察\n\n在本周期内未发现符合分析条件的异动资产。\n\n"

    message += f"\n---\n\n> 统计样本：{scanned} 个热门合约，周期 {tf}；数据仅供研究，不构成投资建议。"
    return message


async def generate_report(report_conf: Dict[str, Any], data_service=None) -> Dict[str, Any]:
    """生成一份周期报告，返回 {'title','markdown','generated_at','report_name','scanned'}。"""
    data = data_service or get_market_data()
    report_name = str(report_conf.get('report_name') or '周期报告')
    tf = str(report_conf.get('run_interval') or '4h')
    top_n = int(report_conf.get('top_n_by_volume') or 100)
    sentiment_conf = report_conf.get('market_sentiment') or {}
    sentiment_enabled = bool(sentiment_conf.get('enabled', False))

    symbols = await data.get_top_symbols_by_volume(top_n)
    if not symbols:
        raise RuntimeError("热门币种列表为空，无法生成报告（检查行情接口/TopN 配置）。")

    sentiment = await fetch_fear_greed() if sentiment_enabled else None
    rsi_period = int(sentiment_conf.get('rsi_period') or 14)
    required_len = max(200, rsi_period + 50)

    gainers: List[Dict[str, Any]] = []
    consecutive: List[Dict[str, Any]] = []
    volume_ratios: List[Dict[str, Any]] = []
    overbought: List[Dict[str, Any]] = []
    oversold: List[Dict[str, Any]] = []
    scanned = 0

    for index, symbol in enumerate(symbols):
        try:
            ohlcv = await data.get_ohlcv(symbol, tf, limit=required_len)
            df = ohlcv_to_df(ohlcv)
            if df is None:
                continue
            stats = summarize_ohlcv(df, report_conf)
            if not stats:
                continue
            scanned += 1

            if 'gain' in stats:
                gainers.append({'symbol': symbol, 'gain': stats['gain']})
            if 'consecutive' in stats:
                consecutive.append({'symbol': symbol, 'candles': stats['consecutive']})
            if 'volume_ratio' in stats:
                volume_ratios.append({
                    'symbol': symbol, 'ratio': stats['volume_ratio'],
                    'volume': stats['volume'], 'volume_ma': stats['volume_ma'],
                })

            # 与 monitor 一致：只对前 10 个币种算 RSI，避免整轮计算量过大
            if sentiment_enabled and index < 10:
                rsi_value = calc_rsi(df, rsi_period)
                if rsi_value is not None:
                    overbought_threshold = float(sentiment_conf.get('rsi_overbought') or 70)
                    oversold_threshold = float(sentiment_conf.get('rsi_oversold') or 30)
                    if overbought_threshold < rsi_value < 100:
                        overbought.append({'symbol': symbol, 'rsi': rsi_value})
                    elif 0 < rsi_value < oversold_threshold:
                        oversold.append({'symbol': symbol, 'rsi': rsi_value})
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 单币种失败继续下一个
            logger.debug(f"扫描 {symbol} 报告指标失败: {exc}")
            continue

    generated_at = datetime.now()
    markdown = render_markdown(report_conf, tf, sentiment, gainers, volume_ratios,
                              overbought, oversold, consecutive, scanned)
    title = f"📰 {report_name} ({generated_at.strftime('%Y-%m-%d %H:%M')}, {tf}周期)"
    return {
        'report_name': report_name,
        'title': title,
        'markdown': markdown,
        'generated_at': generated_at.timestamp(),
        'generated_at_text': generated_at.strftime('%Y-%m-%d %H:%M:%S'),
        'scanned': scanned,
        'symbols_total': len(symbols),
        'counts': {
            'gainers': len(gainers),
            'volume_ratios': len(volume_ratios),
            'overbought': len(overbought),
            'oversold': len(oversold),
            'consecutive': len(consecutive),
        },
    }
