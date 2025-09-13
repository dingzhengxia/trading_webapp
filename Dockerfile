# =================================================================
# STAGE 1: Build Frontend (编译前端)
# 使用一个包含完整构建工具的 Node.js 官方镜像
# =================================================================
FROM node:20 AS frontend-builder

# 设置工作目录
WORKDIR /app/frontend

# 1. 只复制 package.json 和 package-lock.json
# 这样只有在依赖变化时，npm install 才会重新运行，能有效利用缓存
COPY frontend/package*.json ./

# 2. 安装前端依赖
# --prefer-offline 尝试使用缓存，减少网络请求
# --no-audit 跳过安全审计，加快速度
RUN npm install --prefer-offline --no-audit

# 3. 复制所有前端源代码
COPY frontend/ ./

# 4. 运行构建命令
RUN npm run build


# =================================================================
# STAGE 2: Build Backend (构建后端)
# 使用一个轻量级的 Python 官方镜像
# =================================================================
FROM python:3.10-slim

# 设置环境变量
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

# 从构建上下文的 backend/ 目录复制配置文件到容器的 /app 目录
COPY backend/user_settings.json .
COPY backend/coin_lists.json .

# 暴露后端服务运行的端口
EXPOSE 8000

# 容器启动时运行的命令
CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "app.main:app", "--chdir", "backend"]