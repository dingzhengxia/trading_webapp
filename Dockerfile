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

# --- 核心修复：依赖缓存优化 ---
# 1. 只复制 requirements.txt 文件。
#    由于这个文件不经常变动，下面这层将能被长期缓存。
COPY backend/requirements.txt .

# 2. 在一个独立的层中安装依赖。
#    只要 requirements.txt 文件没有变化，Docker 就会直接使用这一层的缓存，
#    完全跳过下载和安装的过程。
RUN pip install --no-cache-dir -r requirements.txt
# --- 修复结束 ---

# 3. 现在再复制经常变动的后端源代码和配置文件。
#    这一层的变动不会影响到上面已经缓存好的依赖层。
COPY backend/ ./backend

# 4. 从前端构建器复制 dist 文件
COPY --from-frontend-builder /app/frontend/dist ./backend/app/frontend_dist

# 5. 设置最终的工作目录
WORKDIR /app/backend

# 6. 暴露端口
EXPOSE 8000

# 7. 启动命令
CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "app.main:app"]