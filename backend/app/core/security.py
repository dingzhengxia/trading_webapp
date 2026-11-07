# backend/app/core/security.py
import secrets

from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

from ..config.config import DEFAULT_CONFIG, load_settings

# 用于识别"用户从未修改过默认访问密钥"的哨兵值。
DEFAULT_ACCESS_KEY = str(DEFAULT_CONFIG.get('app_access_key', ''))

# 定义请求头中期望的密钥名称，例如 'X-API-KEY'
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)


def get_app_access_key() -> str:
    """每次校验时从配置读取访问密钥。

    config.load_settings() 内部带有缓存，开销可以忽略；这样在设置页改完Key
    后无需重启服务，也不会在 import 时把密钥固化。
    """
    return str(load_settings().get('app_access_key') or '')


def access_key_warning() -> str | None:
    """检查访问密钥是否为空或仍是默认值，返回需要打印的醒目告警。"""
    access_key = get_app_access_key()
    if not access_key:
        return "!!! 安全警告：app_access_key 为空，所有交易接口都会拒绝访问。请在设置页配置强随机密钥。"
    if access_key == DEFAULT_ACCESS_KEY:
        return ("!!! 安全警告：app_access_key 仍为默认值，等同于公开访问！"
                "请立即在设置页修改为强随机密钥，并轮换交易所 API Key。")
    return None


def _keys_equal(provided: str, expected: str) -> bool:
    try:
        return secrets.compare_digest(provided, expected)
    except TypeError:
        return provided == expected


async def verify_api_key(api_key: str = Security(api_key_header)):
    """FastAPI 依赖项：校验请求头中的 'X-API-KEY'。"""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing API Key in header 'X-API-KEY'",
        )
    expected_key = get_app_access_key()
    if not expected_key or not _keys_equal(str(api_key), expected_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key",
        )
    return api_key
