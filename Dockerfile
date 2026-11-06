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

# 信号策略配置（/app/signal_config.json，signals/scanner.py 读取；缺失时自动用兜底配置）
COPY signal_config.json .

# SQLite 数据目录（config.py / database.py 运行时写入 /app/data/app.db，建议运行时挂载卷持久化）
RUN mkdir -p /app/data

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