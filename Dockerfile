# Dockerfile

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

# 缓存 pip 依赖
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码 (不包括配置文件)
COPY backend/ ./backend

# 从前端构建阶段复制编译好的静态文件
COPY --from=frontend-builder /app/frontend/dist ./backend/app/frontend_dist

WORKDIR /app/backend
EXPOSE 8000
CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "app.main:app"]