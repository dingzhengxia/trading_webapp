# Dockerfile (最终健壮版)

# =================================================================
# STAGE 1: Build Frontend
# =================================================================
# 使用一个更完整的 Node.js 镜像，避免 alpine 版本可能缺少的依赖
FROM node:20 AS frontend-builder

WORKDIR /app/frontend

# 复制前端代码
COPY frontend/ ./

# 清理并重新安装依赖，确保环境纯净
RUN rm -rf node_modules && npm install

# 运行构建
RUN npm run build


# =================================================================
# STAGE 2: Final Image
# =================================================================
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV IS_DOCKER=1

WORKDIR /app

# 安装 Python 依赖
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码
COPY backend/ ./backend/

# 复制配置文件
COPY backend/user_settings.json ./backend/user_settings.json
COPY backend/coin_lists.json ./backend/coin_lists.json

# 从前端构建阶段复制编译好的静态文件
COPY --from=frontend-builder /app/frontend/dist ./backend/app/frontend_dist

EXPOSE 8000

# 将工作目录改为 backend，确保 gunicorn 能找到 app.main
WORKDIR /app/backend

CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "app.main:app"]