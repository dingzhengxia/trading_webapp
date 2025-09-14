# Dockerfile
# 负责使用基础镜像来构建最终的应用镜像。

# =============================================================
# STAGE 1: Builder - 在基础镜像环境中准备所有文件
# =============================================================
FROM trading-app-base:latest AS builder

# 继承基础镜像的环境变量
ENV VENV_PATH=/opt/venv
ENV PATH="$VENV_PATH/bin:$PATH"

WORKDIR /app

# 复制源代码
COPY backend/ ./backend
COPY frontend/ ./frontend

# 构建前端 (使用基础镜像中已安装的 npm 依赖)
WORKDIR /app/frontend
RUN npm run build


# =============================================================
# STAGE 2: Final - 创建最终的、干净的生产镜像
# =============================================================
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV IS_DOCKER=1

# 1. 从 builder 阶段复制完整的、包含所有依赖的虚拟环境
COPY --from=builder /opt/venv /opt/venv

# 2. 激活虚拟环境
ENV VENV_PATH=/opt/venv
ENV PATH="$VENV_PATH/bin:$PATH"

# 3. 创建并设置工作目录
WORKDIR /app/backend

# 4. 从 builder 阶段复制后端代码和已编译的前端
COPY --from=builder /app/backend .
COPY --from=builder /app/frontend/dist ./app/frontend_dist

# 5. 暴露端口
EXPOSE 8000

# 6. 启动命令
#    Gunicorn 会使用 PATH 中我们指定的虚拟环境里的 Python 和包
CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "app.main:app"]