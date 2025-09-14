# Dockerfile
# 负责整合代码并构建最终应用

# =============================================================
# STAGE 1: Builder - 准备所有文件
# =============================================================
FROM trading-app-base:latest AS builder

WORKDIR /app

# 复制源代码
COPY backend/ ./backend
COPY frontend/ ./frontend

# 构建前端
WORKDIR /app/frontend
RUN npm run build


# =============================================================
# STAGE 2: Final - 创建最终的、干净的生产镜像
# =============================================================
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV IS_DOCKER=1

# 复制虚拟环境（包含所有Python依赖）
COPY --from=builder /opt/venv /opt/venv

# 激活虚拟环境
ENV VENV_PATH=/opt/venv
ENV PATH="$VENV_PATH/bin:$PATH"

WORKDIR /app/backend

# --- 核心修复：从 builder 阶段的正确位置复制所有需要的文件 ---
# 1. 复制后端代码
COPY --from=builder /app/backend .
# 2. 复制已编译的前端
COPY --from=builder /app/frontend/dist ./app/frontend_dist
# --- 修复结束 ---

EXPOSE 8000

CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "app.main:app"]