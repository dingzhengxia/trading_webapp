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
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from ..config.config import load_settings
from ..reports import dingtalk

MAX_BATCH = 20          # 单条合并消息最多包含的信号数
MAX_ITEM_CHARS = 1200   # 单条信号正文上限（超出截断，保留整体可读性）

# 中国市场习惯：红涨绿跌 -> 做多红、做空绿
_DIRECTION_LABEL = {
    'long': '🔴 做多',
    'short': '🟢 做空',
    'neutral': '⚪ 中性',
}


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


def _format_item(index: int, record: Dict[str, Any]) -> str:
    direction = str(record.get('direction') or 'neutral').lower()
    label = _DIRECTION_LABEL.get(direction, '⚪ 中性')
    strategy = str(record.get('strategy') or 'unknown')
    timeframe = str(record.get('timeframe') or '-')
    title = str(record.get('title') or record.get('symbol') or '信号').strip()
    price = _format_price(record.get('price'))

    meta = f"{label} · 周期 `{timeframe}` · 策略 `{strategy}`"
    if price:
        meta += f" · 价格 `{price}`"

    body = str(record.get('message') or '').strip()
    if len(body) > MAX_ITEM_CHARS:
        body = body[:MAX_ITEM_CHARS].rstrip() + '…'

    lines = [f"**{index}. {title}**", '', meta]
    if body:
        lines.extend(['', body])
    return '\n'.join(lines)


def format_signal_batch(records: List[Dict[str, Any]]) -> Tuple[str, str]:
    """把一批信号格式化为 (通知标题, markdown 正文)。"""
    records = [r for r in records if isinstance(r, dict)]
    count = len(records)
    if count == 1:
        title = str(records[0].get('title') or '币种信号')
    else:
        title = f'🔔 币种信号 × {count}'

    parts = [f"### 🔔 币种信号 · {count} 条", '']
    for index, record in enumerate(records, start=1):
        if index > 1:
            parts.extend(['', '---', ''])
        parts.append(_format_item(index, record))
    return title, '\n'.join(parts)


async def push_signal_batch(records: List[Dict[str, Any]],
                            settings: Optional[Dict[str, Any]] = None) -> bool:
    """推送一批信号到钉钉；任何异常都吞掉，绝不影响扫描/自动开仓主流程。"""
    if not records:
        return False
    try:
        if not is_enabled(settings):
            return False
        title, text = format_signal_batch(records)
        sent = await dingtalk.send_markdown(title, text)
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
