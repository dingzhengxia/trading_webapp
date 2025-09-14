# Dockerfile
# 负责构建和运行应用

# STAGE 1: 构建器，包含了所有依赖和源代码
FROM trading-app-base:latest as builder

WORKDIR /app
COPY backend/ ./backend
COPY frontend/ ./frontend
COPY user_settings.json ./backend/user_settings.json
COPY coin_lists.json ./backend/coin_lists.json

# 构建前端
WORKDIR /app/frontend
RUN npm run build


# STAGE 2: 最终的生产镜像
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV IS_DOCKER=1

# 复制虚拟环境（包含所有Python依赖）
COPY --from=builder /opt/venv /opt/venv

# 将虚拟环境添加到 PATH
ENV VENV_PATH=/opt/venv
ENV PATH="$VENV_PATH/bin:$PATH"

WORKDIR /app/backend

# 从构建器复制后端代码和已编译的前端
COPY --from=builder /app/backend .
COPY --from=builder /app/frontend/dist ./app/frontend_dist

EXPOSE 8000

# gunicorn 现在是虚拟环境的一部分
CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "app.main:app"]