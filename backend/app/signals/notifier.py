# backend/app/signals/notifier.py
"""币种信号的钉钉推送（补齐 Phase 2 合并时未并入的通知链路）。

背景：monitor 的 notification_service 在合并计划里被明确排除（MERGE_PLAN §1
"钉钉/桌面通知留作 Phase 3"），所以信号只走「内存缓冲 + 网页信号页」，
钉钉群只会收到周期报告、仓位保护告警，收不到任何币种信号。

设计：
- 消费循环同一批（同一次队列排空）的信号合并为一条 markdown，避免
  100 币种 × 多策略 × 多周期刷屏，也避开钉钉机器人 20 条/分钟的限流；
- webhook / secret 只从环境变量读取，复用 app.reports.dingtalk（含加签与截断）；
- 开关：全局 dingtalk_enabled（与报告共用）且 signal_dingtalk_enabled（信号子开关，默认开）。
"""
import asyncio
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from ..config.config import load_settings
from ..reports import dingtalk

MAX_BATCH = 20          # 单条合并消息最多包含的信号数
MAX_ITEM_CHARS = 1200   # 单条信号正文上限（超出截断，保留整体可读性）

# 钉钉机器人限流 20 条/分钟：批间强制最小间隔（推送 task 串行排队，短时突发自动合并节奏）
MIN_PUSH_INTERVAL_SEC = 5.0

DEFAULT_PUSH_VOLUME_MULTIPLIER = 2.0  # 非静态币推送所需的成交量倍数默认值

# 用户偏好：红跌绿涨 -> 做多绿、做空红
_DIRECTION_LABEL = {
    'long': '🟢 做多',
    'short': '🔴 做空',
    'neutral': '⚪ 中性',
}


def _static_bases(settings: Dict[str, Any]) -> set:
    """静态币种列表（base 大写集合），这些币的信号无条件推送。"""
    return {
        str(base).strip().upper()
        for base in (settings.get('signal_scan_static_symbols') or [])
        if str(base).strip()
    }


