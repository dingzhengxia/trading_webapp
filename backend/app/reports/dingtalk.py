# backend/app/reports/dingtalk.py
"""钉钉机器人推送（自 monitor notification_service 提取）。

约定：
- webhook / secret **只从环境变量读取**，不写入配置文件、不落数据库、不进日志：
  DINGTALK_WEBHOOK_URL、DINGTALK_SECRET（可选，加签用）；
- 是否推送由设置项 dingtalk_enabled 控制（默认关闭），未配置 webhook 时自动跳过；
- 发送走线程池（requests 是同步库），不阻塞事件循环；
- 单条 markdown 过长会被钉钉拒绝，这里按字符数截断并提示。
"""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
from typing import Optional

from loguru import logger

MAX_MARKDOWN_CHARS = 18000  # 钉钉 markdown 上限约 20KB，留出余量


def webhook_url() -> str:
    return (os.getenv('DINGTALK_WEBHOOK_URL') or '').strip()


def webhook_secret() -> str:
    return (os.getenv('DINGTALK_SECRET') or '').strip()


def is_configured() -> bool:
    """是否已通过环境变量配置 webhook（不含密钥内容判断）。"""
    return bool(webhook_url())


def build_signed_url(url: str, secret: str, timestamp_ms: Optional[int] = None) -> str:
    """按钉钉加签规则拼接 timestamp + sign（无 secret 时原样返回）。"""
    if not secret:
        return url
    timestamp = str(int(timestamp_ms if timestamp_ms is not None else time.time() * 1000))
    string_to_sign = f'{timestamp}\n{secret}'
    hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'),
                         digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    separator = '&' if '?' in url else '?'
    return f"{url}{separator}timestamp={timestamp}&sign={sign}"


def truncate(text: str, limit: int = MAX_MARKDOWN_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + '\n\n> ⚠️ 内容过长已截断，完整报告请在网页「周期报告」页查看。'


def send_markdown_sync(title: str, text: str, timeout: float = 10.0) -> bool:
    """同步发送 markdown（标准库 urllib，无第三方依赖）；失败只记 warning，不抛异常。"""
    url = webhook_url()
    if not url:
        logger.debug('钉钉推送跳过：未配置 DINGTALK_WEBHOOK_URL')
        return False

    payload = {'msgtype': 'markdown', 'markdown': {'title': title, 'text': truncate(text)}}
    data = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(
        build_signed_url(url, webhook_secret()),
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode('utf-8') or '{}')
        if body.get('errcode') == 0:
            logger.info('✅ 钉钉推送成功')
            return True
        logger.warning(f"钉钉推送失败: {body.get('errcode')} {body.get('errmsg')}")
        return False
    except Exception as exc:  # noqa: BLE001 - 通知失败绝不影响主流程
        logger.warning(f"钉钉推送异常: {exc}")
        return False


async def send_markdown(title: str, text: str) -> bool:
    """异步发送（线程池执行 requests）。"""
    if not is_configured():
        return False
    return await asyncio.to_thread(send_markdown_sync, title, text)
