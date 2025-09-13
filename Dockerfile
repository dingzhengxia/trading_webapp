# =================================================================
# STAGE 1: Build Frontend (编译前端)
# =================================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build


# =================================================================
# STAGE 2: Build Backend (构建后端)
# =================================================================
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV IS_DOCKER=1

WORKDIR /app

# 安装 Python 依赖
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 复制后端代码
COPY backend/ ./backend/

# 从前端构建阶段复制编译好的静态文件
COPY --from=frontend-builder /app/frontend/dist ./backend/app/frontend_dist

# --- 核心修复：从 backend 目录复制配置文件 ---
# 从构建上下文的 backend/ 目录复制配置文件到容器的 /app 目录
COPY backend/user_settings.json .
COPY backend/coin_lists.json .
# --- 修复结束 ---

EXPOSE 8000

CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "app.main:app", "--chdir", "backend"]