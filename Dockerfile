# Dockerfile

# =================================================================
# STAGE 1: Builder (构建器)
# 这一阶段负责安装所有依赖并编译前端
# =================================================================
FROM node:20 AS builder

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 1. 安装 Python 和 pip
RUN apt-get update && apt-get install -y python3 python3-pip

# 2. 设置工作目录
WORKDIR /app

# 3. 复制依赖定义文件
COPY backend/requirements.txt ./backend/
COPY frontend/package*.json ./frontend/

# 4. 安装所有依赖 (Python 和 Node)
#    将它们放在同一个 RUN 指令中，可以更好地利用缓存
RUN pip3 install --no-cache-dir -r ./backend/requirements.txt && \
    cd frontend && npm install

# 5. 复制所有源代码
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# 6. 构建前端
RUN cd frontend && npm run build


# =================================================================
# STAGE 2: Final (最终镜像)
# 这一阶段只包含运行所需的最小文件
# =================================================================
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV IS_DOCKER=1

WORKDIR /app/backend

# 1. 从构建器复制 Python 依赖
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
# 复制 gunicorn, uvicorn 等可执行文件
COPY --from=builder /usr/local/bin/gunicorn /usr/local/bin/gunicorn
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn

# 2. 复制后端代码和配置文件
COPY --from=builder /app/backend .

# 3. 复制编译好的前端
COPY --from=builder /app/frontend/dist ./app/frontend_dist

EXPOSE 8000

CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "app.main:app"]