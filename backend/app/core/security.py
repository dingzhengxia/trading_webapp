# backend/app/core/security.py (最终版)
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

from ..config.config import load_settings

# --- 配置 ---
settings = load_settings()
# 从 user_settings.json 中读取预设的访问密钥
APP_ACCESS_KEY = settings.get("app_access_key", "default_secret_key_change_this")

# 定义请求头中期望的密钥名称，例如 'X-API-KEY'
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)):
    """
    这是一个 FastAPI 依赖项，用于校验 API Key。
    它会检查请求头中的 'X-API-KEY' 是否与配置的密钥匹配。
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing API Key in header 'X-API-KEY'",
        )
    if api_key != APP_ACCESS_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key",
        )
    return api_key