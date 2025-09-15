# Dockerfile (语法修正版)

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

# --- 核心修改在这里：修复 --from 的语法 ---
# 将 --from-frontend-builder 改为 --from=frontend-builder
COPY --from=frontend-builder /app/frontend/dist ./backend/app/frontend_dist
# --- 修改结束 ---

WORKDIR /app/backend
EXPOSE 8000

# 使用稳定的单进程模式
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]