# backend/run.py (完整更新版)
import uvicorn
import sys
from pathlib import Path

# --- 新增：路径设置 ---
# 将 backend 目录添加到 Python 的模块搜索路径中
# 这样 uvicorn 就能找到 app.main
sys.path.insert(0, str(Path(__file__).resolve().parent))
# --------------------

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)