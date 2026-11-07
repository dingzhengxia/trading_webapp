# backend/app/core/env_loader.py
"""加载 .env 环境变量（本地运行与 Docker 均生效）。

规则：
- 依次尝试：项目根目录 `.env`（与 deploy.sh / start.bat 同级，**推荐放在这里**）、
  当前工作目录 `.env`、`/app/.env`（Docker 内项目根目录，deploy.sh 会以只读方式挂载）；
- **已存在的环境变量优先**（override=False），因此 Docker `--env-file` / 平台注入的值
  不会被 .env 覆盖；
- .env 里通常含交易所密钥，只加载不打印内容（仅打印命中的文件路径，便于排查“未配置”）；
  缺失 python-dotenv 时静默跳过，不影响仅用真实环境变量的部署方式。
"""
from pathlib import Path
from typing import List, Optional

from loguru import logger

from .paths import PROJECT_ROOT

_LOADED = False


def _candidates() -> List[Path]:
    """项目根目录 .env 优先，其次当前工作目录（Docker 下根目录即 /app）。"""
    return list(dict.fromkeys([PROJECT_ROOT / '.env', Path.cwd() / '.env']))


def load_env(force: bool = False) -> Optional[Path]:
    """加载第一个存在的 .env 文件；返回已加载的路径（未加载返回 None）。"""
    global _LOADED
    if _LOADED and not force:
        return None
    _LOADED = True

    try:
        from dotenv import load_dotenv
    except ImportError:  # 未安装 python-dotenv：完全依赖进程环境变量
        return None

    for path in _candidates():
        if path.is_file():
            load_dotenv(dotenv_path=str(path), override=False)
            logger.info(f'已加载环境变量文件: {path}')
            return path
    logger.warning('未找到 .env 文件，仅使用进程环境变量')
    return None
