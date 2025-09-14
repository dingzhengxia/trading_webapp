# Dockerfile

# =================================================================
# STAGE 1: Build Frontend
# =================================================================
FROM node:20 AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install --prefer-offline --no-audit
COPY frontend/ ./
RUN npm run build

# =================================================================
# STAGE 2: Final Production Image
# =================================================================
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV IS_DOCKER=1

WORKDIR /app

# --- 核心修复：先复制所有后端文件，包括配置文件 ---
COPY backend/ ./backend
# ---------------------------------------------------

# 从前端构建器复制 dist 文件
COPY --from-frontend-builder /app/frontend/dist ./backend/app/frontend_dist

# 安装依赖
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r ./backend/requirements.txt

# 设置最终的工作目录
WORKDIR /app/backend

EXPOSE 8000

CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "app.main:app"]