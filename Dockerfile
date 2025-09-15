# Dockerfile (最终单进程版)

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
COPY --from-frontend-builder /app/frontend/dist ./backend/app/frontend_dist

WORKDIR /app/backend
EXPOSE 8000

# --- 核心修改：强制使用单 worker ---
# 移除了 --workers 参数，让 Uvicorn 以默认的单进程模式运行。
# 这将确保 TradingService 和 asyncio 事件循环是真正的全局单例，彻底解决状态不一致和“僵尸”进程问题。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]