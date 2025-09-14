# =================================================================
# STAGE 1: Build Frontend (编译前端)
# =================================================================
FROM node:20 AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm install --prefer-offline --no-audit

COPY frontend/ ./
RUN npm run build


# =================================================================
# STAGE 2: Final Production Image (构建后端)
# =================================================================
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV IS_DOCKER=1

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 复制后端所有代码到 /app/backend/
COPY backend/ ./backend/

# 从前端构建阶段复制编译好的静态文件到 /app/backend/app/frontend_dist
COPY --from=frontend-builder /app/frontend/dist ./backend/app/frontend_dist

# --- 核心修复：从构建上下文的 backend/ 目录复制配置文件 ---
# 将它们复制到 /app/backend/ 目录中，与 config.py 的路径逻辑保持一致
COPY backend/user_settings.json ./backend/user_settings.json
COPY backend/coin_lists.json ./backend/coin_lists.json
# --- 修复结束 ---

# 将最终工作目录设置到 backend
WORKDIR /app/backend

EXPOSE 8000

CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "app.main:app"]