# backend/app/core/paths.py
"""项目根目录与运行环境判定（唯一来源）。

原先 config.py / database.py / signals/scanner.py 各自复制了一份
「IS_DOCKER ? /app : 上溯 4 级」的判断，路径写错一处就会读写到别的目录，
统一收敛到这里。
"""
import os
from pathlib import Path

IS_DOCKER: bool = bool(os.environ.get('IS_DOCKER'))

# backend/app/core/paths.py → parents[0]=core, [1]=app, [2]=backend, [3]=项目根
PROJECT_ROOT: Path = Path('/app') if IS_DOCKER else Path(__file__).resolve().parents[3]
