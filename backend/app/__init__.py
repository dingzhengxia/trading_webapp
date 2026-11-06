# backend/app/__init__.py
"""应用包入口：最先加载 .env，确保各模块导入时读到的环境变量已就绪。"""
from .core.env_loader import load_env as _load_env

_load_env()
