# backend/app/core/env_loader.py
"""加载 .env 环境变量（本地运行与 Docker 均生效）。

规则：
- 依次尝试：环境变量 PROJECT_ROOT 指定目录、项目根目录、当前工作目录、/app/.env；
- **已存在的环境变量优先**（override=False），因此 Docker `--env-file` / 平台注入的值
  不会被 .env 覆盖；
- .env 里通常含交易所密钥，只加载不打印；缺失 python-dotenv 时静默跳过，
  不影响仅用真实环境变量的部署方式。
"""
from pathlib import Path
from typing import List, Optional

_LOADED = False


def _candidates() -> List[Path]:
    project_root = Path(__file__).resolve().parents[3]
    return [
        project_root / '.env',
        Path.cwd() / '.env',
        Path('/app/.env'),
    ]


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
            return path
    return None
