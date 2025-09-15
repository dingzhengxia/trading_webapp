# Dockerfile (最终完整版)

# =================================================================
# STAGE 1: Build Frontend
# =================================================================
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# =================================================================
# STAGE 2: Final Production Image
# =================================================================
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV IS_DOCKER=1

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend
COPY --from=frontend-builder /app/frontend/dist ./backend/app/frontend_dist

WORKDIR /app/backend
EXPOSE 8000

# --- 核心修改：使用 Uvicorn 并指定 workers ---
# 这比 Gunicorn + UvicornWorker 的组合更直接、更稳定
# --workers 2 可以利用多核，Uvicorn 会处理好进程管理
# 如果您的服务器是单核的，可以将 --workers 2 改为 --workers 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]