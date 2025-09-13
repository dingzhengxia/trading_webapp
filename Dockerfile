# =================================================================
# STAGE 1: Build Frontend (编译前端)
# 使用一个包含 Node.js 的官方镜像作为编译环境
# =================================================================
FROM node:20-alpine AS frontend-builder

# 设置工作目录
WORKDIR /app/frontend

# 复制 package.json 和 package-lock.json 文件
COPY frontend/package*.json ./

# 安装前端依赖
RUN npm install

# 复制所有前端源代码
COPY frontend/ ./

# 运行构建命令，生成静态文件到 /app/frontend/dist
RUN npm run build


# =================================================================
# STAGE 2: Build Backend (构建后端)
# 使用一个轻量级的 Python 官方镜像作为最终的运行环境
# =================================================================
FROM python:3.10-slim

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV IS_DOCKER=1  # --- 在这里添加环境变量

# 设置工作目录
WORKDIR /app

# 复制后端的 Python 依赖文件
COPY backend/requirements.txt .

# 安装后端依赖
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 复制所有后端源代码到 /app/backend
COPY backend/ ./backend/

# 从第一阶段 (frontend-builder) 复制编译好的前端静态文件
COPY --from=frontend-builder /app/frontend/dist ./backend/app/frontend_dist

# 复制项目根目录下的配置文件
COPY user_settings.json .
COPY coin_lists.json .

# 暴露后端服务运行的端口
EXPOSE 8000

# 容器启动时运行的命令
# 使用 Gunicorn 作为生产级的 ASGI 服务器，比 uvicorn 更健壮
# (Gunicorn 在 Windows 上不原生支持, 但在 Docker (Linux) 环境中是最佳选择)
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "app.main:app", "--chdir", "backend"]