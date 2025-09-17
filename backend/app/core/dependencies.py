# backend/app/core/dependencies.py (新文件)
from typing import Dict, Any
from ..config.config import load_settings

# REFACTOR: 创建一个依赖注入函数来提供配置。
# 这避免了在每个API端点函数内部重复调用 load_settings()。
# FastAPI的依赖注入系统会处理调用，使得API层代码更干净，
# 并且未来如果更换配置源（如Redis），只需修改这一个地方。
def get_settings_dependency() -> Dict[str, Any]:
    """
    FastAPI依赖项，用于加载和提供应用配置。
    """
    return load_settings()