def filter_for_push(records: List[Dict[str, Any]], settings: Dict[str, Any]) -> List[Dict[str, Any]]:
    """推送层量能过滤：静态币实时全推，其它币要求放量达标。

    - signal_push_volume_multiplier <= 0 表示不过滤（全部推送）；
    - 倍数取信号记录里的 volume_ratio（当前量/动态基准，已按周期进度调整），
      与 signal_config.json 各策略的成交量确认是同一口径，但作用在推送层，
      不影响信号产生与自动开仓；
    - 无法计算倍数的信号（如资金费率告警）按不达标处理，不推送。
    """
    try:
        multiplier = float(settings.get('signal_push_volume_multiplier',
                                        DEFAULT_PUSH_VOLUME_MULTIPLIER) or 0)
    except (TypeError, ValueError):
        multiplier = DEFAULT_PUSH_VOLUME_MULTIPLIER
    if multiplier <= 0:
        return list(records)

    static = _static_bases(settings)
    kept: List[Dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        base = str(record.get('symbol') or '').strip().upper()
        if base in static:
            kept.append(record)
            continue
        ratio = record.get('volume_ratio')
        if isinstance(ratio, (int, float)) and ratio >= multiplier:
            kept.append(record)
    return kept


def is_enabled(settings: Optional[Dict[str, Any]] = None) -> bool:
    """是否应当推送信号：已配置 webhook + 总开关 + 信号子开关。"""
    if not dingtalk.is_configured():
        return False
    conf = settings if isinstance(settings, dict) else load_settings()
    return bool(conf.get('dingtalk_enabled', False)) and bool(conf.get('signal_dingtalk_enabled', True))


def _format_price(price: Any) -> str:
    try:
        value = float(price)
    except (TypeError, ValueError):
        return ''
    if value >= 1000:
        return f'{value:,.2f}'
    if value >= 1:
        return f'{value:.4f}'
    return f'{value:.6g}'


def _format_item(index: int, record: Dict[str, Any], body: Optional[str] = None) -> str:
    direction = str(record.get('direction') or 'neutral').lower()
    label = _DIRECTION_LABEL.get(direction, '⚪ 中性')
    strategy = str(record.get('strategy') or 'unknown')
    timeframe = str(record.get('timeframe') or '-')
    title = str(record.get('title') or record.get('symbol') or '信号').strip()
    price = _format_price(record.get('price'))

    meta = f"{label} · 周期 `{timeframe}` · 策略 `{strategy}`"
    if price:
        meta += f" · 价格 `{price}`"
    ratio = record.get('volume_ratio')
    if isinstance(ratio, (int, float)) and ratio > 0 and ratio != float('inf'):
        meta += f" · 放量 `{ratio:.1f}x`"

    if body is None:
        body = str(record.get('message') or '').strip()
    if len(body) > MAX_ITEM_CHARS:
        body = body[:MAX_ITEM_CHARS].rstrip() + '…'

    lines = [f"**{index}. {title}**", '', meta]
    if body:
        lines.extend(['', body])
    return '\n'.join(lines)


# 消息尾部的「成交量分析」块：vol_text 以 "\n---\n**成交量分析**…" 拼在模板最后
_VOLUME_SPLIT_RE = re.compile(r'\n*-{3,}\s*\n\*{2}成交量分析\*\*[\s\S]*$')


def split_volume_block(message: str) -> Tuple[str, str]:
    """把消息尾部的「成交量分析」块剥离，返回 (正文, 成交量块)。无块时第二项为空。"""
    match = _VOLUME_SPLIT_RE.search(message or '')
    if not match:
        return (message or '').strip(), ''
    volume_block = match.group(0).strip().lstrip('-').strip()
    return message[:match.start()].rstrip(), volume_block


def format_signal_batch(records: List[Dict[str, Any]]) -> Tuple[str, str]:
    """把一批信号格式化为 (通知标题, markdown 正文)。

    同一币种同一周期的多条信号（指标入场 + 破位/离场类）合并为一组连续展示，
    组内「成交量分析」只保留一份——同一根 K 线的量能数据完全相同，重复
    展示只会刷屏。
    """
    records = [r for r in records if isinstance(r, dict)]
    count = len(records)
    if count == 1:
        title = str(records[0].get('title') or '币种信号')
    else:
        title = f'🔔 币种信号 × {count}'

    # groups: {(symbol, timeframe): [(序号, 信号, 剥离成交量块后的正文)]}
    # volume_blocks: 每组保留第一份非空成交量分析（同根K线数据完全相同）
    groups: dict = {}
    volume_blocks: dict = {}
    for index, record in enumerate(records, start=1):
        body, volume_block = split_volume_block(str(record.get('message') or ''))
        key = (str(record.get('symbol') or '').upper(), str(record.get('timeframe') or '-'))
        groups.setdefault(key, []).append((index, record, body))
        if volume_block and key not in volume_blocks:
            volume_blocks[key] = volume_block

    parts = [f"### 🔔 币种信号 · {count} 条", '']
    first_group = True
    for key, items in groups.items():
        if not first_group:
            parts.extend(['', '---', ''])
        first_group = False
        for position, (index, record, body) in enumerate(items):
            if position:
                parts.append('')
            parts.append(_format_item(index, record, body))
        volume_block = volume_blocks.get(key)
        if volume_block:
            parts.extend(['', volume_block])
    return title, '\n'.join(parts)


# 推送节流状态（同一事件循环内串行化；跨 loop 复用时惰性重建）
_push_lock: Optional[asyncio.Lock] = None
_last_push_at = 0.0


async def push_signal_batch(records: List[Dict[str, Any]],
                            settings: Optional[Dict[str, Any]] = None) -> bool:
    """推送一批信号到钉钉；任何异常都吞掉，绝不影响扫描/自动开仓主流程。

    推送按 MIN_PUSH_INTERVAL_SEC 节流（钉钉机器人 20 条/分钟），短时多批自动排队。
    """
    global _push_lock, _last_push_at
    if not records:
        return False
    try:
        conf = settings if isinstance(settings, dict) else load_settings()
        if not is_enabled(conf):
            return False
        records = filter_for_push(records, conf)
        if not records:
            logger.debug('📡 [信号] 本批信号全部未达推送量能门槛，跳过钉钉推送')
            return False
        if _push_lock is None:
            _push_lock = asyncio.Lock()
        async with _push_lock:
            wait = MIN_PUSH_INTERVAL_SEC - (time.monotonic() - _last_push_at)
            if wait > 0:
                await asyncio.sleep(wait)
            title, text = format_signal_batch(records)
            sent = await dingtalk.send_markdown(title, text)
            _last_push_at = time.monotonic()
        if sent:
            logger.info(f"📡 [信号] 钉钉推送成功（{len(records)} 条）")
        else:
            logger.warning(f"📡 [信号] 钉钉推送失败（{len(records)} 条）")
        return sent
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - 通知失败不影响主流程
        logger.warning(f"📡 [信号] 钉钉推送异常: {exc}")
        return False
